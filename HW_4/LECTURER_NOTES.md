# Пояснення до домашнього завдання №4

## Посилання

- HW4: https://github.com/MAXGODDYK/rag-homework/tree/HW_4/HW_4
- Pull request: https://github.com/MAXGODDYK/rag-homework/pull/1
- QLoRA repository:
  https://github.com/MAXGODDYK/qwen3-grounded-rag-finetuning

## Що я реалізував

У HW4 я продовжив retrieval pipeline з попередніх робіт і додав
повний grounded RAG. Система не відповідає безпосередньо зі знань
мовної моделі: спочатку знаходить інформацію в локальній базі, а
потім передає моделі тільки три найкращі chunks.

Фінальний pipeline:

```text
question
→ semantic retrieval + BM25
→ top-10 candidates
→ BGE reranking
→ top-3 chunks
→ confidence gate
→ grounded multilingual prompt
→ FreeModel або fine-tuned local Qwen
→ JSON і citation validation
→ answer із джерелами або fallback
```

Knowledge base не змінювалася: це 3 українські документи про
планування навчання, 25 chunks, multilingual embeddings розмірності
384 і FAISS `IndexFlatIP`.

## Grounding і безпечний fallback

Модель повинна повернути JSON з відповіддю, citations та прапорцем
`insufficient_context`. Код дозволяє цитувати тільки `chunk_id` із
retrieved top-3. Якщо JSON або citations неправильні, виконується
одна repair-спроба. Після другої помилки повертається безпечний
fallback.

Перед генерацією я перевіряю raw BGE score. Якщо найкращий score
нижче `0.005`, LLM взагалі не викликається. Наприклад, питання про
столицю Франції та зміну університету були відхилені за 112–116 мс
і не отримали вигаданих відповідей чи citations.

## Провайдери

Я реалізував три adapters:

- OpenAI `gpt-4.1-mini` через Responses API;
- FreeModel через OpenAI-compatible `/chat/completions`;
- local `Qwen/Qwen3-4B-Instruct-2507` із власним LoRA adapter.

У live-перевірці використовувалися FreeModel і local Qwen.
Офіційний OpenAI не запускався, оскільки окремий
`OPENAI_API_KEY` не налаштований. Якщо зовнішній provider має
мережеву або API-помилку, інтерактивний режим може явно перейти на
local Qwen. Під час evaluation такий перехід вимкнений, щоб не
підміняти результати одного provider іншим.

## Fine-tuning Qwen

Для Qwen я підготував окремий репозиторій із 80 вручну перевіреними
SFT-прикладами: 60 answerable і 20 insufficient-context, трьома
мовами та split `64/8/8`.

Навчання виконано через QLoRA: 4-bit NF4, LoRA `r=16`,
`alpha=32`, 3 epochs, BF16 compute і gradient checkpointing.
Фінальний adapter пройшов quality gate:

| Метрика | Base Qwen | LoRA adapter |
|---|---:|---:|
| JSON validity | 1.000 | 1.000 |
| Citation validity | 1.000 | 1.000 |
| Fallback accuracy | 1.000 | 1.000 |
| Manual groundedness | 0.875 | 0.875 |

Я не вважаю це покращенням якості: adapter не гірший за base за
groundedness, але не перевершив його і був трохи повільнішим. Цей
результат залишив у звіті без прикрашання.

## Evaluation HW4

Однакові 8 питань перевіряли прямі відповіді, paraphrases,
англійський запит і два випадки без достатнього контексту.

| Provider | Успішні результати | Правильний answer/fallback | Invalid citations | Ручна оцінка | Mean latency |
|---|---:|---:|---:|---|---:|
| FreeModel | 8/8 | 8/8 | 0 | 7 relevant, 1 partially relevant | 17.1 s |
| Local Qwen + LoRA | 8/8 | 8/8 | 0 | 6 relevant, 2 partially relevant | 12.9 s |
| OpenAI | не запускався | — | — | ключ не налаштований | — |

Під час FreeModel evaluation один запит отримав тимчасову server
error. Окремий повтор завершився успішно, а ця подія явно записана
у звіті.

## Telegram-бот

Бот працює через long polling і підтримує:

- `/start` і `/help`;
- `/provider openai|freemodel|local`;
- `/status`, `/sources` і `/reset`;
- не більше 1000 символів у питанні;
- 5 питань користувача за 10 хвилин;
- окремі денні ліміти зовнішніх providers;
- безпечне розбиття довгих повідомлень.

Я перевірив у Telegram обидва робочі providers, українські та
англійські питання, citations, `/sources`, confidence fallback,
rate limit і `/reset`. Ключі, питання користувачів та локальний
стан не зберігаються в Git.

## Основні файли

- `README.md` — запуск і повна документація;
- `outputs/rag_answers_examples.md` — усі відповіді та ручні оцінки;
- `outputs/rag_evaluation.json` — машинний evaluation-звіт;
- `outputs/telegram_bot_live_test.md` — результати live-перевірки;
- `scripts/rag/` — retrieval, prompt, providers і validation;
- `scripts/telegram_bot/` — Telegram interface та rate limiting.

## Обмеження

- база складається тільки з 25 chunks;
- evaluation містить лише 8 питань;
- citation validation перевіряє дозволені ID, але не є повною
  автоматичною entailment-перевіркою;
- FreeModel є стороннім gateway і може мати тимчасові server errors;
- local Qwen потребує NVIDIA GPU та CUDA;
- історія діалогу свідомо не використовується.

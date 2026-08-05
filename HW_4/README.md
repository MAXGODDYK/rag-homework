# HW4: Grounded RAG, Telegram-бот і fine-tuned Qwen

HW4 продовжує retrieval pipeline з HW3 і додає генерацію
grounded-відповідей, автоматичну перевірку JSON/citations,
confidence fallback, CLI, Telegram-інтерфейс, зовнішній
FreeModel API і локальну
`Qwen3-4B-Instruct-2507` з LoRA adapter.

Knowledge base не змінювалася: 3 українські HTML-документи,
25 chunks і FAISS-індекс із 384-вимірними embeddings.

## Pipeline

```text
question
→ optional source_file filter
→ semantic + BM25 (0.75 / 0.25)
→ top-10 hybrid candidates
→ BAAI/bge-reranker-v2-m3
→ top-3 chunks
→ raw BGE confidence gate (0.005)
→ grounded prompt
→ OpenAI gpt-4.1-mini, FreeModel або local Qwen + LoRA
→ JSON та citation validation
→ одна repair-спроба
→ answer + sources або deterministic fallback
```

BGE використовується для інтерактивного retrieval, тому що в HW3
він працював приблизно 2.1 секунди на query, тоді як
Qwen3-Reranker-4B на CPU потребував близько 28 секунд.

Якщо найкращий raw BGE score нижче `0.005`, LLM не викликається.
Поріг обрано за фактичними перевірками бази: релевантні питання
мали score від `0.0114`, сторонні — до `0.0005`.

## Структура

```text
HW_4/
├── config/
│   └── settings.py
├── local_config/
│   ├── constants.example.py
│   └── constants.py              # ignored
├── local_state/                  # ignored
├── data/
├── index/
├── outputs/
│   ├── rag_answers_examples.md
│   ├── rag_evaluation.json
│   └── prompt_improvements.md
├── prompts/
│   ├── grounded_qa_prompt.txt
│   └── repair_prompt.txt
├── scripts/
│   ├── rag_answer.py
│   ├── evaluate_rag.py
│   ├── rag/
│   └── telegram_bot/
├── tests/
├── README.md
└── requirements.txt
```

Скрипти HW3 (`retrieval.py`, `retrieval_improved.py`,
`evaluate_retrieval.py`) збережені.

## Встановлення

Команди PowerShell із каталогу `HW_4`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Для local provider потрібні NVIDIA GPU, CUDA і CUDA-enabled
PyTorch. Перевірка:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```

Перший retrieval-запуск завантажує BGE reranker обсягом близько
2.29 GB. Перший local-запуск також завантажує базову Qwen;
вона завантажується в 4-bit NF4, BF16 compute. Без CUDA local
provider недоступний, але зовнішні API providers продовжують
працювати за наявності ключів і доступного балансу.

## Secrets і локальні значення

Пріоритет налаштувань:

```text
OS environment / HW_4/.env
→ local_config/constants.py
→ tracked defaults
```

Скопіюйте `local_config/constants.example.py` у
`local_config/constants.py` і заповніть тільки локально:

```python
TELEGRAM_BOT_TOKEN = ""
OPENAI_API_KEY = ""
FREEMODEL_API_KEY = ""
HF_TOKEN = ""
LOCAL_ADAPTER_PATH = r"C:\...\artifacts\qwen3-4b-grounded-lora-v4"
```

`constants.py`, `.env`, `.venv` і `local_state` не потрапляють у
Git. У tracked example немає реальних токенів.

FreeModel є стороннім OpenAI-compatible gateway, а не сервісом
OpenAI. Для нього використовується окремий ключ, base URL
`https://api.freemodel.dev/v1`, модель-router `auto` і endpoint
`/chat/completions`. Не слід передавати через зовнішній gateway
приватні або чутливі дані.

## CLI

OpenAI:

```powershell
.\.venv\Scripts\python.exe .\scripts\rag_answer.py `
    "Як скласти реалістичний план підготовки до іспиту?" `
    --provider openai `
    --top-k 3 `
    --candidate-k 10
```

FreeModel:

```powershell
.\.venv\Scripts\python.exe .\scripts\rag_answer.py `
    "Як скласти реалістичний план підготовки до іспиту?" `
    --provider freemodel
```

Локальна Qwen:

```powershell
.\.venv\Scripts\python.exe .\scripts\rag_answer.py `
    "How can a student balance studying, sleep, and rest?" `
    --provider local
```

При мережевій/API-помилці OpenAI або FreeModel виконується явний
перехід на local provider, якщо CUDA й adapter доступні. Помилка не
приховується: зовнішній результат містить notice.

## Grounded JSON contract

Модель повинна повернути тільки:

```json
{
  "answer": "Текст відповіді",
  "citations": ["exam_time_planning_chunk_005"],
  "insufficient_context": false
}
```

Python-код перевіряє точний набір полів, типи, непорожню
відповідь, citations як підмножину top-3, наявність citation для
звичайної відповіді та порожній список для fallback. Після першої
помилки виконується одна repair-спроба; друга помилка завершується
безпечним fallback.

## Telegram-бот

```powershell
.\.venv\Scripts\python.exe -m scripts.telegram_bot.bot
```

Команди:

- `/start` — можливості бота;
- `/help` — приклад і команди;
- `/provider openai|freemodel|local` — provider поточного чату;
- `/status` — конфігурація providers, CUDA/adapter і ліміти;
- `/sources` — chunks останньої відповіді;
- `/reset` — OpenAI за замовчуванням і очищення останньої відповіді.

Історія діалогу не використовується. Захист:

- до 1000 символів у питанні;
- 5 запитів користувача за 10 хвилин;
- окремо до 100 OpenAI і 100 FreeModel-запитів на добу;
- ignored-лічильник `local_state/bot_usage.json`;
- одна local generation одночасно;
- питання і ключі не записуються в application logs;
- довгі відповіді розбиваються за лімітом Telegram;
- `/reset` не скидає rate limits.

## Evaluation

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_rag.py
.\.venv\Scripts\python.exe .\scripts\apply_rag_manual_reviews.py
```

Вісім обов’язкових питань були запущені через local provider.
OpenAI не запускався, тому що в середовищі перевірки не було
`OPENAI_API_KEY`; у звіті ці запуски чесно позначено `skipped`.
Evaluation вимикає автоматичний перехід між providers, щоб збій
зовнішнього API не був помилково зарахований як його результат.
FreeModel adapter додано й перевірено unit-тестами та live-запуском
5 серпня 2026 року. Вісім питань можна окремо повторити командою:

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_rag.py `
    --providers freemodel
```

| ID | Тема | Результат | Ручна оцінка |
|---|---|---|---|
| q01 | План підготовки | answer + citations | relevant |
| q02 | Продуктивний час | answer + citations | relevant |
| q03 | Термінове/важливе | answer + citations | partially relevant |
| q04 | Відкладання навчання | answer + citations | relevant |
| q05 | Study/sleep/rest, EN | answer + citations | relevant |
| q06 | Перерви | answer + citations | partially relevant |
| q07 | Столиця Франції | confidence fallback | relevant |
| q08 | Зміна університету | confidence fallback | relevant |

Підсумок local run:

- 8/8 очікуваних fallback/non-fallback рішень;
- 0 citations поза retrieved top-3;
- 6 `relevant`, 2 `partially relevant`, 0 `not relevant`;
- q07 raw BGE `0.000017`, q08 `0.000497`, обидва нижче `0.005`.

Підсумок FreeModel run:

- 8/8 успішних підсумкових результатів;
- 8/8 очікуваних fallback/non-fallback рішень;
- 0 citations поза retrieved top-3;
- 7 `relevant`, 1 `partially relevant`, 0 `not relevant`;
- середня latency 17.1 секунди, p95 42.0 секунди;
- q06 спочатку отримав тимчасову `InternalServerError` від gateway,
  але окремий повтор завершився успішно; це явно зазначено у звіті.

Деталі з відповідями, scores, chunks і коментарями:
`outputs/rag_answers_examples.md`. Машиночитаний результат:
`outputs/rag_evaluation.json`. Розвиток prompt:
`outputs/prompt_improvements.md`.

## Fine-tuning repository

QLoRA-код, 80 reviewed SFT-прикладів і фінальний LoRA adapter
знаходяться в окремому локальному репозиторії:

```text
C:\Все мои проэкты\qwen3-grounded-rag-finetuning
```

Зв’язок виконується тільки через `LOCAL_ADAPTER_PATH`; Git
submodule не використовується. Base Qwen weights і проміжні
checkpoints не комітяться.

Фінальний held-out quality gate:

| Metric | Base Qwen | LoRA adapter |
|---|---:|---:|
| JSON validity | 1.000 | 1.000 |
| Citation validity | 1.000 | 1.000 |
| Fallback accuracy | 1.000 | 1.000 |
| Manual groundedness | 0.875 | 0.875 |
| Mean generation latency | 7.57 s | 8.41 s |

Adapter пройшов заданий gate, але не покращив manual
groundedness і був трохи повільнішим. Це не приховується.

## Тести

```powershell
.\.venv\Scripts\python.exe -m compileall config scripts tests
.\.venv\Scripts\python.exe -m pytest -q
```

Unit/integration tests використовують fake providers і не
витрачають API. Вони перевіряють precedence settings, межі prompt,
confidence fallback, JSON/citations, repair і rate limiting.

## Обмеження

- knowledge base містить лише 25 chunks;
- evaluation має тільки 8 питань;
- citation validation не є повною entailment-перевіркою;
- 2 local-відповіді отримали лише `partially relevant`;
- local Qwen потребує CUDA і значно повільніша за API-відповідь;
- OpenAI не був live-перевірений через відсутність окремого
  `OPENAI_API_KEY`;
- Telegram token live-перевірено через `getMe`, а application і
  handlers успішно збираються; повний діалог треба перевіряти при
  запущеному long polling;
- FreeModel є стороннім gateway і під час evaluation один раз
  повернув тимчасову серверну помилку;
- історія діалогу, hybrid answer synthesis з більшим контекстом і
  окремий faithfulness evaluator не реалізовані.

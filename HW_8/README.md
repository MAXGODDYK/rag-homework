# HW8: evaluation + observability layer

У HW8 я додав мінімальний, але відтворюваний шар оцінювання для chatbot-а
з попередніх робіт. Мета — не лише показати окрему відповідь, а зберегти
trace кожного сценарію, порахувати метрики та чесно зафіксувати обмеження.

## Що оцінюється

Eval set містить 10 фіксованих запитань у
`data/evaluation/chatbot_eval_cases.json`:

| Тип сценарію | Кількість | Покриття |
|---|---:|---|
| RAG / fallback | 7 | прості KB-питання, retrieval, складний і неоднозначний retrieval, English query, два out-of-domain fallback |
| NBU tool | 2 | поточний USD та перерахунок 100 EUR у гривні |
| Agent clarification | 1 | неоднозначний запит без retrieval і tools |

RAG cases запускають справжній pipeline з HW4/HW5: multilingual embeddings,
hybrid retrieval, BGE reranking, confidence gate, prompt builder та
validation citations. NBU cases роблять live read-only запит до офіційного
API НБУ через існуючий allowlisted tool.

У цьому середовищі OpenAI, FreeModel і local Qwen не налаштовані. Тому
generation для RAG cases виконує локальний `EvaluationProvider`: він повертає
короткий extractive фрагмент top-1 context із валідною citation. Це дає
відтворювану перевірку retrieval, confidence gate і JSON/citation contract,
але **не є оцінкою якості live LLM generation**. Це обмеження прямо
зафіксовано в summary та quality report.

## Артефакти

| Файл | Призначення |
|---|---|
| `outputs/eval_results.csv` | таблиця з усіма обов'язковими полями завдання та додатковими latency/mode полями |
| `outputs/eval_traces.jsonl` | machine-readable traces, один record на case |
| `outputs/eval_metrics.json` | machine-readable підсумок метрик |
| `outputs/eval_summary.md` | observability metrics summary |
| `outputs/quality_report.md` | аналіз результатів і три головні проблеми |

`eval_results.csv` містить: `id`, `question`, `expected_behavior`, `answer`,
`retrieved_chunks`, `route_or_mode`, `tools_used`, `task_success`,
`groundedness`, `answer_quality`, `latency_ms`, `errors` та `notes`.

## Запуск

Усі команди запускаються з кореневої папки репозиторію, де знаходиться
`HW_8`.

```powershell
py -3.14 -m venv .\HW_8\.venv
.\HW_8\.venv\Scripts\python.exe -m pip install -r .\HW_8\requirements.txt
```

Запустити evaluation та перезаписати всі артефакти:

```powershell
.\HW_8\.venv\Scripts\python.exe `
    .\HW_8\scripts\evaluate_chatbot.py
```

Альтернативна папка для експериментального запуску:

```powershell
.\HW_8\.venv\Scripts\python.exe `
    .\HW_8\scripts\evaluate_chatbot.py `
    --output-dir .\HW_8\outputs\manual_run
```

## Метрики

Скрипт автоматично розраховує:

- `total_cases`;
- `success_rate` — кількість `task_success = yes` / усі cases;
- `groundedness_good_rate` — кількість `groundedness = good` / усі cases;
- `average_latency_ms`;
- `top_error_types`.

Також я зберігаю partial/failure counts, retrieval latency і max latency,
щоб наступний запуск можна було порівняти з поточним без зміни eval set.

## Відтворюваність та інтерпретація

- Questions, expected chunks і критерії успіху зафіксовані до запуску у
  `chatbot_eval_cases.json`.
- NBU rate, timestamps і latency є live-даними, тому вони змінюються між
  запусками.
- `EvaluationProvider` детермінований, тому RAG answer/citation contract
  можна відтворити. Реальний reranker та NBU API при цьому запускаються.
- `task_success` перевіряє очікуваний route та relevant chunk/citation;
  `groundedness` перевіряє, чи підтримана відповідь дозволеним context або
  офіційним NBU result.

## Тестування

```powershell
.\HW_8\.venv\Scripts\python.exe -m compileall -q .\HW_8\config .\HW_8\scripts .\HW_8\tests
.\HW_8\.venv\Scripts\python.exe -m pytest -q .\HW_8\tests
```

Тести перевіряють діапазон та coverage eval set, всі обов'язкові CSV columns,
формули metrics, JSONL traces, а також повну регресію успадкованих HW5-HW7
сценаріїв.

Фактична перевірка фінального стану: `73 passed`. Поточний live запуск
evaluation дав `9/10 = 90%` success rate, `10/10 = 100%` groundedness-good
та один partial retrieval case; точні latency і NBU rates збережені в
артефактах цього запуску.

## Обмеження і наступний крок

Детальний аналіз знаходиться в `outputs/quality_report.md`. Головні наступні
кроки: metadata filtering/query rewriting для нечітких запитів, live provider
evaluation на тому самому set і оптимізація CPU reranking latency.

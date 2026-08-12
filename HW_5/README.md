# HW5: зовнішній tool офіційного курсу НБУ

## Посилання для перевірки

- HW5: https://github.com/MAXGODDYK/rag-homework/tree/HW_5/HW_5
- Pull request: https://github.com/MAXGODDYK/rag-homework/pull/2

HW5 продовжує grounded RAG та Telegram-бот із HW4 і додає
read-only tool `get_nbu_exchange_rate`. Він отримує поточний або
історичний офіційний курс через
[Developer API НБУ](https://bank.gov.ua/en/open-data/api-dev) і
перераховує суму у гривні. API key та confirmation не потрібні.

Knowledge base не змінювалася: 3 українські HTML-документи,
25 chunks, multilingual embeddings `(25, 384)`, FAISS,
semantic + BM25 retrieval і BGE reranking.

## Pipeline

```text
Telegram question або /rate
→ currency intent prefilter
→ LLM router або прямий command call
→ strict Pydantic validation
→ allowlisted get_nbu_exchange_rate
→ fixed HTTPS endpoint НБУ
→ response validation
→ Decimal calculation
→ deterministic answer
```

Якщо prefilter не бачить ознак валютного запиту, LLM-router не
викликається і питання одразу переходить у незмінений grounded RAG
pipeline HW4. Router може вибрати лише `rag` або
`get_nbu_exchange_rate`; довільні function names, URL, SQL та extra
fields заборонені.

## Основні файли

```text
HW_5/
├── config/settings.py
├── local_config/constants.py       # ignored
├── local_state/                    # ignored
├── outputs/
│   ├── tool_examples.md
│   └── telegram_bot_live_test.md
├── prompts/
│   ├── tool_router_prompt.txt
│   └── tool_router_repair_prompt.txt
├── scripts/
│   ├── external_tool.py
│   ├── generate_tool_examples.py
│   ├── tools/
│   │   ├── schemas.py
│   │   ├── nbu_exchange.py
│   │   ├── router.py
│   │   └── orchestrator.py
│   ├── rag/                         # HW4
│   └── telegram_bot/
├── tests/
├── LECTURER_NOTES.md
├── README.md
└── requirements.txt
```

## Встановлення

PowerShell із каталогу `HW_5`:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Для local Qwen потрібні NVIDIA GPU і CUDA-enabled PyTorch. На
машині перевірки використовувався PyTorch 2.11 + CUDA 12.8:

```powershell
.\.venv\Scripts\python.exe -m pip install --force-reinstall `
    torch==2.11.0+cu128 `
    --index-url https://download.pytorch.org/whl/cu128

.\.venv\Scripts\python.exe -c `
    "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Без CUDA працюють NBU tool, FreeModel/OpenAI та всі функції, які не
використовують local Qwen. `tzdata` додано явно для правильної
перевірки поточної дати `Europe/Kyiv` на Windows.

## Secrets

Пріоритет налаштувань:

```text
OS environment / HW_5/.env
→ local_config/constants.py
→ tracked public defaults
```

Скопіюйте `local_config/constants.example.py` у `constants.py` і
заповніть тільки локально. НБУ tool не потребує нового ключа.
`constants.py`, `.env`, `.venv`, model cache та `local_state` не
потрапляють у Git.

## CLI: прямий tool call

```powershell
.\.venv\Scripts\python.exe .\scripts\external_tool.py call `
    --currency USD `
    --amount 100 `
    --date 2026-08-11
```

Режим `call` не використовує LLM: аргументи одразу проходять
Pydantic validation і allowlisted tool registry.

## CLI: natural-language routing

```powershell
.\.venv\Scripts\python.exe .\scripts\external_tool.py route `
    "How much is 50 GBP in UAH at today's official NBU rate?" `
    --provider freemodel
```

Підтримуються `openai`, `freemodel` і `local`. Router повертає
strict JSON. Після першої помилки дозволена одна repair-спроба;
друга помилка завершується безпечним повідомленням із порадою
скористатися `/rate`. Непідтверджені параметри не підставляються.

## Input/output contract

Input:

```json
{
  "currency_code": "USD",
  "date": "2026-08-11",
  "amount": 100
}
```

- `currency_code`: рівно три латинські літери, uppercase;
- `date`: необов’язкова ISO-дата, не пізніше сьогодні;
- `amount`: `0.01–1000000`, default `1`;
- extra fields заборонені.

Нормалізований output містить окремі `requested_date` та
`effective_date`, оскільки дата чинного курсу може відрізнятися від
запитаної. HTTP timeout — 10 секунд. Код перевіряє status, JSON
array, усі обов’язкові поля, currency code, додатний rate і
`exchangedate`. Розрахунок виконується через `Decimal`, результат
округлюється до копійок.

Timeout, network error, malformed JSON, HTTP error та unknown
currency перетворюються на безпечний `ExternalToolError` без
внутрішніх деталей.

## Telegram

### Перший запуск

Відкрийте PowerShell у корені клонованого репозиторію — у
каталозі, де знаходиться папка `HW_5`. Якщо репозиторій ще не
клоновано:

```powershell
git clone --branch HW_5 --single-branch `
    https://github.com/MAXGODDYK/rag-homework.git
Set-Location ".\rag-homework"
```

Якщо локального файла налаштувань ще немає, створіть його з
безпечного прикладу:

```powershell
Copy-Item `
    ".\HW_5\local_config\constants.example.py" `
    ".\HW_5\local_config\constants.py"
```

Відкрийте `HW_5\local_config\constants.py` і заповніть щонайменше
`TELEGRAM_BOT_TOKEN`. Для звичайних RAG-запитів також налаштуйте
`FREEMODEL_API_KEY`, `OPENAI_API_KEY` або local provider. Для
команди `/rate` окремий ключ НБУ не потрібен. Файл
`constants.py` і `local_state` ігноруються Git.

Запустіть bot у foreground:

```powershell
Set-Location ".\HW_5"
.\.venv\Scripts\python.exe -m scripts.telegram_bot.bot
```

Якщо `HW_5\.venv` ще не створено:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.telegram_bot.bot
```

Після успішного запуску в консолі з'явиться:

```text
=============== TELEGRAM BOT ===============
Polling started. Press Ctrl+C to stop.
```

Одночасно має працювати лише один екземпляр bot із цим token,
інакше Telegram long polling поверне conflict.

### Зупинка

У тому самому вікні PowerShell натисніть `Ctrl+C` і дочекайтеся
повернення командного рядка. Це штатно завершує polling.

Якщо вікно було закрито, а процес залишився працювати, знайдіть
лише процес HW5 bot і зупиніть його:

```powershell
$bot = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match '^python(.exe)?$' -and
        $_.CommandLine -like '*scripts.telegram_bot.bot*'
    }

$bot | Select-Object ProcessId, CommandLine
$bot | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

Перед `Stop-Process` перевірте показаний `CommandLine`, щоб не
зупинити інший Python-процес.

Нові команди:

- `/rate USD` — поточний курс;
- `/rate EUR 100` — перерахунок суми;
- `/rate PLN 500 2026-08-01` — історичний курс;
- `/sources` після tool-відповіді — tool name, validated input,
  НБУ URL та effective date;
- `/reset` — очищення останнього RAG/tool результату.

Звичайний текст із валютними ознаками проходить LLM-router.
Навчальні питання продовжують повертати RAG chunks. `/status`
показує доступність providers і НБУ tool. Зберігаються обмеження
HW4: 1000 символів, 5 запитів за 10 хвилин, денні API limits,
одна local generation і відсутність питань/ключів у logs.

## Реальні результати 11 серпня 2026

| Перевірка | Результат |
|---|---|
| Current USD | 44.8305 UAH |
| 100 EUR | 5178.15 UAH |
| PLN, 2026-08-01 | 11.8975 UAH |
| 50 GBP, English + FreeModel router | 3025.84 UAH |
| Той самий GBP + local router | tool, ті самі arguments і result; 18.6 s |
| Invalid `US` | validation до HTTP |
| Навчальне питання | prefilter → RAG, NBU не викликано |

Повні inputs, official source URLs, normalized results та final
answers: `outputs/tool_examples.md`. Числа є snapshot конкретної
дати, тому поточні курси змінюватимуться при повторному запуску.

Перегенерувати звіт:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_tool_examples.py `
    --provider freemodel
```

## Тести

```powershell
.\.venv\Scripts\python.exe -m compileall -q config scripts tests
.\.venv\Scripts\python.exe -m pytest -q
```

Фактичний результат: `40 passed`. Mock HTTP transport покриває
успішну нормалізацію, `special=null`, unknown currency, timeout,
4xx/5xx, malformed response і відсутність HTTP для invalid input.
Fake providers перевіряють tool/RAG decisions, repair, allowlist і
fallback. Telegram tests перевіряють `/rate`, natural-language tool
call, `/sources`, `/reset` та rate limiting без витрати API.

## Обмеження

- NBU endpoint є зовнішньою залежністю і може бути тимчасово
  недоступний;
- LLM-router повільніший та менш надійний за прямий `/rate`;
- FreeModel є стороннім gateway;
- local Qwen потребує CUDA, близько 4B base weights і LoRA adapter;
- OpenAI live не перевірявся, оскільки окремий ключ не налаштований;
- tool конвертує тільки іноземну валюту в UAH за офіційним курсом;
- tool повертає довідкові дані, а не фінансову рекомендацію.

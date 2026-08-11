# JARVIS

JARVIS — мій експериментальний desktop AI-agent, який виріс із HW5.
Здаваний варіант домашнього завдання залишається у Git-гілці `HW_5`, а
ця версія розробляється окремо у `codex/HW_5-more-functionality`.

Проєкт поєднує локальний Tauri/React interface, FastAPI sidecar,
Telegram, dynamic document/repository RAG і typed tool registry з
обов'язковими permissions та audit trail.

## Архітектура

```text
Tauri 2 + React/TypeScript desktop
Telegram bot
CLI administrator
        ↓
FastAPI 127.0.0.1 + one-time IPC token
        ↓
bounded agent loop (maximum 8 steps)
        ↓
retrieval + allowlisted tools + approvals
        ↓
SQLite/FTS5 + FAISS + extracted files + repository graph
        ↓
local Qwen / FreeModel / OpenAI / external APIs
```

Основні правила:

- backend слухає тільки `127.0.0.1`;
- desktop передає випадковий IPC token у кожному HTTP request;
- Telegram працює в тому самому backend process;
- режим сесії після restart або `/reset` завжди `safe + workspace`;
- tool name має існувати у registry, а input проходить Pydantic validation;
- instructions із завантажених файлів вважаються untrusted content;
- API keys, OAuth tokens, allowlists, local state і model cache не комітяться.

Детальні схеми: [ARCHITECTURE.md](docs/ARCHITECTURE.md) і
[SECURITY.md](docs/SECURITY.md).

## Можливості

### Dynamic RAG

Підтримуються PDF, DOCX, PPTX, XLSX, OpenDocument, EPUB, HTML,
notebooks, текстові data-файли та основні мови програмування. Архіви
ZIP/TAR/TGZ/7z/RAR розпаковуються у sandbox із захистом від traversal,
links, encrypted archives, nested archives та decompression bombs.

Retrieval:

```text
SQLite FTS5
+ multilingual FAISS
+ symbol/import graph expansion
→ reciprocal-rank fusion
→ BGE reranking
→ page/cell/line citations
```

Повторний import використовує SHA-256 і пропускає незмінені файли.
`.gitignore`, `.venv`, `node_modules`, build outputs, binaries,
credentials та private keys виключаються. Повний список форматів і
поточні parser limitations знаходяться у
[SUPPORTED_FORMATS.md](docs/SUPPORTED_FORMATS.md).

### Tool registry

Початковий pack містить:

- офіційний курс НБУ;
- monthly budget, savings plan і loan amortization;
- study schedule, calculator, units і timezone;
- Open-Meteo weather та explicit URL reader;
- web search adapter;
- list/read/create/patch files;
- allowlisted argument-vector shell для tests/build;
- controlled Playwright browser;
- Windows UI Automation;
- Google Workspace і Microsoft Graph adapters.

Інтеграції без локального credential або runtime мають статус
`disabled`. Фінансові tools нічого не оплачують і повертають лише
довідкові розрахунки.

### Permissions

Кожна сесія має два незалежні параметри:

```text
mode:  safe | autonomous
scope: workspace | roots | computer
```

- `safe`: write, execute та external mutation потребують Confirm;
- `autonomous`: звичайні allowlisted operations можуть виконуватися
  автоматично;
- `high_risk`: завжди дві перевірки — видимий Confirm і короткий local
  code із desktop/CLI;
- Telegram ніколи не показує high-risk code;
- destructive drive-root path та unresolved path не можуть бути
  представлені як valid tool input.

## Структура

```text
JARVIS/
├── desktop/                    # Tauri 2 + React 19 + TypeScript
│   ├── src/
│   └── src-tauri/
├── jarvis/                     # новий unified backend
│   ├── ingestion/
│   ├── tools/
│   ├── agent.py
│   ├── api.py
│   ├── database.py
│   ├── retrieval.py
│   └── security.py
├── scripts/
│   ├── telegram_bot/
│   ├── build_sidecar.py
│   ├── build_installer.ps1
│   └── legacy HW4/HW5 scripts
├── tests/
├── docs/
├── local_config/constants.py  # ignored
├── local_state/               # ignored
└── requirements.txt
```

## Встановлення backend

```powershell
cd "C:\Все мои проэкты\rag-homework\JARVIS"
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Playwright browser встановлюється окремо:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Local Qwen потребує CUDA-enabled PyTorch і не входить у model cache
репозиторію. OpenAI/FreeModel та зовнішні adapters працюють без CUDA.

## Local config

У desktop installer ключі можна ввести у **Settings**. Вони записуються
у локальний application profile як `.env`; API ніколи не повертає
значення назад, а показує тільки `configured/available`. FreeModel та
OpenAI підхоплюються одразу, Telegram token й integration tokens — після
перезапуску JARVIS. Файл не знаходиться всередині Git checkout.

Для development/CLI можна скопіювати
`local_config/constants.example.py` у ignored
`local_config/constants.py`. Значення також можна задати через
environment або `.env`.

```python
AUTHORIZED_TELEGRAM_USER_IDS = "123456789"
ADMIN_TELEGRAM_USER_IDS = "123456789"
JARVIS_ALLOWED_ROOTS = r"C:\work\one;C:\work\two"

TELEGRAM_BOT_TOKEN = ""
OPENAI_API_KEY = ""
FREEMODEL_API_KEY = ""
HF_TOKEN = ""
WEB_SEARCH_API_KEY = ""
```

Пріоритет лишився сумісним із HW4/HW5:

```text
OS environment / .env
→ local_config/constants.py
→ tracked public defaults
```

## Запуск

Backend із Telegram:

```powershell
.\.venv\Scripts\python.exe -m jarvis.cli serve --with-telegram
```

Окремий Telegram development launch:

```powershell
.\.venv\Scripts\python.exe -m scripts.telegram_bot.bot
```

Desktop development:

```powershell
cd desktop
npm install
npm run tauri dev
```

CLI diagnostics:

```powershell
.\.venv\Scripts\python.exe -m jarvis.cli migrate
.\.venv\Scripts\python.exe -m jarvis.cli status
.\.venv\Scripts\python.exe -m jarvis.cli users
.\.venv\Scripts\python.exe -m jarvis.cli roots
.\.venv\Scripts\python.exe -m jarvis.cli approvals
.\.venv\Scripts\python.exe -m jarvis.cli reindex <project-id>
.\.venv\Scripts\python.exe -m jarvis.cli emergency-shutdown
```

Telegram commands:

```text
/files
/uploadinfo
/use auto|all|<project-or-file>
/delete <file>
/clearfiles
/mode safe|autonomous
/scope workspace|roots|computer
/approvals
/whoami
/rate
/sources
/reset
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m compileall -q jarvis scripts tests
.\.venv\Scripts\python.exe -m pytest tests -q

cd desktop
npm run build
& "$env:USERPROFILE\.cargo\bin\cargo.exe" check --manifest-path .\src-tauri\Cargo.toml
```

Набір включає всі 40 tests із HW5 та нові tests для SQLite migrations,
IPC authentication, session reset, approvals, path scopes, parser
citations, archive traversal, repository symbols та user/project
isolation, write-only Settings і sidecar lifecycle. Live credentials не
витрачаються у unit tests.

## Installer

Перед build потрібні Rust, MSVC Build Tools і WebView2. Команда
створює Python sidecar, frontend та Windows NSIS/MSI bundle:

```powershell
.\scripts\build_installer.ps1
```

Згенеровані binaries, installer artifacts і PyInstaller cache ignored.
Компактний installer sidecar працює через FTS5 і remote providers; повний
`.venv` runtime додає multilingual FAISS/BGE та local Qwen без включення
CUDA libraries у installer.
Bundled sidecar отримує explicit config/state roots, а parent watchdog
завершує backend разом із desktop window.
Деталі та обмеження packaging описані у
[PACKAGING.md](docs/PACKAGING.md).

Фактичний стан першої версії та acceptance matrix наведені у
[IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Поточні обмеження

- OCR/STT/TTS/media мають extension points, але самі pipelines ще не
  реалізовані;
- encrypted та пошкоджені archives відхиляються;
- OAuth refresh/consent setup виконується поза JARVIS; adapters приймають
  локальний access token;
- remote provider отримує retrieved chunks, якщо користувач вибрав
  `remote-strong` або `auto`;
- маленька legacy knowledge base не є репрезентативним benchmark для
  довільних repository corpora;
- local Qwen weights не пакуються в Git або installer.
- profile `auto` спочатку використовує налаштований remote provider для
  швидкої routing-відповіді; `local-agent` вмикається явно і має значно
  повільніший cold start на 12-ГБ GPU.

## Git

Milestone commits створюються локально у
`codex/HW_5-more-functionality`. Push виконується тільки після окремого
підтвердження.

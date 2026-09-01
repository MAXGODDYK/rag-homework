# JARVIS Desktop RAG

JARVIS — мій локальний desktop-застосунок для роботи з власними документами
та репозиторіями. Я свідомо залишив один користувацький інтерфейс —
графічне вікно на моєму ПК. Telegram, зовнішні tools та agent loop прибрані:
застосунок відповідає лише на основі завантажених файлів і завжди показує
джерела.

## Що вміє застосунок

- імпортує папки проєктів та завантажені файли: PDF, DOCX, PPTX, XLSX,
  OpenDocument, EPUB, HTML, Markdown, CSV/JSON/YAML та код;
- безпечно розпаковує ZIP, TAR/TGZ, 7z і RAR без виконання їхнього вмісту;
- індексує текст у SQLite FTS5 та multilingual FAISS, зберігає page/cell/line
  metadata, symbols та dependency graph для коду;
- виконує hybrid retrieval і BGE reranking;
- дозволяє обрати current project, all projects або конкретний файл до запиту;
- повертає відповідь із citations. Якщо LLM не налаштована, працює
  `Evidence only`: показує релевантні уривки й citations без вигадування
  відповіді.

## RAG pipeline

```text
selected corpus/file
→ early metadata filter
→ SQLite FTS5 + multilingual FAISS + code-symbol expansion
→ reciprocal-rank fusion
→ BGE reranking
→ evidence gate
→ grounded JSON answer / extractive evidence / honest fallback
→ page, cell або line citations
```

Файли та їхні інструкції завжди трактуються як **untrusted context**. Модель
може процитувати лише chunks, які JARVIS фактично отримав у retrieval.

## Головне покращення фінального проєкту

Раніше вибраний файл фільтрувався лише після формування загального candidate
set. Через це chunk із потрібного файлу міг не потрапити до top candidates.
Тепер filter застосовується **до** FTS5, FAISS, graph expansion та BGE
reranking. Отже selector реально обмежує search space і всі citations
належать вибраному corpus.

Детальний before/after, changelog і обмеження: [FINAL_IMPROVEMENT.md](FINAL_IMPROVEMENT.md).

## Запуск desktop-версії

Команди виконуються з папки `JARVIS`.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd desktop
npm install
npm run tauri dev
```

Tauri запускає Python backend як локальний sidecar. Він слухає лише
`127.0.0.1`, використовує одноразовий IPC token і не відкриває мережевий
server назовні. Щоб зупинити застосунок, достатньо закрити desktop-вікно або
натиснути `Ctrl+C` у terminal, де запущено `npm run tauri dev`.

## Налаштування provider

Ключ можна ввести у **Settings** desktop-застосунку. Альтернативно треба
скопіювати `local_config/constants.example.py` у
`local_config/constants.py` та додати локальні значення. `constants.py`,
`.env`, індекси, завантажені файли й caches не потрапляють у Git.

Підтримуються `FreeModel` та `OpenAI`. Provider не є обов'язковим:
`Evidence only` не надсилає контекст у зовнішню модель і повертає лише
retrieved passages з citations.

## Перевірка

```powershell
.\.venv\Scripts\python.exe -m compileall -q jarvis scripts config tests
.\.venv\Scripts\python.exe -m pytest tests -q

cd desktop
npm run build
```

Автотести перевіряють IPC token, RAG-only API, parser-и, archive guards,
citations, evidence gate, extractive fallback і ранню metadata-фільтрацію.

## Обмеження

- Якість semantic search залежить від embedding/reranker моделей і розміру
  corpus.
- OCR, зображення, аудіо та відео не індексуються в цій версії.
- Індексація великої папки зараз виконується синхронно.
- BGE та FAISS потребують повного Python runtime; compact installer може
  працювати лише lexical mode.

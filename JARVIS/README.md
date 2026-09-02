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
- синхронізує current/history chunks з Google Sheets, а локально тримає
  text-free multilingual FAISS cache та карти IDs;
- виконує scope-aware semantic retrieval, candidate BM25, graph expansion і
  BGE reranking;
- дозволяє обрати current project, all projects або конкретний файл до запиту;
- повертає відповідь із citations через локальну Qwen3. Режим `Evidence only`
  за потреби показує релевантні уривки й citations без генерації відповіді.

## RAG pipeline

```text
project sync + chunking policy
→ Google Sheets Current / History + text-free FAISS cache
→ early project/file + representation filter
→ FAISS IDs → Sheets batch fetch → candidate BM25 + code graph
→ BGE reranking + evidence gate
→ grounded JSON answer / extractive evidence / honest fallback
→ page, cell або line citations
```

Перед кожним питанням JARVIS перевіряє весь активний проєкт. Він спершу
порівнює розмір і час зміни файла, а SHA-256 рахує лише для можливих змін.
Тому незмінені файли не ріжуться повторно і FAISS не перебудовується без
потреби. Після підключення Google Sheets повний текст не зберігається у
локальних artifacts:

```text
local_state/projects/<project-name>--<short-id>/
└── index/
    ├── embeddings.npy  # відновлювані вектори без вихідного тексту
    ├── faiss.index
    └── manifest.json   # chunk → row/document/representation maps
```

Змінений або видалений файл спочатку переноситься з `Chunks_Current` у
`Chunks_History`, після чого FAISS і maps оновлюються. Якщо нова версія не
парситься, вона має статус `rejected`, а застарілий текст не може бути
процитований. Перед відповіддю інтерфейс показує результат: перевірка,
відсутність змін, кількість оновлених/видалених або відхилених файлів.

## Режими нарізки chunks

У **Settings → Нарізка chunks для розробників** доступні глобальний режим і
окремі правила для Code, Web markup, Config/data, Documents, Tables,
Notebooks та Plain text.

- **Classic** — очищений семантичний текст для пояснень: HTML прибирає теги,
  metadata, scripts, styles і template-вміст; документи зберігають корисну
  структуру для citations.
- **Developer** — source-представлення. Код, HTML/XML, CSS, JSON/YAML/TOML та
  notebook cells зберігають рядки, відступи, коментарі, теги й атрибути.
  PDF/Office-файли мають структурований текст із page/slide/sheet/cell metadata,
  але не внутрішні ZIP/XML або binary bytes.
- **Mixed** — створює обидва представлення. Перед retrieval explainable router
  обирає Developer для code/error/tag/config запитів і Classic для summaries та
  пояснень. Окрема LLM для цього не використовується.

Якщо правило змінене, JARVIS перед наступним питанням переіндексує лише
відкритий проєкт: попередні chunks потрапляють у history і не беруть участі у
новому retrieval. Для Code значення **По умолчанию / Default** означає
Developer. Security-фільтри для `.env`, credentials, private keys, binaries і
executables діють у кожному режимі.

## Google Sheets chunks database

Після підключення Google Sheets стає **єдиною постійною текстовою базою**:
`Chunks_Current` містить актуальні chunks, `Chunks_History` — попередні
версії, `Files` — metadata файлів, а `Meta` — revision проєкту. Локально після
успішної міграції залишаються лише embeddings, FAISS-index та мапа
`chunk_id → Google Sheets row`; повний текст chunks, FTS, `chunks.jsonl`,
extracted text і local history очищаються.

Під час питання FAISS повертає до 100 IDs, JARVIS завантажує з Google Sheets
лише ці рядки, застосовує BM25 і BGE reranking, а після відповіді звільняє
candidate text з RAM. Якщо Sheets недоступні, JARVIS не використовує старі
локальні chunks і повертає безпечну помилку.

### One-time setup

1. У Google Cloud створіть service account, увімкніть **Google Sheets API** і
   **Google Drive API**, а JSON-ключ збережіть у приватній папці на ПК.
2. У Settings введіть шлях до JSON і свій Google e-mail.
3. Натисніть **Create / connect JARVIS DB**. JARVIS створить `JARVIS DB` та
   надасть вашому e-mail Editor-доступ.
4. Наступна синхронізація звірить ID/SHA/count перед очищенням локального
   text staging.

JSON service-account, `.env`, локальні індекси та текстові artifacts не
потрапляють у Git. Не надсилайте JSON-ключ у чат і не додавайте його до Git.

Файли та їхні інструкції завжди трактуються як **untrusted context**. Модель
може процитувати лише chunks, які JARVIS фактично отримав у retrieval.

## Головне покращення фінального проєкту

Раніше вибраний файл фільтрувався лише після формування загального candidate
set. Через це chunk із потрібного файлу міг не потрапити до top candidates.
Тепер filter застосовується **до** FTS5, FAISS, graph expansion та BGE
reranking. Отже selector реально обмежує search space і всі citations
належать вибраному corpus.

Матеріали для перевірки та захисту:

- [FINAL_IMPROVEMENT.md](FINAL_IMPROVEMENT.md) — before/after, changelog і
  remaining limitations;
- [docs/WORKFLOW_GRAPH.md](docs/WORKFLOW_GRAPH.md) — велике workflow-дерево;
- [DEFENSE_SCRIPT_UK.md](DEFENSE_SCRIPT_UK.md) — готовий текст виступу та
  live-demo;
- [outputs/presentation/JARVIS_FINAL_DEFENSE_UK.pptx](outputs/presentation/JARVIS_FINAL_DEFENSE_UK.pptx)
  — презентація на 10 слайдів.

## Запуск desktop-версії

Команди виконуються з папки `JARVIS`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# One-time local model download (about 9.3 GB for the Q4 variant).
ollama pull qwen3:14b

cd desktop
npm install
npm run tauri dev
```

Для Windows рекомендовано Python 3.12. Python 3.14 поки не використовується для
desktop backend через нестабільність native FAISS/Torch-пакетів у цьому
оточенні. Tauri запускає Python backend локально. Desktop-ярлик для цього
проєкту використовує перевірене локальне середовище Python 3.12 (із fallback
на `JARVIS/.venv`), тому працюють повний FAISS semantic search і BGE
reranking, а не лише lexical mode. Backend слухає тільки `127.0.0.1`,
використовує одноразовий IPC token і не відкриває мережевий server назовні.
Щоб зупинити застосунок, достатньо закрити desktop-вікно або натиснути
`Ctrl+C` у terminal, де запущено `npm run tauri dev`.

## Чати, архів і проєкти

- Кожен проєкт є розкривною папкою, а його діалоги показуються безпосередньо
  під ним. Стан розкриття зберігається локально.
- Меню `…` біля діалогу дозволяє перейменувати або архівувати його. Архівація
  не видаляє повідомлення чи citations.
- Відновлення доступне на повноекранній сторінці **Settings → Archived
  chats**. Архівований діалог доступний лише для читання, доки його не
  відновлено.
- Налаштування розділено на вертикальні вкладки **General**, **Model & RAG**,
  **Database**, **Developer chunking** і **Archived chats**; є пошук розділів.
- Одна й та сама папка не створює дублікат проєкту: JARVIS нормалізує її
  абсолютний шлях і повторно відкриває вже наявний проєкт. Папки з однаковою
  назвою, але різними шляхами, залишаються різними проєктами. Старі дублікати
  одного шляху показуються в sidebar один раз разом з усіма їхніми чатами;
  дані при цьому не видаляються автоматично.

## Локальна модель

JARVIS використовує лише локальний Ollama endpoint `127.0.0.1:11434` і
`qwen3:14b`. У **Settings** можна змінити лише назву вже завантаженої
локальної Ollama-моделі. API-ключі для генерації не використовуються, а
контекст документів не надсилається у хмарні LLM.

На ПК з 12 GB VRAM Qwen3-14B працює на GPU, а BGE reranker навмисно працює на
CPU. Це залишає відеопам'ять для генерації і не допускає конфлікту моделей;
ціною є трохи довший retrieval перед відповіддю.

За потреби `HF_TOKEN` у `local_config/constants.py` дозволяє швидше
завантажувати локальні embedding/reranker ваги з Hugging Face. Це не ключ
провайдера відповідей. `constants.py`, `.env`, індекси, завантажені файли й
caches не потрапляють у Git.

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
- Повний FAISS і BGE pipeline потребує локального Python 3.12 runtime;
  поточний installer на цьому ПК використовує підготовлене Python 3.12
  середовище; повністю self-contained Python sidecar ще не зібраний.

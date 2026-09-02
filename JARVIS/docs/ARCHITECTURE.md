# Архітектура JARVIS Desktop RAG

```text
Tauri 2 + React desktop
        ↓ authenticated loopback HTTP / WebSocket
FastAPI sidecar на 127.0.0.1 і випадковому порту
        ↓
incremental sync активного проєкту
        ↓
Classic / Developer / Mixed chunking
        ↓
Google Sheets: Files + Chunks_Current + Chunks_History
        ↓
text-free local FAISS cache + chunk/document/representation maps
        ↓
early corpus filter → semantic candidates → Sheets batch fetch
        ↓
candidate BM25 → BGE reranking → evidence gate
        ↓
local Qwen3 або Evidence only → grounded JSON → citations
```

## Desktop і backend

Tauri запускає один локальний Python sidecar. Backend сам обирає вільний
loopback-порт і отримує одноразовий IPC token; кожен HTTP та WebSocket запит
desktop-клієнта має містити цей token. Публічного HTTP listener, Telegram,
довільного shell-виконання або tool registry у фінальній версії немає.

Для Windows launcher спочатку використовує Python 3.12 з `.venv312`. Це
усуває нестабільність native FAISS/Torch на Python 3.14. Якщо `.venv312`
відсутня, launcher може використати сумісну `.venv`.

## Дані та ізоляція

SQLite зберігає локальні метадані: проєкти, aliases однакових абсолютних
шляхів, conversations, messages, documents, symbols та dependency graph.
Повний текст актуальних і попередніх chunks зберігається у Google Sheets:

- `Files` — SHA-256, size, mtime, revision та статус файлу;
- `Chunks_Current` — лише поточні chunks;
- `Chunks_History` — замінені, видалені або rejected версії;
- `Meta` — schema version і поточна revision.

Локально залишається тільки відновлюваний vector cache без текстів:
embeddings/FAISS та карти `chunk_id → Google row`, `chunk_id → document_id`,
`chunk_id → representation`. Service-account JSON, Spreadsheet ID та e-mail
власника знаходяться тільки в ignored `.env`/local state.

Якщо Google Sheets недоступний, JARVIS не відповідає за старим локальним
текстом, а повертає безпечну помилку синхронізації.

## Incremental ingestion

Перед кожним питанням `sync_project(project_id)` порівнює size і mtime, а
SHA-256 обчислює лише для потенційно змінених файлів. Незмінені файли не
парсяться повторно. Для зміненого або видаленого файлу попередні chunks
переходять у history, а звичайний retrieval бачить тільки нову current-версію.

Політика нарізки має три режими:

- `Classic` — очищений семантичний текст;
- `Developer` — структура коду, теги, коментарі та точні line ranges;
- `Mixed` — обидва представлення з детермінованим router за типом питання.

Секрети, `.env`, credentials, private keys, binaries і executables не
індексуються в жодному режимі.

## Scope-aware retrieval

`source_selector` може означати весь поточний проєкт, усі проєкти або один
імпортований файл. Retriever спочатку будує eligible document IDs. У cloud
route FAISS повертає лише IDs, після чого локальна text-free карта відсіює
чужі documents і representations **до** обмеження candidate set. Лише
відібрані rows читаються з Google Sheets, а потім проходять candidate BM25 і
BGE reranking.

Для локального fallback route FTS5, FAISS і graph expansion також отримують
той самий allowed document set до reciprocal-rank fusion.

Evidence gate не передає у модель слабкий контекст. Qwen3 отримує тільки
відібрані chunks, повертає структуровану grounded-відповідь, а citations
перевіряються за file/page/sheet/cell/line metadata. У режимі `Evidence only`
JARVIS показує retrieved passages без генерації.

Повну відтворювану схему див. у
[`WORKFLOW_GRAPH.md`](WORKFLOW_GRAPH.md).

# Стан реалізації

## Реалізовано

- Tauri 2 / React desktop із російською та англійською локалізацією;
- проєкти як розкривні папки з вкладеними чатами;
- сфокусована одноколонкова chat-area без file-preview і dependency-graph
  панелей;
- race-safe перемикання чатів і автоматичне відновлення локального backend
  після його перезапуску;
- нормалізація абсолютних шляхів і візуальне об'єднання legacy-дублів;
- rename, archive та restore conversations без втрати messages/citations;
- повноекранні Settings із розділами General, Model/RAG, Database,
  Chunking та Archived chats;
- FastAPI sidecar на випадковому loopback-порту з одноразовим IPC token;
- Python 3.12 desktop runtime, production Tauri EXE, MSI та NSIS installer;
- incremental SHA-256 sync перед кожним питанням;
- Classic / Developer / Mixed chunking та representation fingerprint;
- Google Sheets як source of truth для Files, current і history chunks;
- text-free local FAISS cache з document/row/representation maps;
- ранній corpus/file filter до candidate cutoff;
- FAISS semantic retrieval, candidate BM25, code graph expansion та BGE
  reranking;
- локальна Qwen3 через Ollama та безпечний режим Evidence only;
- evidence gate, grounded JSON contract, repair і перевірені citations;
- page, slide, sheet/cell та code line citations;
- parser/archive/security tests і desktop/API regression tests.

## Свідомо прибрано з фінального продукту

- Telegram bot і всі Telegram-команди;
- зовнішні finance/browser/email/calendar/system integrations;
- довільні agent tools, approvals, safe/autonomous modes та виконання команд;
- автоматичне редагування або запуск коду користувача.

Фінальний фокус — контрольований desktop RAG над локально вибраними файлами,
а не універсальний computer-use agent.

## Перевірений стан

- Python suite: `44 passed`;
- production frontend build: успішний;
- Tauri release EXE, MSI та NSIS setup: успішно зібрані;
- live Google Sheets snapshot для проєкту «Сашен сайт»:
  `975` current chunks, `975` vector/document mappings, `0` локальних
  SQLite text chunks;
- desktop запущений через актуальний ярлик без `Failed to fetch`.

## Поточні обмеження

- Google Sheets має API quotas та більшу latency, ніж спеціалізована vector DB;
- threshold evidence gate відкалібрований на навчальному corpus і потребує
  ширшого eval set;
- OCR, зображення, аудіо й відео не мають production ingestion pipeline;
- великі репозиторії синхронізуються перед питанням, а не окремим scheduler;
- локальна Qwen3 залежить від доступності Ollama і ресурсів конкретного ПК;
- JARVIS аналізує код і дає citations, але навмисно не змінює файли.

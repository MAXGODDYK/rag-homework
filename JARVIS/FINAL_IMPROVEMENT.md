# Final Technical Improvement — Scope-aware RAG retrieval

## What was improved

Я виправив реальну слабку точку JARVIS: selector конкретного файлу існував у
desktop UI, але раніше міг обмежувати результати вже після побудови global
candidate set. За малого `candidate_k` сильний chunk з іншого файлу займав
місце потрібного evidence, потім відкидався, і відповідь для вибраного файлу
ставала порожньою.

Тепер `project/file scope` застосовується **до candidate cutoff**. Для Google
Sheets route це забезпечує локальна text-free карта
`chunk_id → document_id`: FAISS може знайти глобальні vector IDs, але чужі
documents відсіюються до вибору top candidates і до завантаження тексту.

## Why this was needed

Користувач обирає конкретний файл, щоб отримати відповідь саме з договору,
лекції, таблиці або code module. Пізня фільтрація створювала хибне відчуття
контролю: UI показував вибраний corpus, а ranking усе ще конкурував з усім
проєктом. Для RAG це не косметична помилка, а порушення grounding contract.

## What changed technically

- Retriever спочатку обчислює eligible documents за `user_id`, `project_id`
  і `source_selector`.
- Vector manifest тепер зберігає text-free maps для `document_id`, Google row
  та `representation` кожного `chunk_id`.
- Cloud FAISS search переглядає IDs індексу, застосовує document і
  representation filters, і лише потім обрізає список до `candidate_k`.
- Текст читається з `Chunks_Current` Google Sheets тільки batch-запитом для
  дозволеного candidate set.
- Candidate BM25 і BGE reranking працюють лише з дозволеним scope.
- Local fallback route так само передає allowed IDs у FTS5, FAISS, graph
  expansion та reciprocal-rank fusion.
- Неповна або застаріла document map вважається помилкою синхронізації:
  JARVIS не відповідає за stale/local text.
- Evidence gate повертає чесний fallback, якщо релевантних доказів немає.

## Before / after behavior

### Case 1 — конкретний файл і small candidate set

```yaml
Before:
  Question: "semantic only query"
  Selected file: selected.md
  candidate_k: 1
  Global vector top-1: other.md / chunk_b
  System behavior: chunk_b займав candidate set, потім відкидався;
    selected.md не отримував evidence.

After:
  Question: "semantic only query"
  Selected file: selected.md
  candidate_k: 1
  System behavior: chunk_b відсіюється document map до cutoff;
    повертається selected.md / chunk_a з правильною citation.
```

### Case 2 — питання поза corpus

```yaml
Before:
  Question: "What is the capital of France?"
  System behavior: модель могла дати правдоподібну відповідь зі своїх знань,
    хоча у вибраних файлах не було evidence.

After:
  Question: "What is the capital of France?"
  System behavior: evidence gate повертає honest fallback без вигаданих
    citations.
```

### Case 3 — Google Sheets недоступний

```yaml
Before:
  System behavior: система могла спробувати використати локальний застарілий
    текстовий cache.

After:
  System behavior: JARVIS повертає безпечну sync error і не генерує відповідь
    за stale context.
```

## Result

Я додав regression test, де global semantic ranking навмисно ставить чужий
`chunk_b` вище за `chunk_a` з вибраного `selected.md`. Після зміни при
`candidate_k=1` повертається тільки `chunk_a`.

Повна локальна перевірка: `41 passed`. Додатково виконано live sync проєкту
«Сашен сайт»: `975` current chunks, `975` document mappings, `975` Google row
mappings і `0` локальних SQLite text chunks. Це підтверджує, що cloud route
має повну scope map і не тримає постійну текстову базу на ПК.

## Remaining limitations

- Selector підтримує один file path, поточний project або всі projects;
  довільні набори tags/document types ще не реалізовані.
- Evidence threshold обрано на невеликому навчальному corpus і треба
  калібрувати на ширшому eval set.
- Google Sheets зручний для прозорої демонстрації, але поступається
  спеціалізованій vector DB за latency та масштабом.
- OCR, image/audio/video ingestion залишаються наступним етапом.
- JARVIS аналізує код у Developer/Mixed mode, але не змінює і не запускає
  файли — це свідоме обмеження безпеки.

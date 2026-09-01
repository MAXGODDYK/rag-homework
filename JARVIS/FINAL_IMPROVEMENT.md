# Final Technical Improvement — Scope-aware RAG retrieval

## What was improved

Я виправив реальну слабку точку JARVIS: selector конкретного файлу існував у
desktop UI, але обмежував результати тільки після побудови global candidate
set. Тобто застосунок міг спочатку витратити `candidate-k` на chunks з інших
файлів, а вже потім відкинути їх. У результаті для вибраного файлу відповідь
могла бути порожньою або містити менше релевантних доказів.

Тепер metadata filtering виконується на початку pipeline. Обраний project або
file визначає дозволений набір documents і chunks **до** FTS5, FAISS,
symbol/graph expansion та BGE reranking.

## Why this was needed

У desktop RAG користувач обирає файл саме тому, що хоче отримати відповідь з
нього, наприклад із конкретного договору, лекції або модуля коду. Пізня
фільтрація створювала хибне відчуття контролю: UI показував вибраний файл, але
ranking усе ще конкурував з усім проєктом.

## What changed technically

- Додано раннє обчислення eligible documents за `user_id`, `project_id` і
  `source_selector`.
- Lexical FTS5 query отримує тільки allowed chunk IDs.
- Для FAISS отримуються vector hits проєкту, але metadata filter
  застосовується до присвоєння RRF ranks; тому чужий top-1 не витісняє chunk
  з обраного файлу.
- Graph expansion та BGE reranking працюють лише з allowed documents.
- Desktop UI має зрозумілий selector: current project, all projects або
  конкретний файл. Відкриття файлу автоматично обирає його як corpus.
- JARVIS переведено у desktop RAG-only режим: прибрано Telegram, agent tools,
  external integrations, approvals та UI для виконання команд.
- Додано evidence gate і extractive mode: за low score повертається чесний
  fallback, а без LLM показуються retrieved passages з citations.

## Before / after behavior

### Case 1 — конкретний файл і small candidate set

```yaml
Before:
  Question: "semantic only query"
  Selected file: selected.md
  candidate_k: 1
  Global vector top-1: other.md / chunk_b
  System behavior: "other.md" потрапляв у candidate set першим,
    після пізньої file filter відкидався, а selected.md не мав результату.

After:
  Question: "semantic only query"
  Selected file: selected.md
  candidate_k: 1
  System behavior: selected.md / chunk_a фільтрується як eligible до ranking,
    отримує RRF rank і повертається з citation на selected.md.
```

### Case 2 — питання поза corpus

```yaml
Before:
  Question: "What is the capital of France?"
  System behavior: загальний agent міг використати model knowledge,
    хоча запит не стосувався завантажених файлів.

After:
  Question: "What is the capital of France?"
  System behavior: evidence gate повертає fallback без citations,
    якщо найкращий BGE score нижчий за 0.005.
```

### Case 3 — немає налаштованого provider

```yaml
Before:
  System behavior: desktop agent завершувався помилкою,
    якщо жоден LLM provider не був available.

After:
  System behavior: Evidence only показує top retrieved passages
    та їхні page/cell/line citations; відповідь не вигадується.
```

## Result

Я перевірив нову поведінку автоматично. Набір тестів містить окремий case,
де global semantic ranking навмисно ставить чужий `chunk_b` вище за
`chunk_a` з `selected.md`; після зміни при `candidate-k=1` повертається лише
`chunk_a`. Також перевірені RAG-only API, відсутність tool/approval routes,
evidence gate, extractive fallback, parser-и документів, archive safety і
citations. Результат локального запуску: `24 passed`.

## Remaining limitations

- Selector підтримує один file path або весь project; групові metadata filters
  за tags/document type ще не реалізовані.
- Threshold `0.005` успадкований із малої навчальної бази та потребує
  калібрування на реальному corpus користувача.
- Відповідь від remote LLM залежить від її доступності та може бути повільною;
  extractive mode безпечніший, але менш зручний для читання.
- OCR, image/audio/video ingestion та background jobs залишаються майбутнім
  розширенням.

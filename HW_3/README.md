# HW3: BM25 hybrid retrieval, reranking та evaluation

HW3 продовжує semantic retrieval із HW2 та додає:

- metadata filtering за `source_file`;
- справжній BM25 lexical search;
- hybrid ranking semantic + BM25;
- порівняння BGE та Qwen3-4B cross-encoder reranking;
- автоматичний evaluation pipeline із фіксованою розміткою релевантності.

## Предметна область

**Student Personal Planning** — планування підготовки до іспитів,
режиму дня, пріоритетів, навчання та відпочинку студентів.
Knowledge base містить 3 українські вебстатті та 25 chunks,
підготовлені в HW1.

## Retrieval pipeline

```text
User query
    → optional source_file metadata filter
    → multilingual query embedding
    → cosine semantic scores
    → BM25 lexical scores
    → min-max normalization
    → 0.75 × semantic + 0.25 × BM25
    → top-10 hybrid candidates
    → selected cross-encoder reranking:
        ├── BGE reranker v2-m3
        └── Qwen3-Reranker-4B
    → final top-3
```

Embedding model:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
Chunks і query кодуються тією самою моделлю у 384-вимірні
`float32` вектори та L2-нормалізуються.

Доступні два rerankers:

- `BAAI/bge-reranker-v2-m3` — швидший multilingual default;
- `Qwen/Qwen3-Reranker-4B` — instruction-aware модель на 4B
  параметрів, що підтримує понад 100 мов.

Обидві моделі отримують пари `(query, chunk_text)` і повторно
сортують тільки десять найкращих hybrid candidates. Для Qwen
використовується англомовна instruction про пошук прямої відповіді
в українській knowledge base.

## BM25 hybrid search

Попередній експеримент HW3 використовував простий keyword overlap.
У фінальній версії він замінений на `BM25Okapi`, який враховує
частоту термів у chunk і рідкість термів у candidate corpus.

Semantic та BM25 scores нормалізуються окремо для кожного query:

```text
hybrid_score =
    0.75 × semantic_normalized
    + 0.25 × bm25_normalized
```

Якщо передано `--source-file`, metadata filter застосовується до
semantic і BM25 scoring. Доступні джерела:

| Source | Chunks |
|---|---:|
| `data/raw/exam_time_planning.html` | 18 |
| `data/raw/student_daily_routine.html` | 3 |
| `data/raw/student_time_management.html` | 4 |

## Структура

```text
HW_3/
├── data/
│   ├── raw/
│   ├── processed/
│   │   ├── normalized_documents.jsonl
│   │   └── chunks.jsonl
│   └── evaluation/
│       └── retrieval_eval.jsonl
├── index/
│   ├── embeddings.npy
│   ├── faiss.index
│   └── manifest.json
├── outputs/
│   ├── baseline_retrieval_examples.md
│   ├── retrieval_comparison.md
│   ├── retrieval_evaluation.json
│   └── retrieval_examples.md
├── scripts/
│   ├── build_index.py
│   ├── evaluate_retrieval.py
│   ├── prepare_knowledge_base.py
│   ├── retrieval.py
│   └── retrieval_improved.py
├── README.md
└── requirements.txt
```

`retrieval.py` залишається незмінним semantic baseline із HW2.
`retrieval_improved.py` містить reusable retrieval pipeline та CLI.
`evaluate_retrieval.py` запускає три системи на однаковій розмітці.

## Встановлення

Команди PowerShell із каталогу `HW_3`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\prepare_knowledge_base.py
.\.venv\Scripts\python.exe .\scripts\build_index.py
```

Перший запуск завантажує публічні моделі з Hugging Face.
`BAAI/bge-reranker-v2-m3` займає приблизно 2.29 GB.
BF16 weights `Qwen/Qwen3-Reranker-4B` потребують приблизно 8 GB
дискового простору та близько 9 GB RAM під час CPU inference.
Попередження про відсутній `HF_TOKEN` або Windows symlinks не є
помилкою і не впливає на ranking.

Якщо PowerShell некоректно показує українські символи:

```powershell
chcp 65001
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## Запуск retrieval

```powershell
.\.venv\Scripts\python.exe .\scripts\retrieval_improved.py `
    "Чи варто робити перерви під час підготовки до іспитів?" `
    --top-k 3 `
    --candidate-k 10 `
    --source-file "data/raw/exam_time_planning.html" `
    --reranker-model bge
```

Параметри:

- `query` — обов'язкове непорожнє питання;
- `--top-k` — кількість фінальних результатів, стандартно 3;
- `--candidate-k` — кількість hybrid candidates для reranker,
  стандартно 10 і не менше `top-k`;
- `--source-file` — опціональний metadata filter;
- `--reranker-model` — `bge` (default) або `qwen3-4b`.

Запуск важчого Qwen3-4B:

```powershell
.\.venv\Scripts\python.exe .\scripts\retrieval_improved.py `
    "Як скласти план підготовки до іспиту?" `
    --top-k 3 `
    --candidate-k 10 `
    --reranker-model qwen3-4b
```

CLI показує три окремі ranking:

```text
=============== SEMANTIC BASELINE ===============
=============== BM25 HYBRID ===============
=============== BGE/QWEN3-4B RERANKING ===============
```

## Evaluation

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_retrieval.py
```

Evaluation dataset містить 8 фіксованих українських queries та
списки relevant chunk IDs. Розмітка перевіряється до запуску:
query IDs мають бути унікальними, а всі relevant IDs — існувати
у поточному `chunks.jsonl`.

Для чесного порівняння headline-метрики рахуються без metadata
filter на однакових 25 chunks:

- `HitRate@1` — частка queries із релевантним top-1;
- `HitRate@3` — частка queries із хоча б одним релевантним top-3;
- `Recall@3` — частка знайдених relevant chunks;
- `MRR@3` — середнє обернене місце першого релевантного chunk.

Отримані результати:

| System | HitRate@1 | HitRate@3 | Recall@3 | MRR@3 | Mean latency |
|---|---:|---:|---:|---:|---:|
| Semantic baseline | 0.375 | 0.625 | 0.500 | 0.500 | 11.6 ms |
| Semantic + BM25 | 0.500 | 0.750 | 0.573 | 0.604 | 11.8 ms |
| Semantic + BM25 + BGE | 0.750 | 0.750 | 0.594 | 0.750 | 2062.7 ms |
| Semantic + BM25 + Qwen3-4B | 0.750 | 0.875 | 0.646 | 0.812 | 28094.3 ms |

На цьому наборі BM25 покращив усі retrieval-метрики відносно
semantic baseline. BGE reranking підвищив `HitRate@1` із `0.375`
до `0.750` та `MRR@3` із `0.500` до `0.750`.

Qwen3-4B зберіг такий самий `HitRate@1`, але підвищив
`HitRate@3` до `0.875`, `Recall@3` до `0.646` і `MRR@3`
до `0.812`. На CPU він працював приблизно у 14 разів повільніше
за BGE: 28.1 секунди проти 2.1 секунди на query. Тому BGE
залишається практичним default, а Qwen3-4B — quality-oriented
експериментом.

Evaluation також окремо підтверджує, що metadata filtering
звужує search space до 3–18 chunks і не повертає результати
з іншого source.

Повний per-query ranking та аналіз помилок:
`outputs/retrieval_comparison.md`. Машиночитані результати:
`outputs/retrieval_evaluation.json`.

## Обмеження

- evaluation містить лише 8 вручну розмічених queries;
- BM25 не виконує stemming українських словоформ;
- min-max scores не можна порівнювати між різними queries;
- BGE повільніший за baseline, а Qwen3-4B на CPU потребує
  приблизно 28 секунд на один query;
- `source_file` задається користувачем, автоматичного routing немає;
- score threshold, fallback і навчання reranker не реалізовані.

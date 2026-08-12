# Evaluation semantic, BM25, BGE та Qwen3-4B reranking

## Конфігурація

- Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- BGE reranker: `BAAI/bge-reranker-v2-m3`
- Qwen reranker: `Qwen/Qwen3-Reranker-4B`
- Hybrid formula: `0.75 × semantic_normalized + 0.25 × bm25_normalized`
- Corpus: 25 chunks; queries: 8; top-k: 3; candidate-k: 10

Розмітка релевантності створена вручну до запуску evaluation. Основні метрики всіх чотирьох систем рахуються без metadata filter на однаковому corpus із 25 chunks. Час завантаження моделей не входить у latency; перед вимірюванням виконано warm-up.

## Зведені метрики

| System | HitRate@1 | HitRate@3 | Recall@3 | MRR@3 | Mean latency, ms | P95 latency, ms |
|---|---:|---:|---:|---:|---:|---:|
| Semantic baseline | 0.375 | 0.625 | 0.500 | 0.500 | 11.6 | 13.9 |
| Semantic + BM25 | 0.500 | 0.750 | 0.573 | 0.604 | 11.8 | 14.7 |
| Semantic + BM25 + BGE | 0.750 | 0.750 | 0.594 | 0.750 | 2062.7 | 2136.3 |
| Semantic + BM25 + Qwen3-4B | 0.750 | 0.875 | 0.646 | 0.812 | 28094.3 | 28734.2 |

## Metadata filtering

| Query | Expected source | Candidates | Усі top-3 відповідають filter |
|---|---|---:|---|
| `q01` | `data/raw/exam_time_planning.html` | 18 | так |
| `q02` | `data/raw/exam_time_planning.html` | 18 | так |
| `q03` | `data/raw/student_daily_routine.html` | 3 | так |
| `q04` | `data/raw/student_time_management.html` | 4 | так |
| `q05` | `data/raw/student_daily_routine.html` | 3 | так |
| `q06` | `data/raw/exam_time_planning.html` | 18 | так |
| `q07` | `data/raw/exam_time_planning.html` | 18 | так |
| `q08` | `data/raw/exam_time_planning.html` | 18 | так |

## Перший релевантний результат

| Query | Semantic | Hybrid | BGE | Qwen3-4B |
|---|---:|---:|---:|---:|
| `q01` | 2 | 1 | 1 | 1 |
| `q02` | 2 | 2 | 1 | 1 |
| `q03` | 1 | 1 | 1 | 1 |
| `q04` | — | — | — | — |
| `q05` | 1 | 1 | 1 | 1 |
| `q06` | 1 | 1 | 1 | 1 |
| `q07` | — | 3 | 1 | 1 |
| `q08` | — | — | — | 2 |

## Детальні top-3

### q01: Як скласти реалістичний план підготовки до іспиту?

Relevant: `exam_time_planning_chunk_011`, `exam_time_planning_chunk_012`, `exam_time_planning_chunk_013`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `exam_time_planning_chunk_015` | 0.6944 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 2 | `exam_time_planning_chunk_011` | 0.6860 | так | `data/raw/exam_time_planning.html` |
| Semantic baseline | 3 | `exam_time_planning_chunk_012` | 0.6809 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 1 | `exam_time_planning_chunk_011` | 0.9836 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 2 | `exam_time_planning_chunk_015` | 0.7775 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 3 | `exam_time_planning_chunk_012` | 0.7487 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 1 | `exam_time_planning_chunk_011` | 0.6084 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 2 | `exam_time_planning_chunk_014` | 0.5660 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_018` | 0.5488 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `exam_time_planning_chunk_012` | 0.9526 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_011` | 0.9497 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_014` | 0.9149 | ні | `data/raw/exam_time_planning.html` |

### q02: У який час доби найкраще вчитися?

Relevant: `exam_time_planning_chunk_002`, `exam_time_planning_chunk_003`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `exam_time_planning_chunk_008` | 0.7204 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 2 | `exam_time_planning_chunk_003` | 0.6912 | так | `data/raw/exam_time_planning.html` |
| Semantic baseline | 3 | `exam_time_planning_chunk_002` | 0.6754 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 1 | `exam_time_planning_chunk_008` | 1.0000 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 2 | `exam_time_planning_chunk_003` | 0.7439 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 3 | `exam_time_planning_chunk_002` | 0.7125 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 1 | `exam_time_planning_chunk_002` | 0.7165 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 2 | `exam_time_planning_chunk_008` | 0.5305 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_003` | 0.5224 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `exam_time_planning_chunk_002` | 0.9707 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_004` | 0.5927 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_003` | 0.5000 | так | `data/raw/exam_time_planning.html` |

### q03: Як розставити пріоритети між терміновими та важливими справами?

Relevant: `student_daily_routine_chunk_001`, `student_daily_routine_chunk_002`, `student_time_management_chunk_002`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `student_daily_routine_chunk_001` | 0.5574 | так | `data/raw/student_daily_routine.html` |
| Semantic baseline | 2 | `student_daily_routine_chunk_002` | 0.5405 | так | `data/raw/student_daily_routine.html` |
| Semantic baseline | 3 | `student_time_management_chunk_002` | 0.5333 | так | `data/raw/student_time_management.html` |
| Semantic + BM25 | 1 | `student_time_management_chunk_002` | 0.9198 | так | `data/raw/student_time_management.html` |
| Semantic + BM25 | 2 | `student_daily_routine_chunk_001` | 0.7500 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 | 3 | `student_daily_routine_chunk_002` | 0.6939 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 1 | `student_daily_routine_chunk_002` | 0.5374 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 2 | `student_daily_routine_chunk_001` | 0.5156 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 3 | `student_time_management_chunk_002` | 0.5050 | так | `data/raw/student_time_management.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `student_daily_routine_chunk_002` | 0.9466 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `student_daily_routine_chunk_001` | 0.7186 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `student_time_management_chunk_002` | 0.5312 | так | `data/raw/student_time_management.html` |

### q04: Що робити, якщо я постійно відкладаю навчання?

Relevant: `exam_time_planning_chunk_018`, `student_time_management_chunk_002`, `student_time_management_chunk_003`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `exam_time_planning_chunk_004` | 0.6213 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 2 | `exam_time_planning_chunk_016` | 0.5969 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 3 | `exam_time_planning_chunk_015` | 0.5937 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 1 | `exam_time_planning_chunk_004` | 0.9503 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 2 | `exam_time_planning_chunk_016` | 0.8847 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 3 | `exam_time_planning_chunk_017` | 0.8703 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 1 | `exam_time_planning_chunk_016` | 0.5047 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 2 | `exam_time_planning_chunk_009` | 0.5041 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_017` | 0.5025 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `exam_time_planning_chunk_017` | 0.9649 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_016` | 0.8808 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_009` | 0.8081 | ні | `data/raw/exam_time_planning.html` |

### q05: Як правильно організувати режим дня студента?

Relevant: `student_daily_routine_chunk_001`, `student_daily_routine_chunk_002`, `student_daily_routine_chunk_003`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `student_daily_routine_chunk_002` | 0.8649 | так | `data/raw/student_daily_routine.html` |
| Semantic baseline | 2 | `student_time_management_chunk_001` | 0.7094 | ні | `data/raw/student_time_management.html` |
| Semantic baseline | 3 | `student_daily_routine_chunk_003` | 0.6856 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 | 1 | `student_daily_routine_chunk_002` | 1.0000 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 | 2 | `student_daily_routine_chunk_001` | 0.6666 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 | 3 | `student_daily_routine_chunk_003` | 0.6546 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 1 | `student_daily_routine_chunk_001` | 0.7221 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 2 | `student_daily_routine_chunk_002` | 0.7176 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 3 | `student_daily_routine_chunk_003` | 0.6633 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `student_daily_routine_chunk_002` | 0.9897 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `student_daily_routine_chunk_003` | 0.9579 | так | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `student_daily_routine_chunk_001` | 0.9497 | так | `data/raw/student_daily_routine.html` |

### q06: Як поєднати навчання, відпочинок і сон без перевантаження?

Relevant: `exam_time_planning_chunk_004`, `exam_time_planning_chunk_005`, `student_time_management_chunk_004`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `exam_time_planning_chunk_005` | 0.7363 | так | `data/raw/exam_time_planning.html` |
| Semantic baseline | 2 | `exam_time_planning_chunk_004` | 0.7270 | так | `data/raw/exam_time_planning.html` |
| Semantic baseline | 3 | `exam_time_planning_chunk_006` | 0.7217 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 1 | `exam_time_planning_chunk_004` | 0.9716 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 2 | `exam_time_planning_chunk_005` | 0.8863 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 3 | `exam_time_planning_chunk_006` | 0.8556 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 1 | `exam_time_planning_chunk_004` | 0.5508 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 2 | `exam_time_planning_chunk_005` | 0.5439 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_003` | 0.5315 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `exam_time_planning_chunk_004` | 0.9914 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_006` | 0.9897 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_003` | 0.9868 | ні | `data/raw/exam_time_planning.html` |

### q07: Чи варто робити перерви під час підготовки до іспитів?

Relevant: `exam_time_planning_chunk_005`, `exam_time_planning_chunk_006`, `exam_time_planning_chunk_007`, `student_time_management_chunk_003`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `exam_time_planning_chunk_015` | 0.7085 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 2 | `exam_time_planning_chunk_016` | 0.6995 | ні | `data/raw/exam_time_planning.html` |
| Semantic baseline | 3 | `exam_time_planning_chunk_004` | 0.6960 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 1 | `exam_time_planning_chunk_004` | 0.9204 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 2 | `exam_time_planning_chunk_017` | 0.8599 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 | 3 | `exam_time_planning_chunk_007` | 0.8465 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 1 | `exam_time_planning_chunk_005` | 0.7261 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 2 | `exam_time_planning_chunk_007` | 0.7118 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_006` | 0.7104 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `exam_time_planning_chunk_007` | 0.9966 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_005` | 0.9966 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_004` | 0.9951 | ні | `data/raw/exam_time_planning.html` |

### q08: Як контролювати виконання запланованих справ?

Relevant: `exam_time_planning_chunk_010`, `exam_time_planning_chunk_011`, `exam_time_planning_chunk_016`

| System | Rank | Chunk | Score | Relevant | Source |
|---|---:|---|---:|---|---|
| Semantic baseline | 1 | `student_time_management_chunk_002` | 0.5558 | ні | `data/raw/student_time_management.html` |
| Semantic baseline | 2 | `student_time_management_chunk_001` | 0.5517 | ні | `data/raw/student_time_management.html` |
| Semantic baseline | 3 | `student_time_management_chunk_003` | 0.5487 | ні | `data/raw/student_time_management.html` |
| Semantic + BM25 | 1 | `student_time_management_chunk_002` | 0.9929 | ні | `data/raw/student_time_management.html` |
| Semantic + BM25 | 2 | `student_time_management_chunk_001` | 0.9844 | ні | `data/raw/student_time_management.html` |
| Semantic + BM25 | 3 | `student_daily_routine_chunk_002` | 0.9182 | ні | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 1 | `student_daily_routine_chunk_002` | 0.5028 | ні | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + BGE | 2 | `student_time_management_chunk_002` | 0.5012 | ні | `data/raw/student_time_management.html` |
| Semantic + BM25 + BGE | 3 | `exam_time_planning_chunk_001` | 0.5009 | ні | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 1 | `student_daily_routine_chunk_002` | 0.4688 | ні | `data/raw/student_daily_routine.html` |
| Semantic + BM25 + Qwen3-4B | 2 | `exam_time_planning_chunk_011` | 0.4688 | так | `data/raw/exam_time_planning.html` |
| Semantic + BM25 + Qwen3-4B | 3 | `exam_time_planning_chunk_010` | 0.3208 | так | `data/raw/exam_time_planning.html` |

## Аналіз результатів

- Semantic + BM25 + BGE: перший релевантний chunk покращено для 3 queries (`q01`, `q02`, `q07`), без змін для 5 (`q03`, `q04`, `q05`, `q06`, `q08`), погіршено для 0 (немає).
  Зміна відносно semantic baseline: `HitRate@1 +0.375`, `MRR@3 +0.250`.
- Semantic + BM25 + Qwen3-4B: перший релевантний chunk покращено для 4 queries (`q01`, `q02`, `q07`, `q08`), без змін для 4 (`q03`, `q04`, `q05`, `q06`), погіршено для 0 (немає).
  Зміна відносно semantic baseline: `HitRate@1 +0.375`, `MRR@3 +0.312`.
- Qwen3-4B порівняно з BGE: `HitRate@1 +0.000`, `MRR@3 +0.062`, `mean latency +26031.6 ms`.

## Обмеження

- Evaluation містить лише 8 вручну розмічених queries, тому метрики мають високу дисперсію.
- BM25 не виконує stemming українських словоформ.
- Min-max scores нормалізуються окремо для кожного query і не порівнюються між різними queries.
- BGE і особливо Qwen3-4B значно повільніші та потребують більше пам'яті, ніж semantic і BM25 stages.
- Metadata source передається явно; автоматичний routing джерела не реалізований.

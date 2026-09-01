# HW8 — Підсумок observability metrics

## Що вимірювалося

Запуск містить 10 кейсів: RAG retrieval і confidence
gate, два live виклики NBU tool та один deterministic agent clarification.
RAG cases проходять справжній pipeline hybrid retrieval + BGE reranker +
`RagAnswerService`. Оскільки в цьому середовищі не налаштовано remote або
local LLM provider, generation layer використовує deterministic extractive
provider: він повертає процитований фрагмент із top-1 reranked chunk. Отже,
ці метрики перевіряють routing, retrieval, gate, tool handling і citation
validation, але не є benchmark-ом якості тексту live LLM.

## Метрики

- Усього cases: **10**
- Success rate: **9/10 = 90%**
- Partial success: **1/10**
- Failure rate: **0/10**
- Groundedness good: **10/10 = 100%**
- Середня end-to-end latency: **2357 ms**
- Середня retrieval latency для всіх cases: **2304 ms**
- Максимальна latency: **12038 ms**

## Evaluation modes

- `real_retrieval + deterministic_extractive_provider`: 7
- `live_nbu_tool`: 2
- `real_deterministic_agent`: 1

## Типи помилок

- `none`: 8
- `wrong_retrieval`: 1
- `evaluation_provider_language_mismatch`: 1

`eval_results.csv` є source of truth для кожної оцінки, а
`eval_traces.jsonl` містить ті самі records у machine-readable форматі.
Timestamps і NBU rates навмисно залежать від конкретного запуску.

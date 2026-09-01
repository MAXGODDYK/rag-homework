# Final Technical Improvement

Фінальний проєкт реалізовано у [JARVIS](JARVIS/README.md) — локальному
desktop RAG-застосунку. Я обрав **scope-aware metadata filtering** як одне
технічне покращення chatbot-а.

## What was improved

Вибраний file/project corpus тепер обмежує retrieval до FTS5, FAISS, graph
expansion і BGE reranking. Раніше file selector застосовувався після
формування кандидатів і міг не дати результат з вибраного файлу.

## Why this was needed

Користувач очікує, що обраний документ реально впливає на retrieval, а не
лише змінює вигляд UI. Рання фільтрація не дає chunks з інших файлів витіснити
релевантний chunk при малому `candidate-k`.

## What changed technically

- Додано resolved allowed document/chunk set перед усіма scoring stages.
- UI дозволяє обрати current project, all projects або точний file path.
- Додано evidence gate та extractive fallback з citations.
- JARVIS спрощено до desktop RAG-only: Telegram, tools і approvals прибрані.

## Result

Автотест відтворює два файли, де global vector top-1 належить іншому файлу.
Після зміни для `selected.md` і `candidate-k=1` повертається `chunk_a` саме
з `selected.md`. Повний test suite: `24 passed`.

## Before / after and remaining limitations

Повна документація з трьома сценаріями before/after, обмеженнями й деталями
реалізації: [JARVIS/FINAL_IMPROVEMENT.md](JARVIS/FINAL_IMPROVEMENT.md).

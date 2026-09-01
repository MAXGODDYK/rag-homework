# Пояснення до HW8

У HW8 я додав evaluation + observability layer до свого chatbot-а. Я не
обмежився прикладами в README: зафіксував 10 test questions у JSON до
запуску, написав runner та зберіг результати у CSV і JSONL.

Набір покриває прості retrieval питання, multi-document planning, складний
case про прокрастинацію, English query, два безпечні fallback, два живі
read-only виклики НБУ та clarification route агентa. Кожний рядок CSV містить
усі потрібні поля: question, expected behavior, answer, chunks/sources,
route, tools, success, groundedness, quality, latency, errors і notes.

RAG cases дійсно запускають hybrid retrieval + BGE reranking + confidence
gate, а NBU cases звертаються до офіційного API. У цьому checkout не
налаштовано live LLM keys, тому я не заявляю, що виміряв якість OpenAI,
FreeModel або Qwen. Замість цього використано локальний deterministic
extractive provider, який перевіряє реальний prompt/citation contract і
робить запуск відтворюваним. Це обмеження окремо вказано в quality report.

`outputs/eval_summary.md` містить розраховані observability metrics, а
`outputs/quality_report.md` — короткий аналіз сильних сторін, обмежень,
трьох головних проблем і наступних кроків.

Фінальна автоматична перевірка: `73 passed`; у live evaluation отримано
`90%` success rate і `100%` groundedness-good rate. Один складний retrieval
case позначено partial, а English extractive response має окремо зафіксоване
обмеження мови, тому результати не прикрашають фактичну поведінку.

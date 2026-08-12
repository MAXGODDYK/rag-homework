# Пояснення до домашнього завдання №5

## Посилання

- HW5: https://github.com/MAXGODDYK/rag-homework/tree/HW_5/HW_5
- Pull request: https://github.com/MAXGODDYK/rag-homework/pull/2

У HW5 я не змінював retrieval та grounded generation із HW4, а
додав один зовнішній read-only tool — `get_nbu_exchange_rate`.
Він отримує поточний або історичний офіційний курс через API
Національного банку України та може перерахувати суму у гривні.
Окремий API key і confirmation не потрібні.

## Архітектура

```text
question або /rate
→ lightweight currency prefilter
→ strict LLM decision або direct call
→ Pydantic input validation
→ allowlisted tool registry
→ fixed NBU HTTPS endpoint
→ NBU response validation
→ Decimal calculation
→ deterministic multilingual answer
```

Router має тільки два дозволені рішення: `rag` або
`get_nbu_exchange_rate`. Він не може передати довільну функцію,
URL, SQL чи extra fields. Якщо JSON неправильний, є одна
repair-спроба; після другої помилки tool не викликається.

LLM використовується тільки для decision та extraction arguments.
Курс, сума і фінальна відповідь не генеруються моделлю: дані
беруться з НБУ, перевіряються Python-кодом, а відповідь формується
детерміновано мовою питання.

## Безпека і validation

- ISO currency code: три латинські літери, uppercase;
- дата не може бути майбутньою;
- amount: від `0.01` до `1000000`;
- unknown fields заборонені;
- endpoint і timeout `10 s` зафіксовані в коді;
- перевіряються HTTP status, JSON array, поля, код, додатний rate
  та формат effective date;
- сума розраховується через `Decimal`;
- timeout/malformed/HTTP errors перетворюються на безпечні помилки;
- invalid `US` зупиняється до HTTP request.

## Live results

11 серпня 2026 року успішно виконані чотири реальні NBU calls:

| Сценарій | Результат |
|---|---:|
| Current USD | 44.8305 UAH |
| 100 EUR | 5178.15 UAH |
| PLN на 2026-08-01 | 11.8975 UAH |
| 50 GBP | 3025.84 UAH |

Англійський GBP query окремо пройшов через FreeModel і local
Qwen router. Обидва повернули той самий allowlisted tool,
`GBP`, amount `50`, date `2026-08-11` і однаковий результат НБУ.
Local routing разом із завантаженням моделі зайняв 18.6 s.

Навчальне питання було відхилене currency prefilter і передане у
RAG без виклику router/NBU. Повні результати знаходяться в
`outputs/tool_examples.md`.

## Telegram

Додано `/rate`, natural-language currency routing, tool-режим
`/sources`, очищення RAG/tool state через `/reset` і status НБУ.
Bot token live-перевірено через Telegram `getMe`; application
успішно створила 9 handlers, включно з командами `rate`, `sources`
і `reset`. Unit integration використовує fake providers/NBU без
витрати API. Додатковий live handler run виконав `/rate EUR 100`
і natural English GBP question через реальні НБУ та FreeModel;
`/sources` повернув офіційне джерело НБУ.

## Verification

- усі Python-файли компілюються;
- `40 passed`, включно з повною HW4-регресією;
- preprocessing: 3 documents і 25 chunks;
- embeddings: `(25, 384)`, `float32`, L2-normalized;
- FAISS і manifest узгоджені з 25 chunks;
- secrets, `.venv`, caches та `local_state` ignored.

OpenAI не перевірявся live, тому що окремий `OPENAI_API_KEY` не
налаштований. Це не впливає на NBU tool; перевірені FreeModel і
local Qwen.

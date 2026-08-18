# Пояснення до домашнього завдання №6

## Посилання

- HW6: https://github.com/MAXGODDYK/rag-homework/tree/HW_6/HW_6
- Pull request: https://github.com/MAXGODDYK/rag-homework/pull/3

У HW6 я реалізував контрольований agentic workflow для персонального
планування студента. Його завдання — визначити, чи потрібен
користувачеві план підготовки до іспиту, розпорядок навчального дня,
обидва результати або уточнення запиту.

## Архітектура

```text
user goal
→ validation
→ deterministic route
→ mock tool action
→ observation
→ state update
→ next step або final answer
```

Реалізовано routes `exam_preparation`, `daily_routine`,
`combined_planning` і `clarification`. Routing працює за фіксованими
правилами українською, російською та англійською мовами без LLM.

## Tools і state

Workflow використовує два локальні read-only mock tools:

- `mock_get_exam_plan` повертає семиденний план підготовки;
- `mock_get_daily_routine` повертає шаблон дня зі сном і перервами.

State зберігає user goal, language, route, current step, tool calls,
observations, повну history, clarification flag і final answer.
Кожна action та observation додає окремий snapshot.

## Додаткова функціональність

Окрім мінімальних вимог, я додав `combined_planning`: workflow
послідовно викликає обидва tools, передає observations у state і лише
після другого кроку формує спільну відповідь. Це показує перехід
`action → observation → state update → next action`.

Agent flow також інтегровано в Telegram:

- `/plan <goal>` запускає локальний workflow;
- `/trace` показує виконані steps;
- `/reset` очищає останній agent state.

## Приклади і перевірка

`outputs/agent_flow_examples.md` містить п'ять реально згенерованих
прикладів із route, tools, observations, state після steps і final
answer. Є окремі приклади трьома мовами, combined route і
clarification без tool call.

Автотести перевіряють routing, порядок tools, state transitions,
validation, deterministic result, CLI, генерацію звіту, Telegram
handlers і повну регресію HW5. Agent workflow не використовує API,
тому його тести не витрачають ключі або зовнішні ліміти.

Фактичний результат автоматичної перевірки: `60 passed`.
Telegram token окремо перевірено через `getMe`; application успішно
зареєструвала дев'ять команд, включно з `plan` і `trace`.

## Обмеження

Keyword routing свідомо простий і не охоплює всі можливі синоніми.
Mock tools демонструють agentic orchestration, а не створюють
індивідуальну академічну рекомендацію.

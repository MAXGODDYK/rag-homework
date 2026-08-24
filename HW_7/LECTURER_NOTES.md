# Пояснення до HW7

У HW7 я переніс свій deterministic student-planning workflow із HW6 на
LangGraph. Мета роботи — показати state, nodes, edges та conditional routing
у framework, не змінюючи домен або правила маршрутизації.

`FrameworkAgentState` описано через `TypedDict`. Граф має п'ять nodes:
`validate_request`, `classify_request`, `run_exam_plan`,
`run_daily_routine` і `build_answer`. Після validation та classification
використовуються conditional edges. Для `combined_planning` є додаткове
розгалуження: після exam tool граф переходить до routine tool, а не до
фіналізації.

Три реально згенеровані трасування знаходяться в
`outputs/langgraph_examples.md`. У кожному є input, selected route, список
виконаних nodes, повний final state та відповідь. Вони покривають exam,
daily routine і combined routes.

Я залишив workflow локальним і детермінованим: LLM, API-ключі та зовнішні
сервіси не потрібні. У README додано порівняння custom flow із HW6 та
framework implementation, включно з trade-offs для невеликого сценарію.

Автоматична перевірка HW7 та успадкованого функціоналу завершилася з
результатом `70 passed`.

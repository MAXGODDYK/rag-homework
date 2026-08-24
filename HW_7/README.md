# HW7: перенесення student-planning workflow на LangGraph

У цій роботі я переніс контрольований workflow із HW6 на **LangGraph**.
Domain не змінював: workflow допомагає студенту отримати план підготовки
до іспиту, шаблон навчального дня, обидва результати або запит на уточнення.

HW7 є ізольованим продовженням HW6. Успадковані RAG, Telegram-бот і NBU
tool з попередніх робіт не змінювались; для цього завдання використовується
локальний LangGraph workflow без LLM, мережевих запитів чи API-ключів.

## Чому LangGraph

Я обрав LangGraph, оскільки він прямо описує workflow через state, nodes,
звичайні edges та conditional edges. Це дозволяє бачити структуру виконання
окремо від коду самих tools. Такий підхід особливо корисний, коли сценарій
має кілька маршрутів або виконує кілька дій послідовно.

## Схема workflow

```text
START
  → validate_request
  ├─ validation error ───────────────────────→ build_answer → END
  └─ valid → classify_request
       ├─ exam_preparation ─→ run_exam_plan ─┬→ build_answer → END
       │                                     └─ combined_planning
       │                                        → run_daily_routine → build_answer → END
       ├─ daily_routine ─────────────────────→ run_daily_routine → build_answer → END
       └─ clarification ─────────────────────→ build_answer → END
```

`classify_request` використовує той самий детермінований multilingual
keyword router, що і HW6. Якщо запит містить ознаки іспиту та режиму дня,
обирається `combined_planning`; tools виконуються у фіксованому порядку:
`mock_get_exam_plan` → `mock_get_daily_routine`.

## State

У `scripts/langgraph_flow.py` state визначено через `TypedDict`:

| Поле | Призначення |
|---|---|
| `user_question` | початкове або нормалізоване питання |
| `language` | визначена мова: `uk`, `ru` або `en` |
| `selected_route` | route після `classify_request` |
| `tool_result` | результати mock tools за ключами |
| `tool_calls`, `observations` | порядок викликів і їх результати |
| `executed_nodes` | фактична траса LangGraph nodes |
| `needs_clarification`, `validation_error` | безпечні стани без tool call |
| `final_answer` | детермінована фінальна відповідь |

## Nodes і conditional edges

| Node | Дія |
|---|---|
| `validate_request` | перевіряє порожнє питання та ліміт 1000 символів |
| `classify_request` | визначає route українською, російською або англійською |
| `run_exam_plan` | викликає `mock_get_exam_plan` |
| `run_daily_routine` | викликає `mock_get_daily_routine` |
| `build_answer` | будує фінальну відповідь або уточнення |

У графі є два conditional edges:

1. Після `validate_request` неправильний input переходить прямо до
   `build_answer`, без router і tools.
2. Після `classify_request` route обирає одну з трьох tool-гілок або
   `clarification`. Після `run_exam_plan` другий conditional edge вирішує,
   чи потрібно виконувати `run_daily_routine` для combined route.

## Запуск

Усі команди запускаються з кореневої папки репозиторію, де знаходиться
папка `HW_7`.

```powershell
py -3.14 -m venv .\HW_7\.venv
.\HW_7\.venv\Scripts\python.exe -m pip install -r .\HW_7\requirements.txt
```

Звичайний trace:

```powershell
.\HW_7\.venv\Scripts\python.exe `
    -m HW_7.scripts.langgraph_flow `
    "Як скласти план підготовки до іспиту?"
```

Повний final state у JSON:

```powershell
.\HW_7\.venv\Scripts\python.exe `
    -m HW_7.scripts.langgraph_flow `
    "Create an exam study plan that includes sleep and breaks." `
    --json
```

Відтворити три приклади для звіту:

```powershell
.\HW_7\.venv\Scripts\python.exe `
    -m HW_7.scripts.langgraph_flow `
    --generate-examples
```

## Три test examples

Реальні результати з route, виконаними nodes, final state та final answer
збережено у [outputs/langgraph_examples.md](outputs/langgraph_examples.md).

| Input | Route | Expected nodes |
|---|---|---|
| `Як скласти план підготовки до іспиту?` | `exam_preparation` | validate → classify → exam tool → answer |
| `Як організувати режим дня, сон і перерви?` | `daily_routine` | validate → classify → routine tool → answer |
| `Create an exam study plan that includes sleep and breaks.` | `combined_planning` | validate → classify → exam tool → routine tool → answer |

## Порівняння HW6 custom flow і LangGraph

| Аспект | Custom flow у HW6 | LangGraph у HW7 |
|---|---|---|
| Структура | порядок кроків захований у `if/elif` | nodes та edges описують workflow явно |
| Routing | звичайні умовні оператори | conditional edges з named routes |
| Multi-step route | вручну викликаються два tools | окремий conditional edge після першого tool |
| Trace | вручну створені snapshots | `executed_nodes` показує фактичний шлях графом |
| Обсяг коду | менше залежностей і boilerplate | більше описового коду для state та графа |
| Масштабування | зручно для 2–3 простих кроків | зручніше для нових branches, retries, паралельності |

Для цього невеликого deterministic workflow custom реалізація HW6 є
простішою. LangGraph додає деяку складність, але допомагає зробити
conditional routing і multi-step шлях перевірюваними та наочними. Тому
framework виправданий як підготовка до складніших workflow, хоча для двох
простих mock tools він не є обов'язковим.

## Тестування

```powershell
.\HW_7\.venv\Scripts\python.exe -m compileall -q .\HW_7\config .\HW_7\scripts .\HW_7\tests
.\HW_7\.venv\Scripts\python.exe -m pytest -q .\HW_7\tests
```

Тести покривають усі чотири routes, conditional edges, фіксований порядок
combined tools, відсутність tool calls для clarification та invalid input,
CLI JSON і створення рівно трьох трасувань.

Фактичний результат: `70 passed`. Torch показав 14 non-blocking
deprecation warnings для Python 3.14; вони не пов'язані з LangGraph workflow.

## Обмеження

- Router навмисно базується на keyword rules та не замінює LLM intent classification.
- Mock tools повертають фіксовані приклади, а не персональні рекомендації.
- LangGraph у цій роботі демонструє orchestration; RAG, Telegram і зовнішні
  API з HW5/HW6 не викликаються цим workflow.

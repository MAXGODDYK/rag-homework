# HW6: контрольований agentic workflow

## Посилання для перевірки

- HW6: https://github.com/MAXGODDYK/rag-homework/tree/HW_6/HW_6
- Pull request: https://github.com/MAXGODDYK/rag-homework/pull/3

У HW6 я продовжив chatbot із попередніх робіт і додав окремий
детермінований agentic workflow для персонального планування студента.
Routing не використовує LLM або зовнішні API: кожен route, перехід
стану та tool call можна відтворити й перевірити.

Успадковані grounded RAG, NBU tool та Telegram-команди HW5 залишилися
доступними без зміни їхньої поведінки.

## Domain area і use case

**Domain:** персональне планування студента.

**Use case:** студент формулює навчальну мету, а workflow визначає,
чи потрібен план підготовки до іспиту, шаблон розпорядку дня, обидва
результати послідовно або уточнення запиту.

## Схема workflow

```text
User goal
→ validation
→ language detection
→ deterministic router
   ├─ exam_preparation
   │  → mock_get_exam_plan
   │  → observation
   │  → state update
   │  → final answer
   ├─ daily_routine
   │  → mock_get_daily_routine
   │  → observation
   │  → state update
   │  → final answer
   ├─ combined_planning
   │  → mock_get_exam_plan
   │  → observation + state update
   │  → mock_get_daily_routine
   │  → observation + state update
   │  → combined final answer
   └─ clarification
      → clarification question without a tool call
```

Workflow завершується максимум після двох tool calls. Довільні tool
names і нескінченний agent loop відсутні.

## Routes

| Route | Умова | Наступна дія |
|---|---|---|
| `exam_preparation` | питання про іспит, тест або підготовку | `mock_get_exam_plan` |
| `daily_routine` | питання про режим, сон, відпочинок або перерви | `mock_get_daily_routine` |
| `combined_planning` | у запиті присутні обидва intents | обидва tools у фіксованому порядку |
| `clarification` | intent не визначено | уточнювальне питання без tool call |

Router підтримує українські, російські та англійські ключові слова.

## Mock tools

| Tool | Тип | Фіксований результат |
|---|---|---|
| `mock_get_exam_plan` | read-only mock | семиденний план підготовки |
| `mock_get_daily_routine` | read-only mock | розклад дня, 8 годин сну, блоки 50/10 |

Tools не читають файли, не викликають мережу та не змінюють зовнішній
стан. Для однакового input вони завжди повертають однаковий result.

## State

Публічний `AgentState`:

```json
{
  "user_goal": "...",
  "language": "uk | ru | en",
  "selected_route": "exam_preparation | daily_routine | combined_planning | clarification",
  "current_step": "completed",
  "tool_calls": [],
  "observations": [],
  "state_history": [],
  "needs_clarification": false,
  "final_answer": "..."
}
```

`state_history` фіксує validation, routing, кожну action, observation
і finalization. Snapshot містить номер step, route, tool name та
кількість накопичених tool calls і observations.

## Основні файли

```text
HW_6/
├── scripts/
│   ├── agent_flow.py
│   └── telegram_bot/
├── outputs/
│   └── agent_flow_examples.md
├── tests/
│   ├── test_agent_flow.py
│   └── test_telegram_handlers.py
├── LECTURER_NOTES.md
├── README.md
└── requirements.txt
```

## Встановлення

Усі команди виконуються з кореневої папки проєкту, де знаходиться
папка `HW_6`:

```powershell
py -3.14 -m venv .\HW_6\.venv
.\HW_6\.venv\Scripts\python.exe -m pip install `
    -r .\HW_6\requirements.txt
```

## CLI

Звичайний текстовий trace:

```powershell
.\HW_6\.venv\Scripts\python.exe `
    -m HW_6.scripts.agent_flow `
    "Як скласти план підготовки до іспиту?"
```

Machine-readable state:

```powershell
.\HW_6\.venv\Scripts\python.exe `
    -m HW_6.scripts.agent_flow `
    "Create an exam study plan with sleep and breaks." `
    --json
```

Відтворити звіт із п'ятьма прикладами:

```powershell
.\HW_6\.venv\Scripts\python.exe `
    -m HW_6.scripts.agent_flow `
    --generate-examples
```

Порожній goal і текст довший за 1000 символів завершуються безпечним
validation error до routing і tool calls.

## Telegram

Один раз створіть ignored-конфігурацію:

```powershell
Copy-Item `
    ".\HW_6\local_config\constants.example.py" `
    ".\HW_6\local_config\constants.py"
```

У `constants.py` заповніть `TELEGRAM_BOT_TOKEN`. Для `/plan` і
`/trace` provider key не потрібен; ключі FreeModel/OpenAI потрібні
тільки для успадкованих RAG-функцій.

Запуск:

```powershell
.\HW_6\.venv\Scripts\python.exe `
    -m HW_6.scripts.telegram_bot.bot
```

Нові команди:

- `/plan Як підготуватися до іспиту?` — виконати agent workflow;
- `/trace` — показати route, steps, tools і final state;
- `/sources` після `/plan` — пояснити, що використані mock tools;
- `/reset` — очистити RAG, NBU та agent result.

`/plan` використовує існуючий per-user rate limit. Зупинка polling —
`Ctrl+C` у тому самому вікні PowerShell. Одночасно має працювати лише
один bot process із цим token.

## Приклади

Повні трасування знаходяться в `outputs/agent_flow_examples.md`.

| № | Мова | Route | Tools |
|---:|---|---|---|
| 1 | українська | `exam_preparation` | exam plan |
| 2 | українська | `daily_routine` | daily routine |
| 3 | English | `combined_planning` | exam plan → daily routine |
| 4 | російська | `daily_routine` | daily routine |
| 5 | українська | `clarification` | none |

## Тестування

```powershell
.\HW_6\.venv\Scripts\python.exe -m compileall -q `
    .\HW_6\config .\HW_6\scripts .\HW_6\tests
.\HW_6\.venv\Scripts\python.exe -m pytest -q .\HW_6\tests
```

Тести перевіряють чотири routes, три мови, порядок двох tools,
state transitions, validation, deterministic output, CLI JSON,
генерацію звіту, Telegram `/plan`, `/trace`, `/reset`, rate limiting
і повну регресію HW5.

Фактичний результат: `60 passed`.

## Обмеження

- keyword routing не розуміє складні синоніми поза allowlist;
- mock results демонструють orchestration, а не персональну пораду;
- workflow не використовує історію попередніх запитів;
- `/plan` не замінює grounded RAG і не викликає реальні API;
- clarification потребує нового, точнішого запиту користувача.

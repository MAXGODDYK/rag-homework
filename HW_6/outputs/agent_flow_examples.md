# HW6 — Agent flow examples

Усі приклади згенеровано реальним deterministic workflow без LLM та API.

## 1. exam_preparation

**Question:** Як скласти план підготовки до іспиту?

**Route:** `exam_preparation`

**Tool called:** `mock_get_exam_plan`

**Observation:**

```json
[
  {
    "sequence": 1,
    "tool_name": "mock_get_exam_plan",
    "result": {
      "result_type": "mock",
      "duration_days": 7,
      "plan": [
        "День 1: визначити мету та перелік тем.",
        "День 2: повторити перший блок матеріалу.",
        "День 3: повторити другий блок матеріалу.",
        "День 4: виконати практичні завдання.",
        "День 5: пройти пробний тест.",
        "День 6: опрацювати помилки та слабкі теми.",
        "День 7: коротке повторення і повноцінний відпочинок."
      ]
    }
  }
]
```

**State after steps:**

```json
[
  {
    "step": 1,
    "phase": "validation",
    "current_step": "validated",
    "selected_route": null,
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "User goal пройшов validation",
    "tool_name": null
  },
  {
    "step": 2,
    "phase": "routing",
    "current_step": "routed",
    "selected_route": "exam_preparation",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Обрано route: exam_preparation",
    "tool_name": null
  },
  {
    "step": 3,
    "phase": "action",
    "current_step": "calling:mock_get_exam_plan",
    "selected_route": "exam_preparation",
    "tool_call_count": 1,
    "observation_count": 0,
    "message": "Виклик deterministic mock tool: mock_get_exam_plan",
    "tool_name": "mock_get_exam_plan"
  },
  {
    "step": 4,
    "phase": "observation",
    "current_step": "observed:mock_get_exam_plan",
    "selected_route": "exam_preparation",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Результат mock_get_exam_plan збережено в observations",
    "tool_name": "mock_get_exam_plan"
  },
  {
    "step": 5,
    "phase": "finalization",
    "current_step": "completed",
    "selected_route": "exam_preparation",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Final answer сформовано; workflow завершено",
    "tool_name": null
  }
]
```

**Final answer:**

План підготовки на 7 днів:
- День 1: визначити мету та перелік тем.
- День 2: повторити перший блок матеріалу.
- День 3: повторити другий блок матеріалу.
- День 4: виконати практичні завдання.
- День 5: пройти пробний тест.
- День 6: опрацювати помилки та слабкі теми.
- День 7: коротке повторення і повноцінний відпочинок.

## 2. daily_routine

**Question:** Як організувати режим дня, сон і перерви?

**Route:** `daily_routine`

**Tool called:** `mock_get_daily_routine`

**Observation:**

```json
[
  {
    "sequence": 1,
    "tool_name": "mock_get_daily_routine",
    "result": {
      "result_type": "mock",
      "sleep_hours": 8,
      "focus_block_minutes": 50,
      "break_minutes": 10,
      "schedule": [
        {
          "time": "08:00",
          "activity": "Підйом, сніданок і визначення пріоритетів"
        },
        {
          "time": "09:00",
          "activity": "Перша сфокусована навчальна сесія"
        },
        {
          "time": "09:50",
          "activity": "Перерва, рух і відпочинок від екрана"
        },
        {
          "time": "10:00",
          "activity": "Друга сесія: практика та перевірка знань"
        },
        {
          "time": "18:00",
          "activity": "Коротке підбиття підсумків і план на завтра"
        },
        {
          "time": "23:00",
          "activity": "Сон"
        }
      ]
    }
  }
]
```

**State after steps:**

```json
[
  {
    "step": 1,
    "phase": "validation",
    "current_step": "validated",
    "selected_route": null,
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "User goal пройшов validation",
    "tool_name": null
  },
  {
    "step": 2,
    "phase": "routing",
    "current_step": "routed",
    "selected_route": "daily_routine",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Обрано route: daily_routine",
    "tool_name": null
  },
  {
    "step": 3,
    "phase": "action",
    "current_step": "calling:mock_get_daily_routine",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 0,
    "message": "Виклик deterministic mock tool: mock_get_daily_routine",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 4,
    "phase": "observation",
    "current_step": "observed:mock_get_daily_routine",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Результат mock_get_daily_routine збережено в observations",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 5,
    "phase": "finalization",
    "current_step": "completed",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Final answer сформовано; workflow завершено",
    "tool_name": null
  }
]
```

**Final answer:**

Приклад збалансованого навчального дня:
- 08:00: Підйом, сніданок і визначення пріоритетів
- 09:00: Перша сфокусована навчальна сесія
- 09:50: Перерва, рух і відпочинок від екрана
- 10:00: Друга сесія: практика та перевірка знань
- 18:00: Коротке підбиття підсумків і план на завтра
- 23:00: Сон

## 3. combined_planning

**Question:** Create an exam study plan that includes sleep and breaks.

**Route:** `combined_planning`

**Tool called:** `mock_get_exam_plan`, `mock_get_daily_routine`

**Observation:**

```json
[
  {
    "sequence": 1,
    "tool_name": "mock_get_exam_plan",
    "result": {
      "result_type": "mock",
      "duration_days": 7,
      "plan": [
        "Day 1: define the goal and list the topics.",
        "Day 2: review the first material block.",
        "Day 3: review the second material block.",
        "Day 4: complete practice tasks.",
        "Day 5: take a mock test.",
        "Day 6: review mistakes and weak topics.",
        "Day 7: do a short review and get proper rest."
      ]
    }
  },
  {
    "sequence": 2,
    "tool_name": "mock_get_daily_routine",
    "result": {
      "result_type": "mock",
      "sleep_hours": 8,
      "focus_block_minutes": 50,
      "break_minutes": 10,
      "schedule": [
        {
          "time": "08:00",
          "activity": "Wake up, have breakfast, and set priorities"
        },
        {
          "time": "09:00",
          "activity": "First focused study session"
        },
        {
          "time": "09:50",
          "activity": "Take a break, move, and rest from the screen"
        },
        {
          "time": "10:00",
          "activity": "Second session: practice and knowledge check"
        },
        {
          "time": "18:00",
          "activity": "Brief review and plan for tomorrow"
        },
        {
          "time": "23:00",
          "activity": "Sleep"
        }
      ]
    }
  }
]
```

**State after steps:**

```json
[
  {
    "step": 1,
    "phase": "validation",
    "current_step": "validated",
    "selected_route": null,
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "User goal пройшов validation",
    "tool_name": null
  },
  {
    "step": 2,
    "phase": "routing",
    "current_step": "routed",
    "selected_route": "combined_planning",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Обрано route: combined_planning",
    "tool_name": null
  },
  {
    "step": 3,
    "phase": "action",
    "current_step": "calling:mock_get_exam_plan",
    "selected_route": "combined_planning",
    "tool_call_count": 1,
    "observation_count": 0,
    "message": "Виклик deterministic mock tool: mock_get_exam_plan",
    "tool_name": "mock_get_exam_plan"
  },
  {
    "step": 4,
    "phase": "observation",
    "current_step": "observed:mock_get_exam_plan",
    "selected_route": "combined_planning",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Результат mock_get_exam_plan збережено в observations",
    "tool_name": "mock_get_exam_plan"
  },
  {
    "step": 5,
    "phase": "action",
    "current_step": "calling:mock_get_daily_routine",
    "selected_route": "combined_planning",
    "tool_call_count": 2,
    "observation_count": 1,
    "message": "Виклик deterministic mock tool: mock_get_daily_routine",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 6,
    "phase": "observation",
    "current_step": "observed:mock_get_daily_routine",
    "selected_route": "combined_planning",
    "tool_call_count": 2,
    "observation_count": 2,
    "message": "Результат mock_get_daily_routine збережено в observations",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 7,
    "phase": "finalization",
    "current_step": "completed",
    "selected_route": "combined_planning",
    "tool_call_count": 2,
    "observation_count": 2,
    "message": "Final answer сформовано; workflow завершено",
    "tool_name": null
  }
]
```

**Final answer:**

Seven-day preparation plan:
- Day 1: define the goal and list the topics.
- Day 2: review the first material block.
- Day 3: review the second material block.
- Day 4: complete practice tasks.
- Day 5: take a mock test.
- Day 6: review mistakes and weak topics.
- Day 7: do a short review and get proper rest.

Example of a balanced study day:
- 08:00: Wake up, have breakfast, and set priorities
- 09:00: First focused study session
- 09:50: Take a break, move, and rest from the screen
- 10:00: Second session: practice and knowledge check
- 18:00: Brief review and plan for tomorrow
- 23:00: Sleep

## 4. daily_routine

**Question:** Как организовать режим дня и отдых между занятиями?

**Route:** `daily_routine`

**Tool called:** `mock_get_daily_routine`

**Observation:**

```json
[
  {
    "sequence": 1,
    "tool_name": "mock_get_daily_routine",
    "result": {
      "result_type": "mock",
      "sleep_hours": 8,
      "focus_block_minutes": 50,
      "break_minutes": 10,
      "schedule": [
        {
          "time": "08:00",
          "activity": "Подъём, завтрак и определение приоритетов"
        },
        {
          "time": "09:00",
          "activity": "Первая сфокусированная учебная сессия"
        },
        {
          "time": "09:50",
          "activity": "Перерыв, движение и отдых от экрана"
        },
        {
          "time": "10:00",
          "activity": "Вторая сессия: практика и проверка знаний"
        },
        {
          "time": "18:00",
          "activity": "Краткое подведение итогов и план на завтра"
        },
        {
          "time": "23:00",
          "activity": "Сон"
        }
      ]
    }
  }
]
```

**State after steps:**

```json
[
  {
    "step": 1,
    "phase": "validation",
    "current_step": "validated",
    "selected_route": null,
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "User goal пройшов validation",
    "tool_name": null
  },
  {
    "step": 2,
    "phase": "routing",
    "current_step": "routed",
    "selected_route": "daily_routine",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Обрано route: daily_routine",
    "tool_name": null
  },
  {
    "step": 3,
    "phase": "action",
    "current_step": "calling:mock_get_daily_routine",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 0,
    "message": "Виклик deterministic mock tool: mock_get_daily_routine",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 4,
    "phase": "observation",
    "current_step": "observed:mock_get_daily_routine",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Результат mock_get_daily_routine збережено в observations",
    "tool_name": "mock_get_daily_routine"
  },
  {
    "step": 5,
    "phase": "finalization",
    "current_step": "completed",
    "selected_route": "daily_routine",
    "tool_call_count": 1,
    "observation_count": 1,
    "message": "Final answer сформовано; workflow завершено",
    "tool_name": null
  }
]
```

**Final answer:**

Пример сбалансированного учебного дня:
- 08:00: Подъём, завтрак и определение приоритетов
- 09:00: Первая сфокусированная учебная сессия
- 09:50: Перерыв, движение и отдых от экрана
- 10:00: Вторая сессия: практика и проверка знаний
- 18:00: Краткое подведение итогов и план на завтра
- 23:00: Сон

## 5. clarification

**Question:** Розкажи щось корисне.

**Route:** `clarification`

**Tool called:** none

**Observation:**

```json
[]
```

**State after steps:**

```json
[
  {
    "step": 1,
    "phase": "validation",
    "current_step": "validated",
    "selected_route": null,
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "User goal пройшов validation",
    "tool_name": null
  },
  {
    "step": 2,
    "phase": "routing",
    "current_step": "routed",
    "selected_route": "clarification",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Обрано route: clarification",
    "tool_name": null
  },
  {
    "step": 3,
    "phase": "finalization",
    "current_step": "completed",
    "selected_route": "clarification",
    "tool_call_count": 0,
    "observation_count": 0,
    "message": "Final answer сформовано; workflow завершено",
    "tool_name": null
  }
]
```

**Final answer:**

Уточніть, будь ласка: вам потрібен план підготовки до іспиту, розпорядок навчального дня чи обидва варіанти?

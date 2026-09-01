# HW7 — LangGraph workflow examples

Усі приклади згенеровано локально через LangGraph без LLM та API.

## 1. exam_preparation

**Input question:** Як скласти план підготовки до іспиту?

**Selected route:** `exam_preparation`

**Executed nodes:** `validate_request` → `classify_request` → `run_exam_plan` → `build_answer`

**Final state:**

```json
{
  "user_question": "Як скласти план підготовки до іспиту?",
  "language": "uk",
  "selected_route": "exam_preparation",
  "tool_result": {
    "exam_plan": {
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
  },
  "tool_calls": [
    "mock_get_exam_plan"
  ],
  "observations": [
    {
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
  ],
  "executed_nodes": [
    "validate_request",
    "classify_request",
    "run_exam_plan",
    "build_answer"
  ],
  "needs_clarification": false,
  "validation_error": "",
  "final_answer": "План підготовки на 7 днів:\n- День 1: визначити мету та перелік тем.\n- День 2: повторити перший блок матеріалу.\n- День 3: повторити другий блок матеріалу.\n- День 4: виконати практичні завдання.\n- День 5: пройти пробний тест.\n- День 6: опрацювати помилки та слабкі теми.\n- День 7: коротке повторення і повноцінний відпочинок."
}
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

**Input question:** Як організувати режим дня, сон і перерви?

**Selected route:** `daily_routine`

**Executed nodes:** `validate_request` → `classify_request` → `run_daily_routine` → `build_answer`

**Final state:**

```json
{
  "user_question": "Як організувати режим дня, сон і перерви?",
  "language": "uk",
  "selected_route": "daily_routine",
  "tool_result": {
    "daily_routine": {
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
  },
  "tool_calls": [
    "mock_get_daily_routine"
  ],
  "observations": [
    {
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
  ],
  "executed_nodes": [
    "validate_request",
    "classify_request",
    "run_daily_routine",
    "build_answer"
  ],
  "needs_clarification": false,
  "validation_error": "",
  "final_answer": "Приклад збалансованого навчального дня:\n- 08:00: Підйом, сніданок і визначення пріоритетів\n- 09:00: Перша сфокусована навчальна сесія\n- 09:50: Перерва, рух і відпочинок від екрана\n- 10:00: Друга сесія: практика та перевірка знань\n- 18:00: Коротке підбиття підсумків і план на завтра\n- 23:00: Сон"
}
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

**Input question:** Create an exam study plan that includes sleep and breaks.

**Selected route:** `combined_planning`

**Executed nodes:** `validate_request` → `classify_request` → `run_exam_plan` → `run_daily_routine` → `build_answer`

**Final state:**

```json
{
  "user_question": "Create an exam study plan that includes sleep and breaks.",
  "language": "en",
  "selected_route": "combined_planning",
  "tool_result": {
    "exam_plan": {
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
    },
    "daily_routine": {
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
  },
  "tool_calls": [
    "mock_get_exam_plan",
    "mock_get_daily_routine"
  ],
  "observations": [
    {
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
  ],
  "executed_nodes": [
    "validate_request",
    "classify_request",
    "run_exam_plan",
    "run_daily_routine",
    "build_answer"
  ],
  "needs_clarification": false,
  "validation_error": "",
  "final_answer": "Seven-day preparation plan:\n- Day 1: define the goal and list the topics.\n- Day 2: review the first material block.\n- Day 3: review the second material block.\n- Day 4: complete practice tasks.\n- Day 5: take a mock test.\n- Day 6: review mistakes and weak topics.\n- Day 7: do a short review and get proper rest.\n\nExample of a balanced study day:\n- 08:00: Wake up, have breakfast, and set priorities\n- 09:00: First focused study session\n- 09:50: Take a break, move, and rest from the screen\n- 10:00: Second session: practice and knowledge check\n- 18:00: Brief review and plan for tomorrow\n- 23:00: Sleep"
}
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

# HW8 — Quality report

## Що тестувалося

Я запустив 10 навмисно різних питань через компоненти
student-planning chatbot-а: прямі knowledge-base питання, multi-document
planning, складний запит про прокрастинацію, English retrieval, два
out-of-domain питання, два live виклики офіційного курсу НБУ та clarification
route детермінованого agent-а. Повні observed outputs, retrieved chunks,
routes, citations, errors і latency збережені в `outputs/eval_results.csv`.

## Результати

Виміряний task success rate становить **90%**
(9/10), а groundedness-good
rate — **100%**. Live NBU tool cases
повернули нормалізовані офіційні дані та детермінований перерахунок. Два
out-of-domain питання дали `2` безпечні fallback responses
замість непідтверджених фактів. Середня RAG/fallback latency склала
**3292 ms**: це включає завантаження й виконання
multilingual embedding model та BGE reranking на CPU.

## Де система працює добре

Найсильніша властивість — bounded execution: прямі навчальні питання
зберігають retrieved chunk IDs, confidence gate не дозволяє відповідати, коли
corpus нерелевантний, а NBU integration використовує validated allowlisted
input замість числа, згенерованого LLM. Agent clarification case також
завершується без непотрібних retrieval і tool calls.

## Де система працює слабше

Складні та нечіткі retrieval cases показують, що top-ranked chunk не завжди
є chunk-ом, який найкраще відповідає очікуваному підпитанню. Extractive
evaluation provider показує це як `wrong_retrieval` або
`missing_expected_citation`; у цьому запуску таких cases **1**.
Результат корисний, але не вимірює якість реального remote або local LLM,
оскільки у відтворюваному запуску provider не налаштований.

## Три головні проблеми

1. **Нечіткі або multi-intent queries можуть повертати сусідню тему.**
   Поточна top-3 стратегія не має query rewriting або intent-specific metadata
   filter, тому семантично близький planning chunk може витісняти chunk про
   прокрастинацію чи пріоритети.
2. **Generation quality ще не спостерігається через live provider.**
   Deterministic extractive provider перевіряє JSON/citation contract, але не
   може показати справжні LLM hallucinations, переклад або synthesis кількох
   chunks.
3. **CPU reranking домінує в interactive latency.** BGE покращує relevance,
   але його вартість видно в observed RAG latency і користувач відчує її в
   Telegram для кожного питання.

## Наступні кроки

Наступним кроком я б додав intent-aware metadata filters і query rewriting
для неоднозначних питань, запустив той самий fixed eval set із налаштованими
FreeModel/OpenAI/local providers і записував citation validity окремо від
answer correctness, а також кешував або batch-ив reranker candidates, щоб
зменшити CPU latency. Збережені CSV і JSONL traces дозволяють порівнювати
before/after без зміни eval set.

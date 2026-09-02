# Повний workflow JARVIS

![Повне дерево JARVIS](../outputs/presentation/JARVIS_WORKFLOW.png)

Схема показує не лише генерацію відповіді, а весь шлях даних: incremental
sync, політику нарізки, Google Sheets як text storage, text-free FAISS cache,
ранню фільтрацію corpus, hybrid retrieval, BGE reranking, evidence gate,
локальну Qwen3 та перевірку citations.

Ключовий інваріант фінального покращення: обраний файл перетворюється на
набір `eligible document IDs` **до** обмеження candidate set. Для Google
Sheets це забезпечує локальна карта `chunk_id → document_id`, яка не містить
тексту. Тому чужий chunk не може витіснити evidence з вибраного файлу, а в
RAM завантажуються тільки кандидати.

Вихідні дані Graphviz збережені поруч у `outputs/presentation/JARVIS_WORKFLOW.dot`,
тому схему можна відтворити або змінити без ручного малювання.

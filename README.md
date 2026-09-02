# rag-homework
Домашние работы по курсу RAG

- `HW_1` — підготовка knowledge base, нормалізація та chunking;
- `HW_2` — multilingual embeddings, FAISS і top-k semantic retrieval.
- `HW_3` — metadata filtering, BM25, BGE/Qwen3-4B reranking і evaluation.
- `HW_4` — grounded RAG, confidence fallback, OpenAI/FreeModel/local
  Qwen, Telegram-бот і перевірка JSON/citations.
- `HW_5` — allowlisted external tool офіційного курсу НБУ,
  LLM-routing, deterministic answers і Telegram `/rate`.
- `JARVIS` — фінальний desktop RAG-проєкт: локальний Tauri/React interface,
  dynamic document/repository ingestion, FTS5 + FAISS + BGE reranking,
  scope-aware metadata filtering і citations. Telegram, agent tools та
  external integrations свідомо прибрані; використовується лише графічний
  доступ з локального ПК.

Фінальне технічне доопрацювання, workflow, презентація та текст захисту
знаходяться у каталозі [`JARVIS`](JARVIS/README.md). Основний changelog:
[`JARVIS/FINAL_IMPROVEMENT.md`](JARVIS/FINAL_IMPROVEMENT.md).

# Implementation status

## Implemented

- Tauri/React local desktop interface with corpus selector, drag-and-drop
  uploads, file preview, citations and code dependency graph;
- FastAPI loopback sidecar with one-time IPC token and WebSocket chat events;
- document/repository ingestion with SHA-256 incremental updates, archive
  guards, page/cell/line citation metadata and code symbols;
- scope-aware FTS5 + multilingual FAISS + graph RRF retrieval and BGE
  reranking;
- grounded JSON contract, evidence gate and extractive no-provider fallback;
- explicit unit/API/ingestion tests for the RAG-only surface.

## Deliberately removed

- Telegram bot and all chat commands;
- external finance, browser, email/calendar and system tools;
- bounded agent loop, approvals, safe/autonomous modes and command execution;
- local Qwen/QLoRA runtime from the desktop product.

## Current limits

- full FAISS/BGE retrieval requires the complete Python environment;
- OCR, media parsing and asynchronous ingestion jobs are not implemented;
- a remote model receives only retrieved context when the user enables a
  local Ollama model; `Evidence only` avoids generation completely.

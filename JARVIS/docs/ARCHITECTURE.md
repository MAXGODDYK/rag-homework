# JARVIS Desktop RAG architecture

```text
Tauri + React desktop window
        ↓ authenticated loopback HTTP/WebSocket
FastAPI sidecar on 127.0.0.1
        ↓
project / file corpus selector
        ↓
early metadata filtering
        ↓
FTS5 + FAISS + code graph RRF → BGE reranking → evidence gate
        ↓
grounded provider answer or extractive evidence
        ↓
file/page/cell/line citations
```

Tauri starts one local Python sidecar. The sidecar chooses a random loopback
port and receives an ephemeral IPC token; every desktop request must supply
that token. There is no Telegram process, public HTTP listener, tool registry
or shell execution path.

SQLite stores projects, conversations, documents, chunks, FTS5, symbols,
graph edges and citations. Originals, extracted text and each project's FAISS
index stay under ignored `local_state/`.

`source_selector` is volatile session state. It can be `auto` (current
project), `all` (all projects of the local desktop owner) or an exact imported
relative path. The retriever resolves that selector before every scoring stage.

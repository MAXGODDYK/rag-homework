# JARVIS architecture

## Processes

Tauri owns the desktop window and starts exactly one Python backend.
The backend binds a random loopback port and prints one bootstrap JSON
line containing `host`, `port` and an ephemeral IPC token. Telegram is
started through the FastAPI lifespan, so it shares one SQLite connection
policy, model cache, agent registry and in-memory session policy store.

## Storage

SQLite stores identities, projects, sessions, messages, document
metadata, chunks, FTS5, symbols, graph edges, tool runs, approvals,
jobs and redacted audit events. Original uploads, extracted text and
per-project FAISS artifacts are stored under:

```text
local_state/users/<hashed-user>/projects/<hashed-project>/
```

The user/project IDs are checked again in every retrieval query; a path
alone is never an authorization decision.

## Agent lifecycle

1. Resolve session and volatile policy.
2. Retrieve scoped context.
3. Select an available provider profile.
4. Ask for one strict JSON decision.
5. Validate the allowlisted tool and its typed arguments.
6. Evaluate mode, scope and dynamic risk.
7. Execute or create an approval.
8. Return the typed result to the provider and continue, up to 8 steps.
9. Validate final citations or mark the answer as general knowledge.

Approved arguments are kept in process memory and are not reconstructed
from redacted audit data. Therefore an approval intentionally becomes
unexecutable after a backend restart.

## Extensibility

Every tool is represented by `ToolSpec`; every document parser returns
`ParsedDocument` and `ExtractedUnit`. Embedding and reranker names are
configuration-backed, so a later code embedding profile can be added
without changing the API or citation schema. OCR/STT/TTS use the same
parser/plugin boundary.

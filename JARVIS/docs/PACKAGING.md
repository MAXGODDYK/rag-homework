# Packaging

For day-to-day development I run the full desktop application through
`npm run tauri dev` after installing `JARVIS/requirements.txt`. This runtime
contains the complete dynamic RAG stack: multilingual embeddings, FAISS and
BGE reranking.

`scripts/build_installer.ps1` builds a Windows Tauri installer with a Python
sidecar. The compact sidecar intentionally excludes heavyweight ML packages,
so it can use FTS5 and remote providers but not local FAISS/BGE. A complete
installer with the full ML runtime is a future packaging task; this limitation
is documented instead of hidden.

# Implementation status

This file separates the tested first release from future extension points.

## Implemented and verified

- loopback FastAPI with random port, one-time IPC token and WebSocket events;
- SQLite migrations, identities, projects, sessions, chunks, FTS5, graph,
  tool runs, approvals and redacted audit;
- document/repository ingestion with SHA-256 incremental updates, archive
  guards and page/cell/line citation metadata;
- FTS5 + FAISS + graph RRF retrieval and optional BGE reranking in the full
  Python runtime;
- bounded eight-step agent, typed tool registry, safe/autonomous policies,
  scopes and double confirmation for high-risk actions;
- deterministic finance, NBU, calculator, schedule, time, weather, URL,
  filesystem, allowlisted process, browser and integration adapters;
- Telegram uploads, project selection, sources, reset, modes and scopes;
- Tauri/React desktop with chat, local Monaco/diff workers, project tree,
  dependency graph, approvals and local write-only provider Settings;
- NSIS and MSI bundles with a PyInstaller sidecar, explicit persistent roots
  and parent-process watchdog;
- 64 automated tests, including all 40 inherited HW5 tests.

Live checks were performed for NBU, FreeModel, dynamic retrieval, Playwright,
the packaged sidecar, Settings persistence and process shutdown. Integrations
without configured credentials remain disabled and were tested with mocks.

## Intentional first-release limits

- OCR, STT, TTS, image, audio and video pipelines are plugin boundaries only;
- compact installer retrieval is FTS5/remote-first; FAISS, BGE and local Qwen
  require the full `.venv`/CUDA runtime or a custom `JARVIS_SIDECAR_PATH`;
- Google/Microsoft adapters accept an existing local access token; interactive
  OAuth consent and refresh flows are not implemented;
- chat events are emitted incrementally after model completion rather than
  native token streaming from every provider;
- terminal is a safety/status panel; commands execute only through typed,
  approval-aware tools;
- background job persistence exists in the schema, while initial ingestion is
  performed synchronously by the local backend;
- local Qwen works only with CUDA and has a slow cold start on the tested
  12-GB GPU, so `auto` prefers a configured remote provider.

These limitations are reported explicitly rather than presented as completed
acceptance scenarios.

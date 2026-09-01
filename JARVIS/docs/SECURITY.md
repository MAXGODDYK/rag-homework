# Security model

- JARVIS accepts requests only from its own Tauri window through a random
  IPC token over `127.0.0.1`.
- There is no public web endpoint, Telegram interface, arbitrary shell,
  browser automation, write tool or external mutation.
- Upload ingestion never executes file content. Archives reject traversal,
  links, nested archives, encrypted archives and quota violations.
- `.gitignore`, virtual environments, binaries, credentials, private keys and
  common build folders are excluded while importing a repository.
- Imported text is untrusted context. The RAG prompt explicitly disallows
  following instructions found in documents.
- Generated citations are validated against the retrieved chunk IDs. Invalid
  model output receives one repair attempt, then JARVIS returns extractive
  evidence rather than an ungrounded answer.
- Secrets are write-only local settings; API responses expose only
  configured/available status.

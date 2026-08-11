# Security model

## Trust boundaries

- Desktop is the local owner interface.
- Telegram full-agent access requires an ignored allowlist.
- Uploaded text and repository content are untrusted data.
- Remote providers are external processors; selected context can leave
  the computer when `remote-strong` or a remote `auto` decision is used.
- External tool responses are validated but still treated as data.

## Filesystem

All paths are expanded and resolved before use. `workspace` is limited
to the active project, `roots` to ignored allowlisted roots and
`computer` to explicit resolved paths. Drive roots cannot be destructive
targets. `.env`, credentials, secrets, tokens and private key locations
become high-risk or are rejected from ingestion.

Archive extraction rejects absolute paths, `..`, symlinks, hardlinks,
encrypted entries, excessive compression ratio and quota overrun.
Nested archives are stored neither as executable content nor recursively
expanded.

## Execution and approvals

Shell input is an executable plus argument array, never an interpolated
shell string. Ordinary commands are allowlisted and run with cwd,
timeout, output cap and a separate process group. Safe mode asks before
write, execute or external mutation. High-risk operations additionally
require a short code retrieved only through local desktop/CLI.

Audit entries redact token-like keys and do not store raw file contents.
API keys, model cache, local state and generated binaries are ignored by
Git. Before publishing, staged changes must be scanned separately.

# Windows packaging

Prerequisites:

- Rust stable;
- MSVC C++ Build Tools;
- WebView2 Runtime;
- Node.js 22+;
- the prepared `JARVIS/.venv`.

`scripts/build_installer.ps1` installs build-only requirements, creates
`jarvis-sidecar-x86_64-pc-windows-msvc.exe` required by the tracked Tauri
`externalBin` configuration and builds MSI/NSIS targets. Generated executables,
PyInstaller work directories and Tauri targets are ignored.

The compact installer does not contain CUDA/PyTorch, Hugging Face model
code or model weights. Its embedded sidecar uses FTS5 retrieval and
remote providers, while the normal development runtime enables
multilingual FAISS/BGE and local Qwen. This split keeps the installer
reproducible instead of embedding several gigabytes of GPU-specific
libraries. A full local-ML runtime can be selected with
`JARVIS_SIDECAR_PATH` after installing the normal requirements.

API credentials and Telegram allowlists remain external local
configuration in both modes. The installed Settings screen writes only
allowlisted values to the per-user application profile. Secret values
are write-only over the loopback API and never returned to the UI.

Development uses `.venv/Scripts/python.exe`; release resolves the bundled
sidecar next to the installed Tauri resources. Both paths use the same
bootstrap contract and loopback-only API. Release passes explicit
`--config-root`, `--state-root` and `--parent-pid` arguments, so one-file
PyInstaller extraction cannot redirect persistent data and the sidecar
terminates when its owning desktop process exits.

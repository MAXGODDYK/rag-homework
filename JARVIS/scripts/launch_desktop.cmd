@echo off
setlocal

rem Use the project Python runtime so semantic retrieval and BGE reranking
rem stay enabled instead of falling back to the compact lexical-only sidecar.
set "JARVIS_USE_DEVELOPMENT_PYTHON=1"
set "JARVIS_DESKTOP=%~dp0..\desktop\src-tauri\target\release\jarvis-desktop.exe"
set "JARVIS_PYTHON=%~dp0..\.venv312\Scripts\python.exe"

rem Keep the original environment as a fallback for other installations.
rem On Windows, Python 3.12 is the supported runtime for native FAISS/Torch.
if not exist "%JARVIS_PYTHON%" set "JARVIS_PYTHON=%~dp0..\.venv\Scripts\python.exe"

if not exist "%JARVIS_DESKTOP%" (
  echo JARVIS desktop executable was not found. Build the desktop application first.
  exit /b 1
)
if not exist "%JARVIS_PYTHON%" (
  echo JARVIS Python environment was not found. Create JARVIS\.venv with Python 3.12 first.
  exit /b 1
)

start "" "%JARVIS_DESKTOP%"

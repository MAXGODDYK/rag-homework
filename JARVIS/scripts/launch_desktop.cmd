@echo off
setlocal

rem The desktop executable inherits this path and starts the matching backend.
set "JARVIS_SIDECAR_PATH=%~dp0..\desktop\src-tauri\target\release\jarvis-sidecar.exe"

if not exist "%JARVIS_SIDECAR_PATH%" (
  echo JARVIS sidecar was not found. Build the desktop application first.
  exit /b 1
)

start "" "%~dp0..\desktop\src-tauri\target\release\jarvis-desktop.exe"

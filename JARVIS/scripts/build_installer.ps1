$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path -LiteralPath $cargoBin) {
    $env:PATH = "$cargoBin;$env:PATH"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Create JARVIS/.venv before building the installer."
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "Rust/Cargo is not available. Install the Tauri Windows prerequisites first."
}

& $python -m pip install -r (Join-Path $projectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install build requirements." }
& $python (Join-Path $PSScriptRoot "build_sidecar.py")
if ($LASTEXITCODE -ne 0) { throw "Failed to build the Python sidecar." }

$desktop = Join-Path $projectRoot "desktop"
Push-Location $desktop
try {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "Failed to install desktop dependencies." }
    npm run tauri build
    if ($LASTEXITCODE -ne 0) { throw "Failed to build the Tauri installer." }
}
finally {
    Pop-Location
}

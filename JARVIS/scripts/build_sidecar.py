from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "desktop" / "src-tauri" / "binaries"


def main() -> int:
    """Build the Python backend as a Windows executable for installer packaging."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "jarvis-sidecar",
            "--exclude-module",
            "torch",
            "--exclude-module",
            "transformers",
            "--exclude-module",
            "sentence_transformers",
            "--exclude-module",
            "peft",
            "--exclude-module",
            "bitsandbytes",
            "--exclude-module",
            "accelerate",
            "--exclude-module",
            "sklearn",
            "--exclude-module",
            "scipy",
            "--exclude-module",
            "pandas",
            "--hidden-import",
            "uvicorn.logging",
            "--hidden-import",
            "uvicorn.loops.auto",
            "--hidden-import",
            "uvicorn.protocols.http.auto",
            "--hidden-import",
            "uvicorn.protocols.websockets.auto",
            "--hidden-import",
            "uvicorn.lifespan.on",
            "--paths",
            str(ROOT),
            str(ROOT / "scripts" / "jarvis_sidecar.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    target = OUTPUT / "jarvis-sidecar-x86_64-pc-windows-msvc.exe"
    shutil.copy2(ROOT / "dist" / "jarvis-sidecar.exe", target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

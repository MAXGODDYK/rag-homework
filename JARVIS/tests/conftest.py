from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolate_live_google_sheets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never inherit or mutate the developer's live Sheets DB."""
    for name in (
        "JARVIS_GOOGLE_SERVICE_ACCOUNT_PATH",
        "JARVIS_GOOGLE_OWNER_EMAIL",
        "JARVIS_GOOGLE_SPREADSHEET_ID",
    ):
        monkeypatch.setenv(name, "")

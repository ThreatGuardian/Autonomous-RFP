"""Test bootstrap: isolated var directory, seeded database, shared trained models."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Must be set before any ``app`` import so Settings picks it up. Models are
# cached across runs in a stable temp folder to keep the suite fast; the
# database is recreated on every session.
_VAR = Path(tempfile.gettempdir()) / "tenderdesk-tests"
_VAR.mkdir(exist_ok=True)
os.environ["TD_VAR_DIR"] = str(_VAR)
os.environ["TD_COMPANY"] = "meridian"
os.environ["TD_FX_MODE"] = "offline"
os.environ["TD_REQUIRE_AUTH"] = "0"
os.environ["TD_LLM"] = "off"  # agents run on rules; language-model steps are tested with a scripted client
(_VAR / "tenderdesk.sqlite3").unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    from app.db.seed import seed_all

    seed_all()
    yield

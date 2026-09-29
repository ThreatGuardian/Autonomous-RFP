"""Runtime configuration.

Values are read from environment variables (prefix ``TD_``) with sensible
defaults so the system runs out of the box on a developer machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"


def _env(name: str, default: str) -> str:
    return os.environ.get(f"TD_{name}", default)


@dataclass(frozen=True)
class Settings:
    var_dir: Path = field(default_factory=lambda: Path(_env("VAR_DIR", str(BACKEND_ROOT / "var"))))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))

    # Mock competitor market service. When empty the in-process mock is used.
    market_api_url: str = field(default_factory=lambda: _env("MARKET_API_URL", ""))
    market_api_key: str = field(default_factory=lambda: _env("MARKET_API_KEY", "demo-market-key"))

    # Currency provider: "live" tries public FX APIs, then falls back to cache/reference.
    fx_mode: str = field(default_factory=lambda: _env("FX_MODE", "live"))
    fx_cache_ttl_hours: int = field(default_factory=lambda: int(_env("FX_CACHE_TTL_HOURS", "12")))
    fx_timeout_seconds: float = field(default_factory=lambda: float(_env("FX_TIMEOUT", "4")))

    pipeline_workers: int = field(default_factory=lambda: int(_env("PIPELINE_WORKERS", "4")))
    frontend_dist: Path = field(
        default_factory=lambda: Path(_env("FRONTEND_DIST", str(BACKEND_ROOT.parent / "frontend" / "dist")))
    )

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.var_dir / 'tenderdesk.sqlite3'}"

    @property
    def model_dir(self) -> Path:
        return self.var_dir / "models"

    @property
    def document_dir(self) -> Path:
        return self.var_dir / "documents"

    def ensure_dirs(self) -> None:
        for path in (self.var_dir, self.model_dir, self.document_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

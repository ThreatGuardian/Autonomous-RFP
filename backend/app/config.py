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
COMPANIES_DIR = DATA_DIR / "companies"
# Files that describe one company (its profile, catalogue, customers, competitors and
# knowledge base). Everything else in DATA_DIR (tax rules, countries, FX, pricing
# policy) is shared.
COMPANY_FILES = {"company.json", "catalog.json", "customers.json", "market.json", "value_adds.json", "price_tiers.json"}


def _env(name: str, default: str) -> str:
    return os.environ.get(f"TD_{name}", default)


def _flag(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() not in ("0", "false", "no", "off", "")


def _production() -> bool:
    return _env("ENV", "development").strip().lower() == "production"


@dataclass(frozen=True)
class Settings:
    # "development" (default) or "production". Production turns on secure cookies, turns off
    # open sign-up and the demo account, and refuses to start with insecure defaults.
    environment: str = field(default_factory=lambda: "production" if _production() else "development")
    # Which company's data set the install runs as (a folder under data/companies).
    company: str = field(default_factory=lambda: _env("COMPANY", "datacare"))
    var_dir: Path = field(default_factory=lambda: Path(_env("VAR_DIR", str(BACKEND_ROOT / "var" / _env("COMPANY", "datacare")))))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))

    # Mock competitor market service. When empty the in-process mock is used.
    market_api_url: str = field(default_factory=lambda: _env("MARKET_API_URL", ""))
    market_api_key: str = field(default_factory=lambda: _env("MARKET_API_KEY", "demo-market-key"))

    # Currency provider: "live" tries public FX APIs, then falls back to cache/reference.
    fx_mode: str = field(default_factory=lambda: _env("FX_MODE", "live"))
    fx_cache_ttl_hours: int = field(default_factory=lambda: int(_env("FX_CACHE_TTL_HOURS", "12")))
    fx_timeout_seconds: float = field(default_factory=lambda: float(_env("FX_TIMEOUT", "4")))

    pipeline_workers: int = field(default_factory=lambda: int(_env("PIPELINE_WORKERS", "4")))

    # Language-model agents (Claude). "auto" uses them when ANTHROPIC_API_KEY is set,
    # "on" requires them, "off" runs the rule-based agents only.
    llm_mode: str = field(default_factory=lambda: _env("LLM", "auto").strip().lower())
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "claude-opus-5-5"))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT", "300")))

    # Authentication: session cookies signed with a per-install secret.
    require_auth: bool = field(default_factory=lambda: _env("REQUIRE_AUTH", "1") not in ("0", "false", "no"))
    session_hours: int = field(default_factory=lambda: int(_env("SESSION_HOURS", "12")))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", ""))
    # Session cookies are sent over HTTPS only. On by default in production.
    cookie_secure: bool = field(default_factory=lambda: _flag("COOKIE_SECURE", _production()))
    # Whether anyone who can reach the server may create an account.
    allow_signup: bool = field(default_factory=lambda: _flag("ALLOW_SIGNUP", not _production()))
    # Seed the demo account (priya / tenderdesk). Never in production.
    demo_user: bool = field(default_factory=lambda: _flag("DEMO_USER", not _production()) and not _production())
    # Firebase project used to verify Google / SSO sign-in tokens. Empty disables Firebase sign-in.
    firebase_project_id: str = field(default_factory=lambda: _env("FIREBASE_PROJECT_ID", ""))
    # Extra browser origins allowed to call the API (comma-separated), besides the server's own.
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip().rstrip("/") for o in _env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()))
    frontend_dist: Path = field(
        default_factory=lambda: Path(_env("FRONTEND_DIST", str(BACKEND_ROOT.parent / "frontend" / "dist")))
    )

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.var_dir / 'tenderdesk.sqlite3'}"

    @property
    def company_dir(self) -> Path:
        return COMPANIES_DIR / self.company

    @property
    def knowledge_dir(self) -> Path:
        return self.company_dir / "knowledge"

    @property
    def model_dir(self) -> Path:
        return self.var_dir / "models"

    @property
    def document_dir(self) -> Path:
        return self.var_dir / "documents"

    @property
    def production(self) -> bool:
        return self.environment == "production"

    def ensure_dirs(self) -> None:
        for path in (self.var_dir, self.model_dir, self.document_dir):
            path.mkdir(parents=True, exist_ok=True)

    def check_production(self) -> list[str]:
        """Configuration problems that make a production deployment unsafe."""
        problems = []
        if not self.production:
            return problems
        if len(self.secret_key) < 32:
            problems.append("TD_SECRET_KEY must be set to a random value of at least 32 characters")
        if self.market_api_key == "demo-market-key":
            problems.append("TD_MARKET_API_KEY must not use the demo value")
        if not self.require_auth:
            problems.append("TD_REQUIRE_AUTH cannot be disabled")
        return problems


def data_file(name: str) -> Path:
    """Resolve a data file, preferring the active company's copy."""
    if name in COMPANY_FILES:
        return get_settings().company_dir / name
    return DATA_DIR / name


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

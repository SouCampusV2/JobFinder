"""Central configuration loaded from environment (.env).

Never hardcode secrets. All tunables live here so the rest of the code has no
magic numbers. Import the module-level `settings` singleton everywhere.

Scraping is handled by the Chrome Extension, so this backend has no
Playwright/LinkedIn settings - only OpenAI, Telegram, server and storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def _get_list(key: str, default: str) -> list[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- Secrets --------------------------------------------------------- #
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )

    # --- OpenAI ---------------------------------------------------------- #
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )

    # --- Sources shown as UI filters ------------------------------------ #
    search_sources: list[str] = field(
        default_factory=lambda: _get_list("SEARCH_SOURCES", "linkedin,glassdoor")
    )

    # --- Public LinkedIn fetch (no login, guest endpoint) --------------- #
    # These drive the server-side scheduler that reads PUBLIC job listings.
    search_query: str = field(
        default_factory=lambda: os.getenv("SEARCH_QUERY", "Product Operations")
    )
    search_location: str = field(
        default_factory=lambda: os.getenv("SEARCH_LOCATION", "European Union")
    )
    # How often the scheduler runs (minutes). 0 disables the scheduler.
    scrape_interval_minutes: int = field(
        default_factory=lambda: _get_int("SCRAPE_INTERVAL_MINUTES", 30)
    )
    # Max cards to pull per source per cycle (guest pages are 10 each).
    max_jobs_per_cycle: int = field(
        default_factory=lambda: _get_int("MAX_JOBS_PER_CYCLE", 50)
    )
    # Only fetch jobs posted within this many seconds (LinkedIn f_TPR filter).
    # 3600 = last hour (best for "first to apply"); 86400 = last 24h.
    linkedin_tpr_seconds: int = field(
        default_factory=lambda: _get_int("LINKEDIN_TPR_SECONDS", 86400)
    )
    # A normal desktop browser UA - public endpoint, but be a good citizen.
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36",
        )
    )
    # Polite delay range (seconds) between paginated guest requests.
    fetch_delay_min: float = field(
        default_factory=lambda: float(os.getenv("FETCH_DELAY_MIN", "2"))
    )
    fetch_delay_max: float = field(
        default_factory=lambda: float(os.getenv("FETCH_DELAY_MAX", "5"))
    )

    # --- Web server ------------------------------------------------------ #
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _get_int("PORT", 8000))
    # Comma-separated origins allowed to POST to /api/ingest (the extension).
    # chrome-extension://<id> once you know the id; "*" is fine for a local tool.
    # Extra origins allowed to call the API, on top of the browser extension and
    # this machine's own pages, which `origins.py` always permits. The default
    # is EMPTY on purpose: it used to be "*", which told every website in the
    # browser that it was welcome to read the CV out of a server with no
    # password on it.
    cors_origins: list[str] = field(
        default_factory=lambda: [o for o in _get_list("CORS_ORIGINS", "") if o != "*"]
    )

    # --- Storage --------------------------------------------------------- #
    db_path: Path = field(
        default_factory=lambda: (
            Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "jobs.db"))).expanduser()
        )
    )

    def redacted(self) -> dict[str, str]:
        """Safe view for logging - never expose secrets."""
        def mask(value: str) -> str:
            return "set" if value else "MISSING"

        return {
            "openai_api_key": mask(self.openai_api_key),
            "telegram_bot_token": mask(self.telegram_bot_token),
            "telegram_chat_id": mask(self.telegram_chat_id),
            "openai_model": self.openai_model,
            "sources": ",".join(self.search_sources),
            "query": self.search_query,
            "location": self.search_location,
            "interval_min": str(self.scrape_interval_minutes),
            "host": self.host,
            "port": str(self.port),
        }


settings = Settings()

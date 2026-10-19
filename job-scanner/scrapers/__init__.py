"""Data-model package.

Historically held Playwright scrapers; scraping now lives in the Chrome
Extension. Only the shared `JobListing` dataclass remains here.
"""

from scrapers.base import JobListing

__all__ = ["JobListing"]

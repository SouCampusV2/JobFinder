"""DEPRECATED - replaced by the Chrome Extension.

Scraping now happens in job-scanner-extension/ (Manifest V3): content.js reads
the LinkedIn DOM inside the user's real session and POSTs to /api/ingest. There
is intentionally no server-side LinkedIn scraper anymore (no Playwright, no
login automation, no external requests to LinkedIn).

This module is kept only so old imports don't break.
"""

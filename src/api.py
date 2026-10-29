"""Thin client for Polymarket's public Data API (no login needed).

Handles pacing, retries on 429/503 (respecting Retry-After), and cursor paging.
Docs: https://docs.polymarket.com/api-reference/data-api/overview
"""
import time
import logging
import requests

from . import config

log = logging.getLogger(__name__)
_session = requests.Session()
_session.headers["User-Agent"] = "prediction-research/0.1"
_last_call = 0.0


def get(path: str, params: dict | None = None, base: str = config.DATA_API, max_retries: int = 6):
    """GET base+path and return parsed JSON. Retries transient errors with backoff."""
    global _last_call
    url = base + path
    for attempt in range(max_retries):
        wait = config.MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            r = _session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        except requests.RequestException as e:
            delay = 2 ** attempt
            log.warning("network error %s; retry in %ss", e, delay)
            time.sleep(delay)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            delay = float(r.headers.get("Retry-After", 2 ** attempt))
            log.warning("%s on %s; retry in %ss", r.status_code, path, delay)
            time.sleep(delay)
            continue
        # 4xx other than 429 = our request is wrong; don't retry
        raise RuntimeError(f"{r.status_code} for {r.url}: {r.text[:300]}")
    raise RuntimeError(f"gave up after {max_retries} attempts: {url} {params}")


def paginate(path: str, params: dict, max_rows: int | None = None, resend_all: bool = False):
    """Yield rows from a v2 cursor-paged endpoint until next_cursor is null.

    /v2/positions rule: after the first page, send only the anchor (user/condition) and
    cursor, plus filters the cursor does NOT carry (title, start/end, condition).
    /v2/trades and /v2/prices-history want every filter resent: use resend_all=True
    (everything except limit, which the cursor carries).
    """
    if resend_all:
        carry = {k: v for k, v in params.items() if k != "limit"}
    else:
        carry = {k: v for k, v in params.items() if k in ("user", "condition", "title", "start", "end", "event_id")}
    page = get(path, params)
    n, pages, seen = 0, 1, set()
    while True:
        rows = page.get("data") or []
        for row in rows:
            yield row
            n += 1
            if max_rows and n >= max_rows:
                log.info("    hit cap of %d rows; stopping this list", max_rows)
                return
        cursor = (page.get("pagination") or {}).get("next_cursor")
        if not cursor:
            return
        if cursor in seen or not rows:
            log.warning("    API returned a repeated cursor or an empty page; stopping to avoid an endless loop")
            return
        seen.add(cursor)
        pages += 1
        if pages % 5 == 0:
            log.info("    ...page %d, %d rows so far (%s)", pages, n, params.get("status", ""))
        page = get(path, {**carry, "cursor": cursor})

import gzip
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx

LOGGER = logging.getLogger(__name__)
# The key travels in the query string, and httpx logs every request URL at INFO.
for _name in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(_name).setLevel(logging.WARNING)
URL = "https://apiprod.dol.gov/v4/get/WHD/enforcement/json"
RETRYABLE = {429, 502, 503, 504}


class IngestError(RuntimeError):
    pass


def redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def _error(message: str, api_key: str, status: int | None = None) -> IngestError:
    error = IngestError(redact(message, api_key))
    error.status = status
    return error


def fetch_page(
    client: httpx.Client,
    *,
    api_key: str,
    offset: int,
    limit: int,
    since: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    # The API documents no rate limit and sends no Retry-After; its 429 window is longer
    # than 5 minutes, so back off for up to ~50 minutes before giving up (the run resumes).
    max_retries: int = 10,
    base_delay: float = 5.0,
) -> list[dict]:
    params = {"X-API-KEY": api_key, "limit": limit, "offset": offset, "sort_by": "case_id"}
    if since is not None:
        params["filter_object"] = json.dumps({"field": "load_dt", "operator": "gt", "value": since})

    for attempt in range(max_retries + 1):
        try:
            response = client.get(URL, params=params)
        except httpx.HTTPError:
            raise _error("WHD API transport error", api_key) from None
        if response.status_code == 200:
            try:
                data = response.json()["data"]
            except (ValueError, KeyError, TypeError):
                data = None
            if not isinstance(data, list):
                raise _error("WHD API returned an invalid response", api_key, 200) from None
            return data
        # 429 is the rate limit; 502-504 are transient gateway errors. 500 is not retried: the
        # API answers 500 past the end of the data.
        if response.status_code in RETRYABLE and attempt < max_retries:
            sleep(min(base_delay * 2**attempt, 900))
            continue
        raise _error(
            f"WHD API returned HTTP {response.status_code}", api_key, response.status_code
        ) from None

    raise AssertionError("unreachable")


def _tag(since: str | None) -> str:
    return "full" if since is None else re.sub(r"[^A-Za-z0-9]", "-", since)


def _write_checkpoint(path: Path, offset: int, since: str | None) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"offset": offset, "since": since}))
    os.replace(temporary, path)


def resolve_since(state_dir: Path, full: bool, watermark: Callable[[], str | None]) -> str | None:
    """An interrupted run finishes first: its checkpoint's `since` wins over the watermark.

    Otherwise a partial backfill would already have rows, the watermark would turn the
    next run incremental, and every older record past the checkpoint would be skipped.
    """
    if full:
        return None
    checkpoint = state_dir / "whd_checkpoint.json"
    if checkpoint.exists():
        return json.loads(checkpoint.read_text()).get("since")
    return watermark()


def run(
    client: httpx.Client,
    *,
    api_key: str,
    state_dir: Path,
    since: str | None,
    load_page: Callable[[Path], int],
    sleep: Callable[[float], None] = time.sleep,
    # The API rejects responses over 6 MB (HTTP 413); rows are ~2.8 KB, so 1,500 rows is ~4.2 MB.
    page_size: int = 1_500,
    page_pause: float = 3.0,
) -> tuple[int, int, int]:
    state_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = state_dir / "whd_checkpoint.json"
    pages_dir = state_dir / "pages"
    offset = 0
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text())
        if saved.get("since") == since:
            offset = saved["offset"]

    pages = rows_fetched = rows_loaded = 0
    while True:
        # A run ends on a short page. Any error, a 500 included, raises and keeps the
        # checkpoint: the API answers 500 past the end, but a run only gets there when the
        # row count is an exact multiple of page_size, and a silent stop would hide a fault.
        data = fetch_page(
            client, api_key=api_key, offset=offset, limit=page_size, since=since, sleep=sleep
        )
        if not data:
            break
        pages += 1
        rows_fetched += len(data)
        pages_dir.mkdir(exist_ok=True)
        # The content hash in the name means a re-fetched identical page keeps its name (COPY's
        # load history skips it), while changed data gets a new name and always loads.
        body = gzip.compress(json.dumps(data).encode(), mtime=0)
        digest = hashlib.sha256(body).hexdigest()[:12]
        prefix = f"whd_{_tag(since)}_{offset:08d}_"
        page = pages_dir / f"{prefix}{digest}.json.gz"
        # Drop older versions of this page, so a later bulk load can never pick up two versions
        # of one page in a single COPY, where loaded_at ties and the stale row could win.
        for stale in pages_dir.glob(f"{prefix}*.json.gz"):
            if stale != page:
                stale.unlink()
        page.write_bytes(body)
        rows_loaded += load_page(page)
        offset += len(data)
        _write_checkpoint(checkpoint, offset, since)
        if len(data) < page_size:
            break
        sleep(page_pause)

    checkpoint.unlink(missing_ok=True)
    return pages, rows_fetched, rows_loaded

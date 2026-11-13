import gzip
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
    max_retries: int = 6,
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
                return response.json()["data"]
            except (ValueError, KeyError, TypeError):
                raise _error("WHD API returned an invalid response", api_key, 200) from None
        if response.status_code == 429 and attempt < max_retries:
            sleep(min(base_delay * 2**attempt, 300))
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


def run(
    client: httpx.Client,
    *,
    api_key: str,
    state_dir: Path,
    since: str | None,
    load_page: Callable[[Path], int],
    sleep: Callable[[float], None] = time.sleep,
    page_size: int = 10_000,
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
    previous_was_full = False
    while True:
        try:
            data = fetch_page(
                client,
                api_key=api_key,
                offset=offset,
                limit=page_size,
                since=since,
                sleep=sleep,
            )
        except IngestError as exc:
            if not (offset > 0 and previous_was_full and exc.status == 500):
                raise
            sleep(5.0)
            try:
                data = fetch_page(
                    client,
                    api_key=api_key,
                    offset=offset,
                    limit=page_size,
                    since=since,
                    sleep=sleep,
                )
            except IngestError as retry_error:
                if retry_error.status != 500:
                    raise
                # ponytail: a real 500 here truncates the run; raw-vs-fetched counts catch it.
                LOGGER.warning(
                    "HTTP 500 at offset %s after a full page; treating as end of data", offset
                )
                break

        if not data:
            break
        pages += 1
        rows_fetched += len(data)
        pages_dir.mkdir(exist_ok=True)
        page = pages_dir / f"whd_{_tag(since)}_{offset:08d}.json.gz"
        page.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
        rows_loaded += load_page(page)
        offset += len(data)
        _write_checkpoint(checkpoint, offset, since)
        previous_was_full = len(data) == page_size
        if not previous_was_full:
            break
        sleep(page_pause)

    checkpoint.unlink(missing_ok=True)
    return pages, rows_fetched, rows_loaded

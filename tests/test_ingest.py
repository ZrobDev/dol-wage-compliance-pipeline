import gzip
import json
import logging
import traceback

import httpx
import pytest

from pipeline.ingest import IngestError, fetch_page, resolve_since, run

KEY = "TESTKEY-not-real-123"


def rows(start, count):
    return [
        {"case_id": index, "load_dt": "2026-01-01T00:00:00"}
        for index in range(start, start + count)
    ]


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def loader(path):
    with gzip.open(path, "rt") as page:
        return len(json.load(page))


@pytest.mark.parametrize("transient", [429, 502, 503, 504])
def test_fetch_page_retries_transient_errors(transient):
    sleeps = []
    responses = [transient, transient, 200]

    def handler(request):
        status = responses.pop(0)
        return httpx.Response(status, json={"data": rows(0, 1)})

    with client(handler) as http:
        assert fetch_page(http, api_key=KEY, offset=0, limit=10, sleep=sleeps.append) == rows(0, 1)
    assert sleeps == [5.0, 10.0]


def test_fetch_page_raises_after_retry_ceiling():
    sleeps = []

    with (
        client(lambda request: httpx.Response(429, json={"data": []})) as http,
        pytest.raises(IngestError),
    ):
        fetch_page(http, api_key=KEY, offset=0, limit=10, sleep=sleeps.append, max_retries=2)
    assert sleeps == [5.0, 10.0]


def test_run_resumes_matching_checkpoint_and_ignores_different_since(tmp_path):
    checkpoint = tmp_path / "whd_checkpoint.json"
    checkpoint.write_text('{"offset": 20000, "since": null}')
    offsets = []

    def handler(request):
        offsets.append(int(request.url.params["offset"]))
        return httpx.Response(200, json={"data": []})

    with client(handler) as http:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            page_size=10,
            page_pause=0,
        )
    assert offsets == [20000]

    checkpoint.write_text('{"offset": 20000, "since": "2025-01-01T00:00:00"}')
    with client(handler) as http:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            page_size=10,
            page_pause=0,
        )
    assert offsets[-1] == 0


def test_run_sends_incremental_filter(tmp_path):
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"data": []})

    with client(handler) as http:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since="2026-01-16T13:04:16",
            load_page=loader,
            page_pause=0,
        )
    assert json.loads(seen["filter_object"]) == {
        "field": "load_dt",
        "operator": "gt",
        "value": "2026-01-16T13:04:16",
    }


def test_run_writes_deterministic_pages_and_clears_checkpoint(tmp_path):
    responses = [rows(0, 2), rows(2, 1)]

    def handler(request):
        return httpx.Response(200, json={"data": responses.pop(0)})

    with client(handler) as http:
        result = run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            page_size=2,
            page_pause=0,
        )
    (page,) = (tmp_path / "pages").glob("whd_full_00000000_*.json.gz")
    first_bytes = page.read_bytes()
    assert result == (2, 3, 3)
    assert not (tmp_path / "whd_checkpoint.json").exists()

    responses[:] = [rows(0, 2), rows(2, 1)]
    with client(handler) as http:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            page_size=2,
            page_pause=0,
        )
    assert page.read_bytes() == first_bytes

    # Changed data at offset 0 replaces the older version on disk instead of sitting beside it.
    responses[:] = [rows(0, 1) + rows(5, 1), rows(2, 1)]
    with client(handler) as http:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            page_size=2,
            page_pause=0,
        )
    (newer,) = (tmp_path / "pages").glob("whd_full_00000000_*.json.gz")
    assert newer != page
    assert len(list((tmp_path / "pages").glob("whd_full_*.json.gz"))) == 2


def test_run_raises_on_500_after_a_full_page_and_keeps_the_checkpoint(tmp_path):
    calls = []

    def handler(request):
        calls.append(int(request.url.params["offset"]))
        if len(calls) == 1:
            return httpx.Response(200, json={"data": rows(0, 2)})
        return httpx.Response(500, json={"data": []})

    with client(handler) as http, pytest.raises(IngestError) as caught:
        run(
            http,
            api_key=KEY,
            state_dir=tmp_path,
            since=None,
            load_page=loader,
            sleep=lambda _: None,
            page_size=2,
            page_pause=0,
        )
    assert caught.value.status == 500
    assert calls == [0, 2]
    assert json.loads((tmp_path / "whd_checkpoint.json").read_text()) == {
        "offset": 2,
        "since": None,
    }


@pytest.mark.parametrize("body", [{"data": None}, {"data": {}}, {"rows": []}])
def test_fetch_page_rejects_a_200_without_a_data_list(body):
    with (
        client(lambda request: httpx.Response(200, json=body)) as http,
        pytest.raises(IngestError),
    ):
        fetch_page(http, api_key=KEY, offset=0, limit=1)


@pytest.mark.parametrize("kind", ["transport", "response"])
def test_fetch_page_redacts_key_everywhere(caplog, kind):
    caplog.set_level(logging.DEBUG)

    def handler(request):
        if kind == "transport":
            raise httpx.ConnectError(f"failed {request.url}", request=request)
        return httpx.Response(403, text=f"denied {KEY}", request=request)

    with client(handler) as http, pytest.raises(IngestError) as caught:
        fetch_page(http, api_key=KEY, offset=0, limit=1)
    error = caught.value
    formatted = "".join(traceback.format_exception(error))
    assert KEY not in str(error)
    assert KEY not in repr(error)
    assert KEY not in formatted
    assert KEY not in caplog.text
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert error.status == (None if kind == "transport" else 403)


def test_resolve_since_finishes_an_interrupted_run_before_going_incremental(tmp_path):
    def watermark():
        return "2026-01-16T13:04:16"

    assert resolve_since(tmp_path, full=False, watermark=watermark) == "2026-01-16T13:04:16"
    assert resolve_since(tmp_path, full=True, watermark=watermark) is None

    (tmp_path / "whd_checkpoint.json").write_text('{"offset": 6000, "since": null}')
    assert resolve_since(tmp_path, full=False, watermark=watermark) is None

    (tmp_path / "whd_checkpoint.json").write_text(
        '{"offset": 6000, "since": "2026-01-01T00:00:00"}'
    )
    assert resolve_since(tmp_path, full=True, watermark=watermark) is None

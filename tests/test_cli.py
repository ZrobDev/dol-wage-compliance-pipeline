from pipeline import cli, warehouse
from pipeline.ingest import IngestError


def setup_fakes(monkeypatch, tmp_path, loads, *, fail=False, newly_loaded=4):
    monkeypatch.setenv("DOL_API_KEY", "TESTKEY-not-real-123")
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "whd_full_00000000_old.json.gz").write_bytes(b"from an interrupted earlier run")

    class FakeConn:
        def close(self):
            pass

    def fake_run(client, *, load_page, **kwargs):
        # This run fetches two pages, 2 rows and 1 row.
        for name in ("whd_full_00001500_a.json.gz", "whd_full_00003000_b.json.gz"):
            (pages / name).write_bytes(b"page")
            load_page(pages / name)
        if fail:
            raise IngestError("WHD API returned HTTP 502")
        return 2, 3, 0

    def load_pages(conn, paths, *, force):
        loads.append(([path.name for path in paths], force))
        return newly_loaded

    monkeypatch.setattr(warehouse, "connect", lambda: FakeConn())
    monkeypatch.setattr(warehouse, "watermark", lambda conn: None)
    monkeypatch.setattr(warehouse, "load_pages", load_pages)
    monkeypatch.setattr(warehouse, "make_loader", lambda conn: lambda path: 0)
    monkeypatch.setattr(cli, "run", fake_run)


ALL_PAGES = [
    "whd_full_00000000_old.json.gz",
    "whd_full_00001500_a.json.gz",
    "whd_full_00003000_b.json.gz",
]


def test_defer_load_loads_every_pending_page_once_at_the_end(tmp_path, monkeypatch, capsys):
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads)
    assert cli.main(["ingest", "--defer-load", "--state-dir", str(tmp_path)]) == 0
    # Pages left by an interrupted earlier run are loaded too, in the same single load.
    assert loads == [(ALL_PAGES, False)]
    assert "fetched=3 loaded=4" in capsys.readouterr().out


def test_defer_load_still_loads_what_was_fetched_when_the_api_fails(tmp_path, monkeypatch):
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads, fail=True)
    assert cli.main(["ingest", "--defer-load", "--state-dir", str(tmp_path)]) == 2
    assert loads == [(ALL_PAGES, False)]


def test_without_defer_load_pages_load_one_by_one(tmp_path, monkeypatch):
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads)
    # The per-page fake loader returns 0 rows, so loaded < fetched and the CLI exits 1.
    assert cli.main(["ingest", "--state-dir", str(tmp_path)]) == 1
    assert loads == []


def test_defer_load_succeeds_when_copy_skips_identical_pages(tmp_path, monkeypatch):
    # A re-fetch of unchanged pages keeps their names, so COPY skips them and loads 0 rows.
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads, newly_loaded=0)
    assert cli.main(["ingest", "--defer-load", "--state-dir", str(tmp_path)]) == 0


WATERMARK = "2026-11-03T00:18:04"


def setup_quiet_week(monkeypatch, tmp_path, *, newest, fetched=0, leftover_rows=0):
    """An incremental run that fetches `fetched` rows; leftover pages load `leftover_rows`."""
    monkeypatch.setenv("DOL_API_KEY", "TESTKEY-not-real-123")
    canary_calls = []

    class FakeConn:
        def close(self):
            pass

    def fake_newest(client, *, api_key):
        canary_calls.append(api_key)
        return newest

    monkeypatch.setattr(warehouse, "connect", lambda: FakeConn())
    monkeypatch.setattr(warehouse, "watermark", lambda conn: WATERMARK)
    monkeypatch.setattr(warehouse, "load_pages", lambda conn, paths, *, force: leftover_rows)
    monkeypatch.setattr(cli, "run", lambda client, **kwargs: (int(bool(fetched)), fetched, 0))
    monkeypatch.setattr(cli, "newest_load_dt", fake_newest)
    return canary_calls


def test_quiet_week_exits_with_the_empty_code_only_when_asked(tmp_path, monkeypatch):
    calls = setup_quiet_week(monkeypatch, tmp_path, newest=WATERMARK)
    argv = ["ingest", "--defer-load", "--state-dir", str(tmp_path)]
    assert cli.main(argv) == 0
    assert cli.main([*argv, "--empty-exit-code", "99"]) == 99
    assert len(calls) == 2


def test_empty_fetch_with_newer_api_data_fails_as_a_broken_filter(tmp_path, monkeypatch, capsys):
    setup_quiet_week(monkeypatch, tmp_path, newest="2026-12-01T00:00:00")
    argv = ["ingest", "--defer-load", "--state-dir", str(tmp_path), "--empty-exit-code", "99"]
    assert cli.main(argv) == 2
    assert "past the watermark 2026-11-03T00:18:04" in capsys.readouterr().err


def test_leftover_pages_that_load_are_work_not_a_quiet_week(tmp_path, monkeypatch):
    setup_quiet_week(monkeypatch, tmp_path, newest=WATERMARK, leftover_rows=5)
    argv = ["ingest", "--defer-load", "--state-dir", str(tmp_path), "--empty-exit-code", "99"]
    assert cli.main(argv) == 0


def test_canary_is_skipped_when_rows_were_fetched(tmp_path, monkeypatch):
    calls = setup_quiet_week(monkeypatch, tmp_path, newest="2099-01-01T00:00:00", fetched=3)
    argv = ["ingest", "--defer-load", "--state-dir", str(tmp_path), "--empty-exit-code", "99"]
    assert cli.main(argv) == 0
    assert calls == []

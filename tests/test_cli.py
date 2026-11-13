from pipeline import cli, warehouse
from pipeline.ingest import IngestError


def setup_fakes(monkeypatch, tmp_path, loads, *, fail=False):
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
        return 4

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

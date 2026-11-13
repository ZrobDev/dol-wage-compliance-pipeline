from pipeline import cli, warehouse


def setup_fakes(monkeypatch, tmp_path, loads):
    monkeypatch.setenv("DOL_API_KEY", "TESTKEY-not-real-123")

    class FakeConn:
        def close(self):
            pass

    def fake_run(client, *, load_page, **kwargs):
        # Two pages "fetched": 2 rows and 1 row.
        loaded = sum(load_page(tmp_path / name) for name in ("p0.json.gz", "p1.json.gz"))
        return 2, 3, loaded

    def load_pages(conn, paths, *, force):
        loads.append(([path.name for path in paths], force))
        return 3

    monkeypatch.setattr(warehouse, "connect", lambda: FakeConn())
    monkeypatch.setattr(warehouse, "watermark", lambda conn: None)
    monkeypatch.setattr(warehouse, "load_pages", load_pages)
    monkeypatch.setattr(warehouse, "make_loader", lambda conn: lambda path: 0)
    monkeypatch.setattr(cli, "run", fake_run)


def test_defer_load_loads_every_page_once_at_the_end(tmp_path, monkeypatch, capsys):
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads)
    assert cli.main(["ingest", "--defer-load", "--state-dir", str(tmp_path)]) == 0
    assert loads == [(["p0.json.gz", "p1.json.gz"], True)]
    assert "fetched=3 loaded=3" in capsys.readouterr().out


def test_without_defer_load_pages_load_one_by_one(tmp_path, monkeypatch):
    loads = []
    setup_fakes(monkeypatch, tmp_path, loads)
    # The per-page fake loader returns 0 rows, so fetched != loaded and the CLI exits 1.
    assert cli.main(["ingest", "--state-dir", str(tmp_path)]) == 1
    assert loads == []

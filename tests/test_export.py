import csv
from decimal import Decimal

import pytest

from pipeline import cli, warehouse
from pipeline.export import EXIT_UNSAFE
from pipeline.state import EXIT_LOCKED, exclusive

HEADER = [
    "sector_code",
    "sector_name",
    "state_code",
    "fiscal_year",
    "cases",
    "is_suppressed",
    "case_violations",
    "employees_due_back_wages",
    "back_wages_agreed",
    "cmp_assessed",
]
SMALL = ("44-45", "Retail Trade", "PA", 1984, 1, True, None, None, None, None)
BIG = ("23", "Construction, Inc. & Sons", "TX", 2020, 7, False, 12, 30, Decimal("1234.56"), 0)


def fake_warehouse(monkeypatch, rows):
    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(warehouse, "connect", lambda: FakeConn())
    monkeypatch.setattr(warehouse, "fetch_aggregate", lambda conn: (HEADER, rows))


def out(tmp_path):
    return tmp_path / "exports" / "agg_industry_state_year.csv"


def test_export_writes_the_chart_csv_with_small_cells_blank(tmp_path, monkeypatch):
    fake_warehouse(monkeypatch, [SMALL, BIG])
    assert cli.main(["export", "--state-dir", str(tmp_path)]) == 0
    with out(tmp_path).open(newline="") as handle:
        assert list(csv.reader(handle)) == [
            HEADER,
            ["44-45", "Retail Trade", "PA", "1984", "1", "True", "", "", "", ""],
            [
                "23",
                "Construction, Inc. & Sons",
                "TX",
                "2020",
                "7",
                "False",
                "12",
                "30",
                "1234.56",
                "0",
            ],
        ]


SMALL_NOT_SUPPRESSED = ("44-45", "Retail Trade", "PA", 1984, 2, False, 1, 1, Decimal(10), 0)
SUPPRESSED_WITH_FIGURE = (
    "44-45",
    "Retail Trade",
    "PA",
    1984,
    1,
    True,
    None,
    None,
    Decimal(10),
    None,
)
BIG_SUPPRESSED = ("23", "Construction", "TX", 2020, 7, True, None, None, None, None)


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(SMALL_NOT_SUPPRESSED, id="small-not-suppressed"),
        pytest.param(SUPPRESSED_WITH_FIGURE, id="suppressed-with-figure"),
        pytest.param(BIG_SUPPRESSED, id="big-suppressed"),
    ],
)
def test_export_refuses_a_row_that_breaks_the_small_cell_rule(tmp_path, monkeypatch, capsys, bad):
    out(tmp_path).parent.mkdir()
    out(tmp_path).write_text("previous export\n")
    fake_warehouse(monkeypatch, [BIG, bad])
    assert cli.main(["export", "--state-dir", str(tmp_path)]) == EXIT_UNSAFE
    assert "export refused" in capsys.readouterr().err
    assert out(tmp_path).read_text() == "previous export\n"
    assert [p.name for p in out(tmp_path).parent.iterdir()] == ["agg_industry_state_year.csv"]


def test_export_exits_locked_before_connecting(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli.warehouse, "connect", lambda: pytest.fail("connected while the lock was held")
    )
    with exclusive(tmp_path):
        assert cli.main(["export", "--state-dir", str(tmp_path)]) == EXIT_LOCKED

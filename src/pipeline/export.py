"""The public CSV behind the Tableau Public chart (ADR 0002: aggregates only, small cells withheld)."""

import csv
import os
import tempfile
from pathlib import Path

EXIT_UNSAFE = 5
SMALL_CELL = 3  # same threshold as dbt/models/marts/agg_industry_state_year.sql
MEASURES = ("case_violations", "employees_due_back_wages", "back_wages_agreed", "cmp_assessed")


class ExportError(Exception):
    exit_code = EXIT_UNSAFE


def check_small_cells(header: list[str], rows: list[tuple]) -> None:
    """Re-check the small-cell rule on the exact rows being published; the dbt test may not have run."""
    col = {name: i for i, name in enumerate(header)}
    missing = {"cases", "is_suppressed", *MEASURES} - col.keys()
    if missing:
        raise ExportError(f"export refused: columns missing from the aggregate: {sorted(missing)}")
    for row in rows:
        suppressed = row[col["is_suppressed"]]
        if (row[col["cases"]] < SMALL_CELL) != suppressed:
            raise ExportError(f"export refused: cell {row[:4]} has is_suppressed={suppressed}")
        if suppressed and any(row[col[m]] is not None for m in MEASURES):
            raise ExportError(f"export refused: suppressed cell {row[:4]} carries a measure")


def write_csv(header: list[str], rows: list[tuple], path: Path) -> None:
    """Write via a temp file and rename, so a failed run leaves the previous file intact."""
    path.parent.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

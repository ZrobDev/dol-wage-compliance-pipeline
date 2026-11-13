import argparse
import logging
import os
import sys
from pathlib import Path

import httpx

from pipeline import warehouse
from pipeline.ingest import IngestError, resolve_since, run


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("snowflake.connector").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    ingest = subcommands.add_parser("ingest")
    ingest.add_argument(
        "--full",
        action="store_true",
        help="ignore the load_dt watermark and pull every record; an interrupted full run "
        "resumes from its checkpoint (delete state/whd_checkpoint.json to start from zero)",
    )
    ingest.add_argument("--state-dir", type=Path, default=Path("state"))
    ingest.add_argument("--page-pause", type=float, default=3.0)
    ingest.add_argument(
        "--defer-load",
        action="store_true",
        help="write every page to disk first and load them in one COPY at the end; use it for "
        "a backfill, where a COPY per page keeps the warehouse awake for hours",
    )
    load = subcommands.add_parser(
        "load", help="load every page file in the state dir that Snowflake has not loaded yet"
    )
    load.add_argument("--state-dir", type=Path, default=Path("state"))
    args = parser.parse_args(argv)

    if args.command == "load":
        conn = warehouse.connect()
        try:
            files, loaded = load_pending(conn, args.state_dir)
        finally:
            conn.close()
        print(f"files={files} newly_loaded_rows={loaded}")
        return 0

    if "DOL_API_KEY" not in os.environ:
        raise SystemExit("DOL_API_KEY is required")
    conn = warehouse.connect()
    try:
        since = resolve_since(args.state_dir, args.full, lambda: warehouse.watermark(conn))
        try:
            with httpx.Client(timeout=120) as client:
                pages, fetched, loaded = run(
                    client,
                    api_key=os.environ["DOL_API_KEY"],
                    state_dir=args.state_dir,
                    since=since,
                    load_page=(lambda page: 0) if args.defer_load else warehouse.make_loader(conn),
                    page_pause=args.page_pause,
                )
        except IngestError as error:
            print(error, file=sys.stderr)
            if args.defer_load:  # whatever was fetched before the error still gets loaded
                _, partial = load_pending(conn, args.state_dir)
                print(f"loaded {partial} rows fetched before the error", file=sys.stderr)
            return 2
        if args.defer_load:
            # Every page on disk that Snowflake lacks, including pages from an earlier run that
            # was interrupted, so a resumed --defer-load never leaves fetched pages behind.
            _, loaded = load_pending(conn, args.state_dir)
    finally:
        conn.close()

    print(f"pages={pages} fetched={fetched} loaded={loaded} since={since or 'full'}")
    if args.defer_load:
        # load_pending raises if COPY fails. Its row count can sit below or above `fetched`:
        # COPY skips re-fetched identical pages, and it also loads pages left by earlier runs.
        return 0
    return 0 if loaded >= fetched else 1


def load_pending(conn, state_dir: Path) -> tuple[int, int]:
    pages = sorted((state_dir / "pages").glob("whd_*.json.gz"))
    try:
        return len(pages), warehouse.load_pages(conn, pages, force=False)
    except Exception:
        print(
            f"Loading failed; the {len(pages)} page files are kept in {state_dir}/pages. "
            "Fix the cause, then run `pipeline load`.",
            file=sys.stderr,
        )
        raise

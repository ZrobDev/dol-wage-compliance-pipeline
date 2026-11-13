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
    ingest.add_argument("--full", action="store_true")
    ingest.add_argument("--state-dir", type=Path, default=Path("state"))
    ingest.add_argument("--page-pause", type=float, default=3.0)
    args = parser.parse_args(argv)

    if "DOL_API_KEY" not in os.environ:
        raise SystemExit("DOL_API_KEY is required")
    conn = warehouse.connect()
    try:
        since = resolve_since(args.state_dir, args.full, lambda: warehouse.watermark(conn))
        with httpx.Client(timeout=120) as client:
            pages, fetched, loaded = run(
                client,
                api_key=os.environ["DOL_API_KEY"],
                state_dir=args.state_dir,
                since=since,
                load_page=warehouse.make_loader(conn),
                page_pause=args.page_pause,
            )
    except IngestError as error:
        print(error, file=sys.stderr)
        return 2
    finally:
        conn.close()

    print(f"pages={pages} fetched={fetched} loaded={loaded} since={since or 'full'}")
    return 0 if fetched == loaded else 1

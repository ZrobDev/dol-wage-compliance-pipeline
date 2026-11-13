import os
from collections.abc import Callable
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def connect():
    private_key = serialization.load_pem_private_key(
        _required("SNOWFLAKE_PRIVATE_KEY").encode(), password=None
    )
    return snowflake.connector.connect(
        account=_required("SNOWFLAKE_ACCOUNT"),
        user=_required("SNOWFLAKE_USER"),
        private_key=private_key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        authenticator="SNOWFLAKE_JWT",
        role="WHD_PIPELINE",
        warehouse="WHD_WH",
        database="WHD",
        schema="RAW",
    )


def watermark(conn) -> str | None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT TO_VARCHAR(MAX(payload:load_dt::TIMESTAMP_NTZ), "
            "'YYYY-MM-DD\"T\"HH24:MI:SS') FROM WHD.RAW.WHD_ENFORCEMENT"
        )
        row = cursor.fetchone()
    return row[0] if row else None


def load_pages(conn, paths: list[Path], *, force: bool) -> int:
    """PUT the page files to the stage, then COPY them in as few statements as possible.

    PUT runs on the client and needs no warehouse; only COPY wakes WHD_WH, so loading many
    pages in one COPY costs about a minute of warehouse time instead of one wake per page.
    force=True always loads (so loaded == fetched); force=False lets COPY's load history skip
    files it has already loaded, which makes `pipeline load` safe to rerun.
    """
    rows = 0
    with conn.cursor() as cursor:
        for path in paths:
            absolute_path = path.resolve().as_posix().replace("'", "\\'")
            cursor.execute(
                f"PUT 'file://{absolute_path}' @WHD.RAW.WHD_STAGE/whd/ "
                "AUTO_COMPRESS=FALSE SOURCE_COMPRESSION=GZIP OVERWRITE=TRUE"
            )
        for start in range(0, len(paths), 1000):  # COPY accepts at most 1,000 FILES
            names = ", ".join(f"'{path.name}'" for path in paths[start : start + 1000])
            cursor.execute(
                "COPY INTO WHD.RAW.WHD_ENFORCEMENT (payload, source_file, file_row) "
                "FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER "
                "FROM @WHD.RAW.WHD_STAGE/whd/) "
                f"FILES = ({names}) "
                "FILE_FORMAT = (TYPE = JSON STRIP_OUTER_ARRAY = TRUE COMPRESSION = GZIP) "
                f"FORCE = {'TRUE' if force else 'FALSE'}"
            )
            columns = [column.name.lower() for column in cursor.description]
            if "rows_loaded" in columns:  # with nothing new to load, COPY returns only a status
                index = columns.index("rows_loaded")
                rows += sum(int(row[index]) for row in cursor.fetchall())
    return rows


def make_loader(conn) -> Callable[[Path], int]:
    # FORCE: a resumed or repeated page always lands, so loaded == fetched holds.
    # Raw is append-only; staging keeps the newest row per case_id.
    return lambda path: load_pages(conn, [path], force=True)

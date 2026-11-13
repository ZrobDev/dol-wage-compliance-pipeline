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


def make_loader(conn) -> Callable[[Path], int]:
    def load_page(path: Path) -> int:
        absolute_path = path.resolve()
        with conn.cursor() as cursor:
            cursor.execute(
                f"PUT 'file://{absolute_path}' @WHD.RAW.WHD_STAGE/whd/ "
                "AUTO_COMPRESS=FALSE SOURCE_COMPRESSION=GZIP OVERWRITE=TRUE"
            )
            cursor.execute(
                "COPY INTO WHD.RAW.WHD_ENFORCEMENT (payload, source_file, file_row) "
                "FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER "
                "FROM @WHD.RAW.WHD_STAGE/whd/) "
                f"FILES = ('{path.name}') "
                "FILE_FORMAT = (TYPE = JSON STRIP_OUTER_ARRAY = TRUE COMPRESSION = GZIP)"
            )
            # An already-loaded file returns one status column and no rows_loaded.
            columns = [column.name.lower() for column in cursor.description]
            if "rows_loaded" not in columns:
                return 0
            index = columns.index("rows_loaded")
            return sum(int(row[index]) for row in cursor.fetchall())

    return load_page

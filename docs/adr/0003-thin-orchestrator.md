# 0003: A thin ingest CLI now; orchestration comes in M2

- Status: accepted
- Date: 2026-11-12

## Context

M1 has to prove the data path end to end: API, then raw, then dbt, then a chart. Airflow with Cosmos fits on the homelab; experiment E3 measured its peak memory at 1.98 GiB. But orchestration adds a deployment surface before the data path itself is proven.

## Decision

- **Ingest is one command,** `pipeline ingest`. It is a small Python CLI using httpx and the Snowflake connector, and it keeps its state in a local checkpoint file plus the warehouse.
- **Behavior the CLI owns:**
  - backoff on 429, for an undocumented quota of about 10 requests per 15 minutes, with no `Retry-After` header;
  - 1,500-row pages, under the API's 6 MB response cap;
  - a resumable offset checkpoint;
  - the `load_dt` watermark, read from Snowflake, for incremental runs;
  - key redaction, because the API takes its key only in the query string.
- **Behavior the orchestrator will own** (Airflow in M2): scheduling, retries across runs, and alerting.

## Consequences

- M2 wraps `pipeline ingest` and `dbt build` as tasks, and does not rewrite them.
- Two things M2 must handle:
  - **A durable state directory.** The checkpoint must survive between runs, or an interrupted backfill restarts from the watermark.
  - **Logging.** Airflow's logging setup must not reset the httpx logger to INFO, because httpx would then log the key-bearing URL. M2 adds a log filter that scrubs the key.
- A full backfill takes about 6 hours, bound by the API quota, not by Snowflake.

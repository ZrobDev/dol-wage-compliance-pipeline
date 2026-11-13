# E3: Airflow 3 + Cosmos + dbt memory test (2026-11-07)

A one-day experiment, kept as a record. It answered one question: does Airflow 3 with Cosmos and dbt fit in a 4 GiB container? `stats.csv` holds the samples taken every 30 s by `sample.sh`.

Do not reuse `compose.yaml` as it stands. It uses default throwaway credentials in `environment:` and was run on a container destroyed the same day. The only published port is bound to `127.0.0.1`. The M3 compose file will use Compose secrets mounted at `/run/secrets/<name>`.

Finding carried forward: Cosmos must use `LoadMode.DBT_MANIFEST`.

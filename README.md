# dol-wage-compliance-pipeline

A data pipeline over the U.S. Department of Labor Wage and Hour Division (WHD) enforcement data: which industries and states see wage-law violations, how much back pay is owed, and how that changes over time.

**Status: M0 (de-risk experiments) done. M1 (thin slice) not started.** Nothing in this repo runs end to end yet.

## Planned architecture

```
DOL WHD API (API key, 429 backoff, resumable offset, load_dt watermark)
  -> Python ingest (uv, httpx, pytest)
  -> Snowflake raw   (M1: internal stage; M3: S3 landing + storage integration)
        dbt: staging (unpivot per-act columns) -> marts
             star schema: fct_compliance_actions, dim_industry, dim_state, dim_date
             tests, source freshness, docs site
        Airflow 3 (LocalExecutor) + Cosmos (LoadMode.DBT_MANIFEST)                [M2]
        Terraform (AWS + Snowflake), GitHub OIDC, S3 landing                     [M3]
        public_export mart (aggregates only) -> Google Sheet -> Tableau Public   [M4]
```

Parked until M1-M4 are done: a second source (BLS QCEW, joined through a ZIP -> county crosswalk).

## Milestones

| Milestone | Scope |
|---|---|
| M1 | Thin slice: one source -> warehouse raw -> 3-5 dbt models with tests and docs -> one chart. Runs locally. |
| M2 | Orchestration with Airflow and Cosmos. |
| M3 | Terraform, CI and the S3 landing zone. |
| M4 | Public layer: aggregates-only export, Tableau Public, dbt docs. |

## What is here now

- `docs/reference/whd_enforcement_metadata.json`: the WHD enforcement column dictionary (110 variables), from the DOL API.
- `experiments/e3-airflow-cosmos/`: a one-day experiment that measured Airflow 3 + Cosmos + dbt memory use. See its README before reusing anything.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.13 is pinned in `.python-version`).
- A free DOL API key from the [DOL Open Data Portal](https://dataportal.dol.gov/).
- A Snowflake account (Standard edition is enough). Run `infra/snowflake/bootstrap.sql` once as ACCOUNTADMIN: it creates a resource monitor capped at 2 credits a month, an XS warehouse, the `WHD` database (`RAW`, `STAGING`, `MARTS`), the `WHD_PIPELINE` role and a key-pair service user.
- Runtime variables, injected by a secrets manager: `DOL_API_KEY`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (PKCS#8 PEM).

## Secrets

No secret lives in this repo. Runtime keys are read from a secrets manager at run time; `.env` files are git-ignored.

## License

MIT. See `LICENSE`.

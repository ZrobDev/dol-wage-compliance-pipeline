# dol-wage-compliance-pipeline

A data pipeline over the U.S. Department of Labor Wage and Hour Division (WHD) enforcement data: which industries and states see wage-law violations, how much back pay is owed, and how that changes over time.

**Status: M0 (de-risk experiments) done. M1 (thin slice) not started.** Nothing in this repo runs end to end yet.

## Planned architecture

```
DOL WHD API (API key, 429 backoff, resumable offset, load_dt watermark) -+  Python ingest (uv, httpx, pytest)
BLS QCEW CSV (keyless; ZIP -> county crosswalk)                    [M3] -+-> S3 landing -> Snowflake raw
        dbt: staging (unpivot per-act columns) -> intermediate -> marts
             star schema: fct_compliance_actions, dim_industry, dim_state, dim_date
             tests, source freshness, docs site
        Airflow 3 (LocalExecutor) + Cosmos (LoadMode.DBT_MANIFEST)                [M3]
        Terraform (AWS + Snowflake), GitHub OIDC                                 [M2]
        public_export mart (aggregates only) -> Google Sheet -> Tableau Public   [M4]
```

## Milestones

| Milestone | Scope |
|---|---|
| M1 | Thin slice: one source -> warehouse raw -> 3-5 dbt models with tests and docs -> one chart. Runs locally. |
| M2 | Terraform and CI. |
| M3 | Orchestration with Airflow and Cosmos; second source and the join. |
| M4 | Public layer: aggregates-only export, Tableau Public, dbt docs. |

## What is here now

- `docs/reference/whd_enforcement_metadata.json`: the WHD enforcement column dictionary (110 variables), from the DOL API.
- `experiments/e3-airflow-cosmos/`: a one-day experiment that measured Airflow 3 + Cosmos + dbt memory use. See its README before reusing anything.

## Secrets

No secret lives in this repo. Runtime keys are read from a secrets manager at run time; `.env` files are git-ignored.

## License

MIT. See `LICENSE`.

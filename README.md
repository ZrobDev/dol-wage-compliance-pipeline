# dol-wage-compliance-pipeline

A data pipeline over the U.S. Department of Labor Wage and Hour Division (WHD) enforcement data. It answers three questions: which industries and states see wage-law violations, how much back pay is owed, and how that changes over time.

**Status: M1 (thin slice) done, except the published chart.**
- **Data loaded:** every WHD enforcement case (370,964 cases, FY2005 onward).
- **Models:** a deduplicated staging layer and a star schema, 41 dbt tests.
- **Public output:** one public aggregate and one chart. Next is M2: orchestration with Airflow.

## Architecture

```
DOL WHD API  (key in the query string, 6 MB response cap, ~10 requests per 15 min)
  -> pipeline ingest   Python + httpx: 1,500-row pages, 429/5xx backoff, resumable checkpoint,
                       load_dt watermark, key redaction; --defer-load for backfills
  -> Snowflake RAW     internal stage, PUT + COPY into one VARIANT column (append-only)
  -> dbt staging       base_whd__enforcement (newest version per case)
                       stg_whd__cases, stg_whd__case_acts (28 acts unpivoted)
  -> dbt marts         dim_industry, dim_state, dim_date, fct_compliance_actions (case x act)
                       agg_industry_state_year  (public: aggregates only, small cells suppressed)
  -> Google Sheet -> Tableau Public
```

Decisions are recorded in `docs/adr/`:
- **0001:** Snowflake as the warehouse, loaded through an internal stage.
- **0002:** the public export holds aggregates only, under a small-cell rule.
- **0003:** a thin ingest CLI now, with orchestration in M2.

## What the data says about itself

Measured on the full load:
- **Unmapped NAICS codes: 3.04% of cases.** Mostly WHD's own `09xxx` codes, which are not valid NAICS, plus missing codes. They are kept as `UNMAPPED`, not hidden.
- **Per-act rows add up to the case totals in 99.27% of cases.** The act rows never sum above the case total, so the acts don't overlap. In the other 2,690 cases (0.73%), the case total is higher: the source records violations that no act column carries, mostly in findings ending 2020–2022. The test `assert_case_acts_reconcile_violations` warns on them; a count well above 2,690 would point to an unpivot bug.
- **Some cases concluded after FY2005 have findings periods that ended as early as 1984.** `dim_date` therefore starts in 1980. One record has a findings end date in the year 3021, after the record was even published; staging nulls any findings date later than the record's `load_dt`.
- **Small-cell rule:** a sector × state × year cell with fewer than 3 cases publishes its case count only. 31.4% (6,343 of 20,191) of cells are suppressed.

## Cost

Snowflake Standard on AWS us-east-1, at $2.00 per credit, with an XS warehouse that suspends after 60 seconds.

| Run | Credits | Dollars |
|---|---|---|
| One full `dbt build` (8 models, 2 seeds, 41 tests; 23 s) | ~0.02 (estimate) | ~$0.05 |
| Bulk load of the full backfill (248 files, one pass; 2 min 10 s) | ~0.05 (estimate) | ~$0.10 |
| Monthly caps (resource monitors) | 2 for the pipeline warehouse, 3 for the account | $4 / $6 |

Measured on the resource monitor: the bulk load, three full builds, the checks and the export together used 0.18 credits ($0.36), about 11 minutes of XS time. The monitor can't split one run from the next, so the per-run figures are runtime × 1 credit per hour, plus the 60-second suspend tail.

Loading a backfill one page per COPY kept the warehouse awake about a third of the time, and nearly used up the monthly cap in two hours. `pipeline ingest --defer-load` loads all pages in one pass instead.

## Running it

Prerequisites:
- [uv](https://docs.astral.sh/uv/) (Python 3.13 is pinned in `.python-version`).
- A free DOL API key from the [DOL Open Data Portal](https://dataportal.dol.gov/).
- A Snowflake account. Run `infra/snowflake/bootstrap.sql` once as ACCOUNTADMIN; it is idempotent.
- Runtime variables, injected by a secrets manager: `DOL_API_KEY`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (PKCS#8 PEM).

```
uv run pytest                                    # offline, no credentials
uv run pipeline ingest --full --defer-load       # first backfill (~6 h, bound by the API quota)
uv run pipeline ingest                           # later runs: only records past the load_dt watermark
uv run pipeline load                             # load any page files left on disk
uv run dbt build --project-dir dbt --profiles-dir dbt
```

CI runs ruff, pytest, `dbt parse` and gitleaks on every pull request. None of these need credentials.

## Chart

Pending: the Tableau Public link goes here once the aggregate is published. The chart reads `agg_industry_state_year` (sector × state × fiscal year, small cells suppressed), exported to a Google Sheet.

## Milestones

| Milestone | Scope | Status |
|---|---|---|
| M1 | One source, then warehouse raw, then dbt staging and marts with tests and docs, then one chart. Runs locally. | done |
| M2 | Orchestration with Airflow 3 and Cosmos on the homelab. | next |
| M3 | Terraform, CI with Snowflake auth, the S3 landing zone, least-privilege roles, a network policy. | |
| M4 | The public layer: the export, Tableau Public, the dbt docs site. | |

Parked until M4 is done: a second source, BLS QCEW, joined through a ZIP-to-county crosswalk.

## Secrets

No secret lives in this repo. Keys are read from a secrets manager at run time, and `.env` files are git-ignored.

## License

MIT. See `LICENSE`.

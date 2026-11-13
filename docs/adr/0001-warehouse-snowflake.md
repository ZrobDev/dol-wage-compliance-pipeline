# 0001: Snowflake as the warehouse, loaded through an internal stage

- Status: accepted
- Date: 2026-11-12

## Context

The pipeline needs a SQL warehouse that dbt targets well. It should also be the one that data-engineering job postings in finance and insurance ask for most. A scan of those postings found Snowflake in about 61% and BigQuery in about 9%. The source is small: about 370,000 rows, published quarterly. Cost matters more than scale.

## Decision

- **Warehouse:** Snowflake Standard edition on AWS us-east-1, at $2.00 per credit.
- **Cost controls:** one XS warehouse that suspends itself after 60 seconds, with a 10-minute statement timeout. A resource monitor caps it at 2 credits a month, and a second, account-wide monitor caps everything at 3 credits a month.
- **Loading:** M1 loads through a Snowflake *internal* stage (`PUT`, then `COPY INTO`). There is no S3 bucket or AWS account yet; S3 and the storage integration arrive with Terraform in M3.
- **One role for M1:** a single `WHD_PIPELINE` role owns `RAW`, `STAGING` and `MARTS`. It is split into loader, transformer and reader roles in M3.
- **Authentication:** a `TYPE = SERVICE` user with key-pair auth. The private key lives only in the secrets manager.

## Consequences

- One full `dbt build` costs a fraction of a credit (measured in the README), so the cap leaves room for dozens of builds a month.
- Raw is append-only. The loader uses `COPY ... FORCE = TRUE`, so a resumed or repeated page always lands and the fetched and loaded counts always match. Staging keeps the newest row per case.
- A leaked service key works from any IP until M3 adds a network policy. The key-rotation steps are documented in `infra/snowflake/bootstrap.sql`.

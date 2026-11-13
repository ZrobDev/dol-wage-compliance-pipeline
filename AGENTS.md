# dol-wage-compliance-pipeline: agent instructions

## Project overview

A portfolio data pipeline over DOL Wage and Hour Division enforcement data. This repo will be public. Status and architecture are in `README.md`.

`AGENTS.md` is the canonical instruction file; `CLAUDE.md` is a relative symlink to it. Edit `AGENTS.md` only.

## Rules specific to this repo

- This repo is public or about to be. No employer or client name, data or document enters it, in code, fixtures, comments, commit messages or retros.
- The public export holds aggregates only, never row-level records.
- Pin every dependency version, and choose versions at least two weeks old.
- Work goes in through PRs once the GitHub repo exists.
- Secrets come from the secrets manager at run time. Never commit a key; never print one.

## Testing

`uv run pytest` runs offline on synthetic fixtures, no credentials needed; `doppler run -p data-projects -c prd -- uv run pipeline ingest` loads the raw table; `uv run ruff check . && uv run ruff format --check .`.

`doppler run -p data-projects -c prd -- uv run dbt build --project-dir dbt --profiles-dir dbt` builds and tests every model against Snowflake.

## Memory

- `docs/retro/` — one retro per session, newest first; read the newest before host work.

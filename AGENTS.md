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
- A backfill or any re-pull uses `pipeline ingest --defer-load` (one COPY at the end). A COPY per page wakes the warehouse for its 60-second minimum each time; on the 6-hour backfill that used 0.93 of the 2-credit monthly cap in two hours.
- A data-quality number written into docs, a test comment or a PR (a share, a count, "100%") comes from a query over the full load. A number measured on partial data says "partial" next to it: the reconcile rate read 100% at 150k rows and 99.27% at 371k.
- `.gitignore` is the one list of what must never be committed, and `tests/test_repo_hygiene.py` fails if any file it excludes is tracked. Before committing, read `git status --short`; an untracked file you did not write on purpose goes into `.gitignore`, not into the commit.

## Testing

`uv run pytest` runs offline on synthetic fixtures, no credentials needed; `doppler run -p data-projects -c prd -- uv run pipeline ingest` loads the raw table; `uv run ruff check . && uv run ruff format --check .`.

`doppler run -p data-projects -c prd -- uv run dbt build --project-dir dbt --profiles-dir dbt` builds and tests every model against Snowflake.

## Memory

- `docs/retro/` — one retro per session, newest first; read the newest before host work.

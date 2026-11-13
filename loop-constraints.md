# Loop constraints

Binding rules for autonomous and delegated work in this repo. The path denylist is in `gate.yaml`.

- Never commit or print a secret. Keys come from Doppler (`data-projects` / `prd`) at run time; a secret entered by a person goes in over stdin at a hidden prompt, followed by a sha256 compare.
- Never commit anything under `state/`: it holds raw API pages, which are row-level records.
- The public aggregate stays aggregates-only. Any change to `agg_industry_state_year` keeps `tests/assert_small_cells_withhold_measures.sql` passing; changing the small-cell threshold is the owner's decision.
- All Snowflake work targets account DOL_WAGE; never create or change anything in any other account.
- Statements that need ACCOUNTADMIN go to the owner as a reviewed file or worksheet; the agent never holds that role.
- Never weaken, skip or delete a test to make a gate pass. A test replaced by a stronger one is named as such in the PR.
- Every guard gets broken once, with the mutation confirmed to have matched, before it is trusted; then restore it and clear `__pycache__`.
- Pins stay exact and at least two weeks old (`exclude-newer` in `pyproject.toml`, action SHAs in `.github/workflows/`).
- Work lands through PRs. The owner merges; the agent never merges or force-pushes `main`.
- A long API run (a backfill takes about 6 hours) runs in the background and resumes from its checkpoint; never restart it from zero without saying so.
- Attempt caps: 3 tries on the same failing item, then stop and report.

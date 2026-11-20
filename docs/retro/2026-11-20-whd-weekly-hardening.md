# Retro: whd-weekly-hardening

- Date: 2026-11-20
- Repo: ZrobDev/dol-wage-compliance-pipeline · Branch: main (PRs #19–#27) · Range: a340319..3a93b0b (26 commits since 2026-11-14)
- Previous: [2026-11-14-m2-airflow-secrets.md](2026-11-14-m2-airflow-secrets.md)
- Backlog: no

## State
Checked during the session (CT 121 SSH needed a Tailscale re-auth at retro time; the re-check is in the Verification loop):
- #19 ingest: HTTP 204 is an empty page — merged — live on CT 121
- #20 ingest: broken-filter canary, incremental runs restart at offset 0, one retry layer, `--empty-exit-code` — merged — live; `dags test` on a quiet week: ingest and all 20 dbt tasks skipped
- #21 → #22 healthchecks.io pings (`ping_ok`/`ping_fail`), `drift` task, image `REVISION`, `deploy.sh` — #21 merged into a dead base; landed through #22 — live
- #23 `deploy.sh` ERR trap with `set -E`, waits for the scheduler — merged — first clean run on the #27 deploy (`deploy: ok 3a93b0b`)
- #24, #25 first measured run cost, 0.11 credits; "keep paused" item closed — merged (a parallel session) — docs
- #26 ping/drift `retry_delay` 1 min — merged — live
- #27 ping errors name the HTTP status — merged — live at `3a93b0b`
- healthchecks.io: `whd-weekly` and `whd-drift` up (API, 05:14 UTC). The failure path was tested: `ping_fail` turned the check down, the Slack alert arrived, and `ping_ok` brought it back up
- `whd_weekly` paused (operator, 2026-11-20); next schedule `0 6 * * 1` UTC once unpaused

## Deviations
| Plan said | What was done | Why | Asked |
|---|---|---|---|
| Plan v1: an end probe for a 500 after a full page (item 1) | Dropped; the code has a ceiling comment instead | DOL loads about quarterly, so the exact-multiple-of-1,500 case is about 1 in 1,500 per load, and a probe can't tell "past the end" apart from "this page is broken" | yes (critique round) |
| Plan v1: exit code 5 and a Python-task wrapper; n8n webhook, Data Table, watch workflow | One retry layer and `BashOperator`; healthchecks.io for the alerts; drift checked in the DAG | Critique: a subprocess orphan could hold the lock; a watcher on meanvps shares its failure domain; Airflow 3 callbacks run in the dag-processor, which has no secrets | yes |
| Plan v2: a `ping_start` (`/start`) task | Not built | The grace period already flags a hung run | no (reported in #21) |
| Plan v2: `deploy.sh` runs the README verify block | It checks the label, the secret mount and the import errors, not the env-leak loop | Kept the script short | no (reported after) |
| Tests unchanged except the new ones | `test_fetch_page_redacts_key_everywhere` now passes a no-op `sleep`; assertions unchanged | Transport errors now retry, so the real sleep hung the suite | no (reported in #20) |
| Plan v2: two PRs, A then B | Four more: #22 re-landed #21; #23, #26 and #27 fixed live findings | #21 merged into a dead base; the first deploy and test surfaced three bugs | no (each reported as found) |

## Owed
- [ ] operator: unpause `whd_weekly` when ready (`airflow dags unpause whd_weekly` in the scheduler) — first scheduled run; healthchecks.io alerts if it fails or never reports
- [ ] operator, optional: delete and recreate both healthchecks.io checks with the same slugs, schedule and grace — retires the UUID ping URLs exposed in a screenshot on 2026-11-20
- [x] agent: `infra/airflow/README.md:73` names the operator's SSH alias in a public repo (added in #21); use `ssh <host>` as line 55 does — the identity gate flagged the same alias in this retro — done in the retro-apply PR, also `deploy.sh:4`
- [ ] operator: delete the merged remote branches `feat/healthchecks-drift-deploy` (#21) and `feat/m2-durable-state` (#16) — not named in the cleanup request, so left in place; auto-delete is now on for future merges

## Verification loop
```bash
uv run pytest -q                                                                   # 70 passed
k=$(doppler secrets get HC_API_KEY_RO -p data-projects -c prd --plain | tr -d '\n'); curl -sS -H "X-Api-Key: $k" https://healthchecks.io/api/v3/checks/ | jq -r '.checks[] | "\(.slug) \(.status)"'; unset k   # whd-weekly up, whd-drift up (or paused/new if the DAG has been paused for weeks)
ssh -n <airflow-host> 'cd /opt/dol-wage-compliance-pipeline/infra/airflow && doppler run -- docker compose exec -T airflow-scheduler airflow dags list-import-errors -o json 2>/dev/null | tail -1'   # []
gh repo view --json deleteBranchOnMerge --jq .deleteBranchOnMerge                  # true
```

## Failure modes
| What broke | Where it hid | Root cause | Check that now forces it |
|---|---|---|---|
| `whd_weekly` failed on a week with no new rows; every dbt task was `upstream_failed` | `src/pipeline/ingest.py` `fetch_page` | The API answers 204 when the `load_dt` filter matches nothing; only 200 and the retryable codes were accepted | `uv run pytest -q tests/test_ingest.py -k 204` |
| A broken filter would have looked like a quiet week forever once 204 meant success | #19 on its own | DOL loads about quarterly, with gaps up to 26 weeks, so a time threshold can't tell the two apart | `uv run pytest -q tests/test_cli.py -k broken_filter` |
| #21 merged but never reached `main` | GitHub stacked PR base `fix/ingest-hardening` | `deleteBranchOnMerge=false`, so merging #20 left the base in place and #21 was never retargeted | `gh repo view --json deleteBranchOnMerge --jq .deleteBranchOnMerge` → `true` |
| `deploy.sh` stopped after `up -d` with no message | `infra/airflow/deploy.sh`, import-errors check | stderr went to `/dev/null`; `set -e` exited quietly inside `main()`, and an ERR trap needs `-E` to fire in functions | `grep -c 'set -Eeuo pipefail' infra/airflow/deploy.sh` → 1 |
| A manual `dags test` hung 20 min per ping attempt | `airflow/dags/whd_weekly.py` ping tasks | They inherited the DAG's `retry_delay=20 min`, which is meant for a killed ingest | `grep -c 'PING_RETRY' airflow/dags/whd_weekly.py` → 4 |
| Pings failed as a bare `HTTPError`; the cause took two operator round trips | `WHD_PING_BASE` held a check UUID, then the checks had no slugs (404) | The secret's shape and the slugs weren't checked before the first deploy that needed them; the error hid the status | API: `curl -sS -H "X-Api-Key: $k" https://healthchecks.io/api/v3/checks/ \| jq -r '.checks[] \| "\(.slug) \(.slug\|length)"'` → both checks, length > 0. Before the first deploy only: probe the ping URL from the scheduler (`curl -sS -o /dev/null -w '%{http_code}' "$(cat /run/secrets/whd_ping_base)/whd-weekly"` → `200`) — it sends a real success ping, so never in a routine audit |

## Process lessons
- Evidence: failure-mode row 3. Rule: before stacking PR B on A, `gh repo view --json deleteBranchOnMerge` must print `true`; otherwise open B against `main` after A merges, and before each merge `gh pr view <n> --json baseRefName -q .baseRefName` prints `main`. Scope: global-candidate.
- Evidence: failure-mode row 6. Rule: before the first deploy that depends on an external check service, probe the exact URL from the host that will call it, printing only the HTTP code, and list the service's view of the target (here: the API's `slug` field). Scope: project.
- Evidence: failure-mode row 4, #23. Rule: a shell guard that can exit non-zero gets `set -E` plus an ERR trap that names the command; break it once with a failing `$(…)` inside a function and confirm the message appears. Scope: global-candidate.

## Decisions
- Kept: Airflow does the data work and alone holds the Snowflake and DOL credentials; n8n gets nothing from this pipeline — grilling Q5, then the critique (plan `generic-snuggling-hellman.md`)
- Reversed: n8n webhook, Data Table and watch workflow for alerts → healthchecks.io `whd-weekly`/`whd-drift`, pinged by plain tasks — outside the homelab and meanvps failure domain; Airflow 3 callbacks run in the dag-processor, which has no secrets (#21)
- Kept: drift counts only image paths (`whd_ping.IMAGE_PATHS`); docs-only commits are not drift — 17 of the first 45 commits were docs only (#21)
- Dropped: the 500 end probe (item 1) and exit code 5 — about 1 in 1,500 per load; one retry layer makes the code moot (#20)
- Kept: the watermark stays in Snowflake; no local cache — about 0.07 credits a month for quiet weeks (critique round)

## Memory proposals
| Action | Note | Reason |
|---|---|---|
| update | m1-api-limits.md | Add: 204 when a filter matches nothing; 500 past the end even when filtered; 401 for a bad key; `sort_by=load_dt&sort=desc` works (the canary); `/metadata` needs a key and offers no row count |
| new | dol-load-cadence.md | DOL loads WHD about quarterly (2–3k rows, gaps up to 26 weeks); most weekly runs fetch nothing. This drives the dbt skip and rules out time-based staleness alerts |
| new | whd-alerting-healthchecks.md | Checks `whd-weekly`/`whd-drift` work by slug under the project ping key (`WHD_PING_BASE`); verify through the API with `HC_API_KEY_RO` from Doppler; a check without a slug answers 404 |

Status: applied 2026-11-20

## Skill feedback
none

Status: applied 2026-11-20

## Graduation candidates
- Before stacking a PR, `gh repo view --json deleteBranchOnMerge` prints `true`, else open the child against `main` after the parent merges — test: 3 projects (entity-status-letter-ca 2026-10-30 #5–#7, omarchy-workstation-setup 2026-11-02 #84, dol-wage-compliance-pipeline 2026-11-20 #21) → pass — graduated 2026-11-20
- A shell guard that can exit non-zero gets `set -E` plus an ERR trap naming the command — test: 1 project (no prior retro or memory names a silent `set -e` exit in a function) → fails test

## Next session
1. `/retro apply` (memory proposals and the graduation candidate pending)
2. Verification loop
3. After the first scheduled run: read the healthchecks.io ping body and `WAREHOUSE_METERING_HISTORY` for the run

Suggested skills: retro

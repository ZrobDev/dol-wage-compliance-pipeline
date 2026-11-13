# Retro: m1-thin-slice

- Date: 2026-11-13
- Repo: ZrobDev/dol-wage-compliance-pipeline · Branch: docs/m1-adrs-readme · Range: 4f16163..39f1f70 (30 commits on main since 2026-11-12, plus open PRs #9 and #10)
- Previous: [2026-11-12-handoff-m1.md](2026-11-12-handoff-m1.md)
- Backlog: yes

## State
- #2 Snowflake bootstrap and pinned dependencies — merged — applied to the project Snowflake account by the owner
- #3 ingest client (backoff, resume, key redaction) — merged — runs locally
- #4 dbt staging — merged — built in `WHD.STAGING`
- #5 marts and the public aggregate — merged (before its review finished) — built in `WHD.MARTS`
- #6 marts review fixes (small-cell rule tested on values, grain and totals test) — merged — built
- #7 CI, `gate.yaml`, `loop-constraints.md`, MONITOR grant — merged — CI live; grant applied by the owner
- #8 CI canary — closed — proved CI goes red
- #9 bulk load (`--defer-load`, `pipeline load`, retry on 502/503/504, content-hashed pages) — open, CI green — its code loaded the full backfill
- #10 full-load fixes (findings dates bounded by `load_dt`, measured reconcile gap) — open — built on the full data: PASS 49, WARN 2, ERROR 0
- docs PR (ADRs 0001–0003, README, this retro) — local on `docs/m1-adrs-readme`
- Raw: 475,964 rows, 370,964 distinct cases = rows fetched; 248 page files
- Aggregate CSV for Tableau: `state/exports/agg_industry_state_year.csv` in the primary checkout (gitignored), 20,191 cells, 0 small cells with measures

## Deviations
| Plan said | What was done | Why | Asked |
|---|---|---|---|
| One PR for M1 (handoff) | Ten PRs (#2–#10) plus the docs PR | 10-file path gate; review per layer | yes (five); no (the four extra fix/CI PRs) |
| Key entered at a hidden prompt | Key piped from openssl into Doppler, sha256 matched, never printed | No person handles the key | yes |
| Account guard in `bootstrap.sql` | Guard moved to the bootstrap helper | Decided during #2; the helper runs the whole bootstrap | no |
| 10,000-row pages (E1 spike) | 1,500-row pages | API returns HTTP 413 above 6 MB (premise false) | no |
| One VARIANT row per page | One raw row per API record | VARIANT size limit; direct row count check | no |
| No macro listed | `generate_schema_name` macro added | marts would land in `STAGING_MARTS` | no |
| Ingest loads page by page | Backfill switched mid-run to fetch-only, then one bulk load | Per-page COPY used 0.93 of 2 credits in two hours | no |
| Review before merge on every PR | #5 merged before its review; fixes went into #6 | Owner merged while the review ran | no |
| No small-cell rule in plan | Cells under 3 cases publish the count only | Public aggregate could expose one employer | yes |
| ADR/README PR is PR 5 | It is the last PR, after #9 and #10 | Numbers needed the full load | no |
| Cost from `WAREHOUSE_METERING_HISTORY` | Read from the resource monitor | `WHD_PIPELINE` sees no metering rows | no |
| "Per-act rows reconcile in 100% of cases" (partial data) | 99.27% on full data | Premise false on the full load | no |

## Owed
- [ ] owner: merge #9, then #10, then the docs PR — puts the bulk load, the date fix and the docs on main
- [ ] owner: paste `state/exports/agg_industry_state_year.csv` into the Tableau Google Sheet, publish on Tableau Public, send the link — fills the README `Chart` section
- [ ] owner (ACCOUNTADMIN): cost-guard test — set `WHD_MONTHLY` quota below used credits, confirm `dbt build` fails, restore to 2
- [ ] owner: reply "yes hook" to open the fixed `guard-main-commit.sh` PR in omarchy-workstation-setup
- [ ] agent, after merges: `git worktree remove` for `dol-wage-dbt-marts`, `dol-wage-bulk`, `dol-wage-fulldata`, `dol-wage-docs` (state/pages in the marts worktree is no longer needed once raw is verified)

## Verification loop
```bash
git fetch origin && git log --oneline -1 origin/main      # merge of the docs PR
uv run pytest -q                                          # 19 passed (after #9)
uv run ruff check . && uv run ruff format --check .       # clean
doppler run -p data-projects -c prd -- uv run dbt build --project-dir dbt --profiles-dir dbt   # PASS 49 WARN 2 ERROR 0
```

## Failure modes
| What broke | Where it hid | Root cause | Check that now forces it |
|---|---|---|---|
| Per-page COPY kept the XS warehouse awake ~1/3 of a 6 h backfill; 0.93 of 2 credits in 2 h | `warehouse.make_loader` per page | Each COPY wakes the warehouse with a 60 s minimum | `review: does a backfill run one COPY per page? use --defer-load` |
| Totals test failed on the full load | one record, findings end date 3021 | Typo outside `dim_date` dropped by the inner join | `tests/assert_aggregate_grain_and_totals.sql` (fails with the clamp removed) |
| "100% reconcile" claim measured on partial data | test comment, README draft | 2,690 non-additive cases appear only after offset ~150k | `review: is every data-quality number in docs measured on the full load?` |
| Deferred re-fetch exited 1 when COPY skipped unchanged pages | `cli.py` exit code | `loaded >= fetched` assumed every page loads | `test_defer_load_succeeds_when_copy_skips_identical_pages` |
| Two versions of one page could load in one COPY with tied `loaded_at` | `ingest.run` page write | Old versions stayed on disk | `test_run_writes_deterministic_pages_and_clears_checkpoint` |
| `dbt/.user.yml` committed | `git add -A` in a dbt worktree | Not git-ignored | `git check-ignore dbt/.user.yml` |
| #5 merged before its review finished | placeholder PR body | Nothing said "review pending" | `review: does the placeholder body say "review pending, do not merge"?` |
| Guard hook blocked commits in compound commands from a main-branch cwd | the workstation's main-branch commit guard hook | Checks session cwd, not `git -C` target | `review: commit with git -C <worktree> in its own command` |

## Process lessons
- Evidence: row 1, the 0.93-credit run. Rule: before a backfill, multiply loads by 60 s of warehouse time and compare with the monitor quota. Scope: global-candidate.
- Evidence: row 3. Rule: data-quality numbers in docs come from the full load; a partial-load number carries "partial" in the text. Scope: project.
- Evidence: #5/#6. Rule: placeholder PR bodies open with "Review pending — do not merge". Scope: project.

## Decisions
- Kept: Snowflake via internal stage, aggregates-only export, thin CLI orchestrator — ADRs 0001–0003 (handoff A1–A7)
- Kept: small-cell rule, cells under 3 cases publish the count only — owner choice, tested on values (#6)
- Kept: backfills use `--defer-load`; incremental runs load per page — cost (#9)
- Kept: findings dates after the record's `load_dt` become null — deterministic, unlike `current_date()` (#10 review)
- Kept: reconcile test stays a warning at 2,690 rows — the gap is in the source (#10)
- Dropped: opencode-go review lanes — subscription closed (memory `opencode-go-closed`)
- Deferred: durable state directory (item 6) to M2

## Memory proposals
| Action | Note | Reason |
|---|---|---|
| update | m1-api-limits.md | Add: full backfill is 370,964 rows; HTTP 502 occurs mid-run and is now retried |
| new | snowflake-cost-backfill.md | Per-COPY wake-ups cost; bulk load ~0.02–0.05 credits; monitor lags, pipeline role can't read metering |

Status: pending

## Skill feedback
none

## Graduation candidates
- Before a backfill, multiply loads by 60 s of warehouse time and compare with the quota — test: >1h: two-hour per-page run that used 0.93 credits, then a restart as fetch-only → pass

## Next session
1. `/retro apply` (memory proposals and the graduation candidate are pending)
2. Run the verification loop above
3. M2: Airflow 3 + Cosmos on the homelab; start with the durable state directory (deferred item 6)

Suggested skills: retro, delegate, finish-feature

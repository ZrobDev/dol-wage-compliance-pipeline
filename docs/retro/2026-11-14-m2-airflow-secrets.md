# Retro: m2-airflow-secrets

- Date: 2026-11-14
- Repo: ZrobDev/dol-wage-compliance-pipeline · Branch: main · Range: 0aa8d91..a340319 (6 commits; #15 and #16 merged since the previous retro, this session made no commits)
- Previous: [2026-11-13-m1-close-out.md](2026-11-13-m1-close-out.md)
- Backlog: no

## State
- #15 docs(retro): M1 close-out — merged — on main
- #16 feat: durable state directory and the Airflow 3 + Cosmos stack (M2) — merged — on main; not deployed (no homelab CT yet)
- Doppler `data-projects`/`prd`: four new secrets set from `openssl` over stdin, values never printed. Before: none of the four existed. Lengths from `doppler secrets get <NAME> --plain | wc -c`, run now:
  - `AIRFLOW_POSTGRES_PASSWORD` 65, `AIRFLOW_JWT_SECRET` 65, `AIRFLOW_API_SECRET_KEY` 65 (hex-32 plus the newline `--plain` adds)
  - `AIRFLOW_FERNET_KEY` 45; urlsafe-base64 decode gives 32 bytes
- Already in Doppler, confirmed by name only: `DOL_API_KEY`, `SNOWFLAKE_PRIVATE_KEY`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`
- 2026-11-15 re-check (second session, same task re-issued): all eight names present; lengths 65/65/65 and Fernet 45, decoding to 32 bytes. Nothing regenerated, no Doppler writes

## Deviations
| Plan said | What was done | Why | Asked |
|---|---|---|---|
| Pipe each value into `doppler secrets set <NAME> -p data-projects -c prd` | Same pipe, plus `set -o pipefail`, `--no-interactive` and stdout sent to `/dev/null` | A failing `openssl` must not write an empty value or open a prompt; the set's result table could show the value | no (reported after; the outcome is unchanged) |
| Set the four, then verify | Set `AIRFLOW_JWT_SECRET` first as a canary and read its stored length (`--json \| jq '[.. \| strings \| length]'` gave 64) before setting the other three | `wc -c` = 65 cannot tell a trimmed 64 plus a printed newline from a stored newline; fixing it afterwards would have meant overwriting | no (reported after) |
| Verify by length only | Also decoded the Fernet key and counted 32 bytes | Length alone does not prove the base64url is valid | no (reported after) |
| 2026-11-15: generate the four secrets | Nothing generated; the verification loop re-run only | All four already existed from 2026-11-14; the task said to stop rather than overwrite | yes (owner chose to keep them) |

## Owed
- [x] owner: create the homelab CT with `/srv/whd-state` mounted and marked, per `infra/airflow/README.md` "Host setup (once)" — done 2026-11-14 in the homelab repo (its 2026-11-14 retro); compose deploy at `a340319` on 2026-11-15, verify block all `ok` (recorded in "Host setup (once)" by #17)
- [x] owner: keep `whd_weekly` paused until the first run's cost is read off the `WHD_MONTHLY` resource monitor (`infra/airflow/README.md`, Deploy) — done 2026-11-20: first full run 0.11 credits from `WAREHOUSE_METERING_HISTORY` (#24), DAG unpaused

## Verification loop
```bash
doppler secrets -p data-projects -c prd --only-names | grep -cE 'AIRFLOW_(POSTGRES_PASSWORD|FERNET_KEY|JWT_SECRET|API_SECRET_KEY)'   # 4
for n in AIRFLOW_POSTGRES_PASSWORD AIRFLOW_JWT_SECRET AIRFLOW_API_SECRET_KEY; do doppler secrets get $n --plain -p data-projects -c prd | wc -c; done   # 65 65 65
doppler secrets get AIRFLOW_FERNET_KEY --plain -p data-projects -c prd | tr -d '\n' | basenc --base64url -d | wc -c   # 32
```

## Failure modes
none

## Process lessons
- Evidence: the canary in this session's Deviations. Rule: after a stdin `doppler secrets set`, `--plain | wc -c` is one byte over the stored length; for the stored length run `doppler secrets get <NAME> --json | jq -c '[.. | strings | length]'`, which prints integers only. Scope: project.

## Decisions
- Kept: Airflow secrets live in Doppler `data-projects`/`prd` with the pipeline's, and compose reads them through `doppler run` (`infra/airflow/README.md`, Secrets)
- Kept: the compose deploy waits until the CT exists with the state mount marked; the pipeline refuses an unmarked directory (#16)

## Memory proposals
none

Status: none pending

## Skill feedback
none

Status: none pending

## Graduation candidates
none

## Next session
1. Run the verification loop above
2. ~~Once the owner reports the CT is up: marker, compose deploy, post-deploy checks~~ done 2026-11-15 (see Owed)
3. ~~Read the first DAG run's cost off `WHD_MONTHLY` before unpausing `whd_weekly`~~ done 2026-11-20 (see Owed)

Suggested skills: retro, finish-feature

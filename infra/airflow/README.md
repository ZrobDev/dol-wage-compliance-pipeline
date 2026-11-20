# Airflow on the homelab (M2)

Airflow 3.3.2 (LocalExecutor) and Cosmos 1.15.1 run the pipeline weekly on one Docker host: an unprivileged LXC container on the homelab. The DAG is `airflow/dags/whd_weekly.py`. It runs `pipeline ingest --defer-load`, then each dbt model and its tests as Cosmos tasks.

E3 measured this stack at 1.98 GiB peak memory, so the container gets 4 GiB.

## What is where

| Path | Holds |
|---|---|
| `Dockerfile` | Built from the repo root. Airflow and Cosmos go in the image's Python. The pipeline and dbt go in `/opt/pipeline/.venv`, built from `uv.lock`. The dbt manifest is built at image time. |
| `compose.yaml` | postgres, plus the init, api-server, scheduler, dag-processor and triggerer services. |
| `requirements-airflow.in` / `.txt` | Airflow and Cosmos pins, transitive ones included. |
| `/srv/whd-state` on the host | The durable state directory (ADR 0004). It is bind-mounted into the scheduler only. |

## Secrets

Every secret is a Compose secret at `/run/secrets/<name>`, sourced from an env var at `docker compose up` time (`doppler run`). `tests/test_compose_secrets.py` fails if one moves into `environment:`.

| Secret | Source env var | Make it with |
|---|---|---|
| `postgres_password` | `AIRFLOW_POSTGRES_PASSWORD` | `openssl rand -hex 32` (hex, so the DB URL needs no escaping) |
| `airflow_fernet_key` | `AIRFLOW_FERNET_KEY` | 32 random bytes, urlsafe base64 (`openssl rand 32 \| basenc --base64url`) |
| `airflow_jwt_secret` | `AIRFLOW_JWT_SECRET` | `openssl rand -hex 32` |
| `airflow_api_secret_key` | `AIRFLOW_API_SECRET_KEY` | `openssl rand -hex 32` |
| `dol_api_key` | `DOL_API_KEY` | already in Doppler |
| `snowflake_private_key` | `SNOWFLAKE_PRIVATE_KEY` | already in Doppler (PKCS#8 PEM; dbt reads it with `private_key_path`) |
| `whd_ping_base` | `WHD_PING_BASE` | `https://hc-ping.com/<ping-key>` from the healthchecks.io project ([Alerts](#alerts)). It is the only thing needed to ping the checks, so treat it as a secret |

Generated values go straight from `openssl` into Doppler over stdin and are never printed, for example `openssl rand -hex 32 | doppler secrets set AIRFLOW_JWT_SECRET -p data-projects -c prd`.

`SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_USER` are identifiers, not credentials, and are passed to the scheduler as plain config.

**Fail closed:**
- An unset source var stops compose from starting.
- An empty one leaves the file empty or absent. Each Airflow `_CMD` then exits non-zero, so Airflow refuses to start, and the pipeline's `secret()` exits before it calls anything.

## Host setup (once)

The container itself is created by the homelab repo's own scripts. This repo assumes only:
- an unprivileged LXC with `nesting=1,keyctl=1`, Docker, 2 vCPU, 4 GiB RAM and a 16 GB root;
- a separate mount point at `/srv/whd-state` (about 2 GB is plenty: a full backfill is 248 gzipped pages, about 500 MB).
- once the mount point is attached, run inside the container:

  ```bash
  findmnt -T /srv/whd-state                       # must be the mount point's own device first
  touch /srv/whd-state/.whd-state-volume          # the marker; the pipeline refuses the dir without it
  chown -R 50000:0 /srv/whd-state && chmod 0750 /srv/whd-state
  ```
- nothing published beyond the container's `127.0.0.1`. The UI is reached with `ssh -L 8080:127.0.0.1:8080 <host>`.
- the Doppler CLI on the host, plus a read-only service token for `data-projects/prd` scoped to the checkout, because the deploy below runs `doppler run` there. Add Doppler's apt repository first ([install-cli](https://docs.doppler.com/docs/install-cli)), then:

  ```bash
  # on the Docker host: pinned CLI, checkout at a known commit, cloned over HTTPS
  apt-get install -y doppler=3.77.0 && apt-mark hold doppler
  git clone https://github.com/ZrobDev/dol-wage-compliance-pipeline.git /opt/dol-wage-compliance-pipeline
  git -C /opt/dol-wage-compliance-pipeline checkout --detach <commit>

  # on a workstation logged in to Doppler: the token goes through a pipe, never onto a screen or into argv
  doppler configs tokens create <host>-whd-airflow -p data-projects -c prd --plain \
    | ssh <host> 't=$(cat); [ -n "$t" ] || exit 1; printf %s "$t" | doppler configure set token --scope /opt/dol-wage-compliance-pipeline >/dev/null && echo token-ok'
  ```

  Inside the checkout the scoped token selects the project and config, so `doppler run --` needs no `-p`/`-c`. Run every `docker compose` command, `ps` and `exec` included, under `doppler run --`: the compose file reads its secret sources and Snowflake identifiers from the environment. The token reads every secret in `prd`, and it sits in root's Doppler config on the host's disk, so the host's backups carry it. When the host is retired, find the token's slug with `doppler configs tokens -p data-projects -c prd` and revoke it with `doppler configs tokens revoke <slug> -p data-projects -c prd`. First run 2026-11-15 on the homelab's CT 121, at `a340319`.

**Never `mkdir /srv/whd-state` or write the marker anywhere but the mounted volume.** If the mount is missing:
- Docker Engine refuses to start the scheduler (`create_host_path: false`).
- A runtime that creates the bind source anyway (Podman does) leaves an empty directory. The pipeline then exits 4 on its first task, because the marker is absent.

## Deploy

```bash
ssh whd-airflow /opt/dol-wage-compliance-pipeline/infra/airflow/deploy.sh   # ends "deploy: ok <sha>"
```

`deploy.sh` refuses when the checkout has local changes under any path the image is built from, or when a `whd_weekly` run is in progress. Restarting the scheduler mid-run would kill ingest. It then:
1. fast-forwards to `origin/main`;
2. builds with `--build-arg REVISION=<sha>`. A bare `docker compose build` fails, because the drift task needs the revision;
3. runs `up -d`;
4. checks that the scheduler's image label equals the sha, that `whd_ping_base` is mounted, and that no DAG has import errors.

The first time, the script isn't on the host yet. Run `git fetch origin && git merge --ff-only origin/main` in the checkout first.

The DAG starts **paused**. Unpause it in the UI or with `docker compose exec airflow-scheduler airflow dags unpause whd_weekly`.

The admin password is generated on the api-server's first start, into the `auth` volume. Read it inside the container with `docker compose exec airflow-apiserver cat /opt/airflow/auth/passwords.json`; never paste it anywhere.

## Verify after a deploy

```bash
# Each line prints "ok"; anything else, including an inspect error, is a failure.
for svc in airflow-scheduler airflow-apiserver postgres; do
  env=$(docker inspect "$(docker compose ps -q $svc)" --format '{{json .Config.Env}}') || { echo "FAIL $svc: no container"; continue; }
  [ -n "$env" ] && ! grep -qE 'DOL_API_KEY|PRIVATE_KEY|PASSWORD=|FERNET_KEY=|JWT_SECRET=' <<<"$env" && echo "ok $svc" || echo "FAIL $svc"
done
docker compose exec airflow-scheduler ls /run/secrets              # all six names
docker compose exec airflow-scheduler findmnt -T /var/lib/pipeline/state
docker compose exec airflow-apiserver test -s /opt/airflow/auth/passwords.json && echo ok   # admin password generated
docker compose exec airflow-scheduler /opt/pipeline/.venv/bin/pipeline load   # files=0 (or the pages left over); proves secrets, lock and state dir
```

Never print `docker compose config` in full; grep it for one key.

**First deploy only.** Before the marker is written, confirm that Docker Engine refuses a missing bind source: stop the stack, point the mount at a path that does not exist, and check that `docker compose up -d airflow-scheduler` fails and creates nothing. The laptop smoke test ran on Podman, which creates the path anyway. If Docker does too, the marker check is the only guard, and it still holds.

**Cost: measured once.** The first full run (2026-11-20 02:12–02:28 UTC, CT 121 at `d7446b2`: ingest plus all 20 dbt nodes) used **0.11 credits**, read from `WAREHOUSE_METERING_HISTORY` for `WHD_WH`. The figure is one hourly bucket, so it may include a minute of an ad-hoc Snowsight query at the bucket's edge. Cosmos runs each dbt node as its own task, and back-to-back tasks keep the warehouse awake inside its 60-second suspend window.
- The bound: if every task woke the warehouse separately, a run would be 21 wakes × 60 s ≈ 0.35 credits, about 1.5 credits a month against the 2-credit cap.
- Since #20 a quiet week exits ingest with 99 and skips every dbt task, so most weeks should cost at most one 60-second wake for the watermark query (about 0.02 credits); a week with new DOL rows should cost the same order as the measured 0.11. Neither case is measured yet: CT 121 still runs `d7446b2`, which predates #20.
- To read a run's cost, run this in Snowsight as ACCOUNTADMIN; `WHD_PIPELINE` has no `MONITOR` on `WHD_WH` and sees no rows. Snowsight shows times in the session time zone:

  ```sql
  SELECT start_time, end_time, credits_used
  FROM TABLE(WHD.INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
    DATEADD('hour', -12, CURRENT_TIMESTAMP()), CURRENT_TIMESTAMP(), 'WHD_WH'))
  ORDER BY start_time;
  ```
  `SHOW RESOURCE MONITORS LIKE 'WHD_MONTHLY'` gives the month's total, not one run's, and it lags.

## Alerts

Two healthchecks.io checks. They sit outside the homelab, so a dead host or a paused DAG still alerts: a check that hears nothing goes late on its own.

| Check (slug) | Schedule (UTC) | Grace | Pinged by |
|---|---|---|---|
| `whd-weekly` | cron `0 6 * * 1` | 4 h | `ping_ok` after dbt (body: the ingest summary, or "no new rows"); `ping_fail` (`/fail`) when ingest or dbt fails |
| `whd-drift` | cron `0 6 * * 1` | 1 h | `drift`: `/fail` when `src/`, `dbt/`, `airflow/`, the lockfiles, the Dockerfile, the Airflow pins or `compose.yaml` changed on `main` since the running image's revision. A docs-only commit is not drift |

Setup, once:
1. Create a healthchecks.io project with the two checks above. Use slugs, not UUIDs. Connect Slack #vps-ops or email.
2. Copy the project's ping key.
3. Store `https://hc-ping.com/<ping-key>` as `WHD_PING_BASE` in Doppler `data-projects/prd` over stdin, never printed, and compare sha256s:
   `read -rs v && printf %s "$v" | doppler secrets set WHD_PING_BASE -p data-projects -c prd --no-interactive >/dev/null; printf %s "$v" | sha256sum; doppler secrets get WHD_PING_BASE -p data-projects -c prd --plain | tr -d '\n' | sha256sum; unset v`

Pings are ordinary tasks, not callbacks: Airflow 3 runs callbacks in the dag-processor, which holds no secrets. A ping that fails fails its task, and the check then goes late.

## Backfill

The weekly DAG is incremental. A full backfill (about 6 hours) runs by hand in the scheduler container and always uses `--defer-load`. Pause the DAG first, so the two never meet at the state-dir lock:

```bash
docker compose exec airflow-scheduler airflow dags pause whd_weekly
# In tmux or another session that survives logout; not `exec -d`, which hides the exit code.
docker compose exec -T airflow-scheduler /opt/pipeline/.venv/bin/pipeline ingest --full --defer-load; echo "exit=$?"
docker compose exec airflow-scheduler airflow dags unpause whd_weekly
```

Exit 3 means another command holds the lock, so nothing ran. Exit 2 means the API failed: the pages fetched so far are loaded, and rerunning the same command resumes from the checkpoint.

## Logging

`pipeline ingest` runs as a subprocess with its own logging setup, and it keeps `httpx` at WARNING. Airflow's logging configuration therefore never reaches the logger that would print the key-bearing URL (ADR 0003). Error messages are redacted before they are printed.

## Regenerating the pins

```bash
curl -sO https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.13.txt
uv pip compile infra/airflow/requirements-airflow.in -c constraints-3.13.txt \
  --exclude-newer <a date at least two weeks back> --python-version 3.13 \
  --python-platform x86_64-manylinux_2_28 --no-header --no-annotate \
  -o infra/airflow/requirements-airflow.txt
```

The base image digest and the postgres digest in `compose.yaml` are pinned too. When a pin changes, bump them together.

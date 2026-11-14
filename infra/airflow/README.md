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

**Never `mkdir /srv/whd-state` or write the marker anywhere but the mounted volume.** If the mount is missing:
- Docker Engine refuses to start the scheduler (`create_host_path: false`).
- A runtime that creates the bind source anyway (Podman does) leaves an empty directory. The pipeline then exits 4 on its first task, because the marker is absent.

## Deploy

```bash
cd infra/airflow
doppler run -p data-projects -c prd -- docker compose build
doppler run -p data-projects -c prd -- docker compose up -d
docker compose ps                                                      # every service healthy; airflow-init exited 0
```

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

**Cost: estimated, not measured.** Cosmos runs each of the 20 dbt nodes as its own task. Back-to-back tasks keep the warehouse awake inside its 60-second suspend window, so a run should cost a few minutes of XS time (about 0.05 to 0.1 credits).
- The bound: if every task woke the warehouse separately, a run would be 21 wakes × 60 s ≈ 0.35 credits, about 1.5 credits a month against the 2-credit cap.
- Read the first real run off the `WHD_MONTHLY` resource monitor before leaving the DAG unpaused.

## Backfill

The weekly DAG is incremental. A full backfill (about 6 hours) runs by hand in the scheduler container, in the background, and always uses `--defer-load`:

```bash
docker compose exec -d airflow-scheduler /opt/pipeline/.venv/bin/pipeline ingest --full --defer-load
```

The state-dir lock keeps the weekly run and a backfill from overlapping. Whichever starts second exits with code 3, and its Airflow retry picks it up later.

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

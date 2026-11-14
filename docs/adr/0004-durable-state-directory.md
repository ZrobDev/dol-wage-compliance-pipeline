# 0004: A durable state directory for the checkpoint and page files

- Status: accepted
- Date: 2026-11-13

## Context

`pipeline ingest` keeps two kinds of state on disk:
- **The checkpoint,** `whd_checkpoint.json`. It holds the offset reached by an interrupted run.
- **The page files,** `pages/whd_*.json.gz`. They are the gzipped API pages that `pipeline load` stages to Snowflake.

On the laptop both live in `./state`. Under Airflow (M2) the task runs in a container, from a working directory that is not the repo, and the container can be recreated at any time. ADR 0003 lists this as the first thing M2 must handle. If the checkpoint is lost, an interrupted 6-hour backfill restarts from the watermark.

## Decision

- **One state directory, named by `PIPELINE_STATE_DIR`.** The `--state-dir` flag wins over it, and `./state` is the fallback when neither is set.
- **The env path must be absolute and must already exist, and the pipeline never creates it.**
  - If it is empty, relative, missing or not writable, the command exits 4 before it touches the API or Snowflake. An empty value counts as an error, not as unset, because Compose expands a missing `${PIPELINE_STATE_DIR}` to an empty string.
  - Creating the directory would hide a forgotten volume: the state would land in the container's writable layer and vanish when the container is recreated.
  - The laptop default and the flag still create their directory.
- **One writer at a time.** Every `ingest` and `load` holds a non-blocking `flock` on `.pipeline.lock` in the state directory for the whole command.
  - A second command exits 3 and changes nothing.
  - Two overlapping runs would otherwise overwrite each other's checkpoint and delete each other's pages.
  - The kernel releases the lock when the process dies, so a killed task never leaves it stuck.
- **Atomic writes.** The checkpoint and every page are first written to a `.tmp` name outside the `whd_*.json.gz` glob, then renamed into place. A killed task never leaves a truncated page for `pipeline load` to stage.
- **The checkpoint records `written_at`.** A resume logs it at WARNING level.
  - A durable checkpoint can outlive the data it points into. An incremental run's offset counts rows after `since`, and that result set grows as the source publishes new records.
  - The log line makes a stale resume visible. Deleting the checkpoint still forces a fresh start.

## Deployment contract (M2)

- The state directory is a dedicated volume or bind mount, and nothing else is stored on it. `findmnt -T "$PIPELINE_STATE_DIR"` must show a real filesystem, never `overlay` or `tmpfs`.
- Ownership is set on the volume, for the user the task runs as (Airflow's image uses UID 50000).
- **The image never creates the path, and the DAG passes the env var, not `--state-dir`.**
  - The existence check catches a missing volume only if nothing else creates the directory. A `mkdir` in the Dockerfile, or the flag, which still creates its directory, would let a forgotten mount pass.
  - The check is "the directory exists", not "it is a mount point". The `findmnt` check above is the deploy-time proof.
- It holds row-level records from the public WHD source. It is never committed (`state/` is in `.gitignore` and `gate.yaml`), and nothing in it is published (ADR 0002).

## Consequences

- **Page files accumulate.** They are the replay source if a load fails, and nothing deletes them yet. A full backfill is 248 files. Retention, and whether the volume is backed up, is an open decision for M2 and is not automated here.
- **No lost work from overlap.** An Airflow ingest and a hand-run `pipeline load` that overlap now fail fast, so the second one can be retried.
- **Linux and macOS only.** `fcntl` is POSIX, and both the laptop and the homelab containers are Linux.

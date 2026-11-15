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
  - It must also contain the marker file `.whd-state-volume`, which the host setup writes once onto the mounted volume.
  - If it is empty, relative, missing, unmarked or not writable, the command exits 4 before it touches the API or Snowflake. An empty value counts as an error, not as unset, because Compose expands a missing `${PIPELINE_STATE_DIR}` to an empty string.
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
- **The marker lives only on the volume.** Write it once on the mounted volume (`touch .whd-state-volume`), never in the image and never on the host's root filesystem.
  - Some runtimes create a missing bind source as an empty directory. Podman does, even with `--mount` (seen in the M2 smoke test, 2026-11-13). So "the directory exists" proves nothing on its own; the marker does.
  - The DAG passes the env var, not `--state-dir`, because the flag still creates its directory.
  - The marker shows the right volume was mounted once. `findmnt` at deploy time is the proof that it is mounted now.
- It holds row-level records from the public WHD source. It is never committed (`state/` is in `.gitignore` and `gate.yaml`), and nothing in it is published (ADR 0002).

## Consequences

- **Page files accumulate.** They are the replay source if a load fails, and nothing deletes them yet. A full backfill is 248 files. Retention, and whether the volume is backed up, is an open decision for M2 and is not automated here.
- **No lost work from overlap.** An Airflow ingest and a hand-run `pipeline load` that overlap now fail fast, so the second one can be retried.
- **Linux and macOS only.** `fcntl` is POSIX, and both the laptop and the homelab containers are Linux.

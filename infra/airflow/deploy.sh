#!/usr/bin/env bash
# Deploy the Airflow stack from origin/main, with the image labelled by the commit it was built
# from (the drift task reads it). Run on the host, from anywhere:
#   ssh whd-airflow /opt/dol-wage-compliance-pipeline/infra/airflow/deploy.sh
# Refuses local edits to anything that enters the image, and a whd_weekly run in progress
# (restarting the scheduler would kill it mid-ingest).
set -euo pipefail

# Everything runs inside main: the merge below rewrites this file, and bash reads a script as it
# goes, so the whole body is parsed before the first line runs.
main() {
  cd "$(dirname "$(readlink -f "$0")")"
  local repo rev label runs errors
  repo=$(git rev-parse --show-toplevel)
  dc() { doppler run -- docker compose "$@"; }
  # The Airflow CLI prints a warning line on stdout first; its JSON is the last line.
  airflow_json() { dc exec -T airflow-scheduler airflow "$@" -o json 2>/dev/null | tail -n 1; }

  # Every path the build reads (the repo-root .dockerignore allowlist) plus the compose file.
  local image_paths=(src dbt airflow pyproject.toml uv.lock .python-version infra/airflow)
  if [[ -n "$(git -C "$repo" status --porcelain -- "${image_paths[@]}")" ]]; then
    git -C "$repo" status --short -- "${image_paths[@]}" >&2
    echo "deploy: local changes above would enter the image; refusing" >&2
    exit 1
  fi

  if [[ -n "$(dc ps -q airflow-scheduler)" ]]; then
    runs=$(airflow_json dags list-runs whd_weekly --state running) || runs="(command failed)"
    if [[ "$runs" != "[]" ]]; then
      echo "deploy: whd_weekly has a running run, or the check failed ($runs); refusing" >&2
      exit 1
    fi
  fi

  git -C "$repo" fetch -q origin
  git -C "$repo" merge -q --ff-only origin/main
  rev=$(git -C "$repo" rev-parse HEAD)
  echo "deploy: building $rev"
  dc build -q --build-arg REVISION="$rev"
  dc up -d

  label=$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
    "$(dc ps -q airflow-scheduler)")
  [[ "$label" == "$rev" ]] || { echo "deploy: scheduler runs $label, not $rev" >&2; exit 1; }
  dc exec -T airflow-scheduler test -s /run/secrets/whd_ping_base \
    || { echo "deploy: whd_ping_base is not mounted" >&2; exit 1; }
  errors=$(airflow_json dags list-import-errors)
  [[ "$errors" == "[]" ]] || { echo "deploy: DAG import errors: $errors" >&2; exit 1; }
  echo "deploy: ok $rev (whd_weekly stays as paused or unpaused as it was)"
}

main "$@"

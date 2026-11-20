"""WHD pipeline, weekly: incremental ingest, then every dbt model and test through Cosmos.

The tasks wrap the M1 commands and do not rewrite them (ADR 0003). The full backfill is not a
DAG run: it takes about 6 hours and is started by hand (infra/airflow/README.md).
"""

import os
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode
from whd_ping import drift_files, ping

PIPELINE = "/opt/pipeline"
DBT = f"{PIPELINE}/dbt"

with DAG(
    dag_id="whd_weekly",
    # Weekly, not daily, under the 2-credit monthly cap. Measured cost and how to read it:
    # infra/airflow/README.md, Deploy.
    schedule="0 6 * * 1",
    start_date=datetime(2026, 11, 16),
    catchup=False,
    # One run at a time; the state-dir lock would refuse a second ingest anyway (exit 3).
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=20)},
    tags=["whd"],
):
    ingest = BashOperator(
        task_id="ingest",
        # --defer-load: one COPY at the end, never one per page (AGENTS.md). The state dir comes
        # from PIPELINE_STATE_DIR, never --state-dir: the flag would create a missing mount.
        bash_command=f"{PIPELINE}/.venv/bin/pipeline ingest --defer-load --empty-exit-code 99",
        # A quiet week (DOL loads about quarterly, so most weeks) skips ingest, and with it
        # every dbt task: rebuilding unchanged models only spends warehouse credits.
        skip_on_exit_code=99,
        # One retry layer: fetch_page already retries 429, 502-504 and transport errors for
        # ~50 min. This retry is for a task that was killed, not for the API.
        retries=1,
        # The API allows ~10 requests per 15 min; a quarterly DOL load is two or three pages.
        execution_timeout=timedelta(hours=2),
    )

    dbt = DbtTaskGroup(
        group_id="dbt",
        project_config=ProjectConfig(DBT, manifest_path=f"{DBT}/target/manifest.json"),
        profile_config=ProfileConfig(
            profile_name="whd", target_name="homelab", profiles_yml_filepath=f"{DBT}/profiles.yml"
        ),
        execution_config=ExecutionConfig(dbt_executable_path=f"{PIPELINE}/.venv/bin/dbt"),
        # dbt ls at parse time timed out the DAG bag in E3; read the manifest built into the image.
        render_config=RenderConfig(load_method=LoadMode.DBT_MANIFEST),
        default_args={"retries": 1},
    )

    # Alerts are plain tasks, not callbacks: Airflow 3 runs callbacks in the dag-processor, which
    # holds no secrets. These run in the scheduler (LocalExecutor), next to /run/secrets.
    # A failed ping fails its task; the check then goes late on healthchecks.io and alerts anyway.
    # Their own short retry delay: the DAG's 20 min suits a killed ingest, not a ping that failed
    # on a network blip (it held a manual `dags test` for 20 min per attempt on 2026-11-20).
    PING_RETRY = {"retries": 2, "retry_delay": timedelta(minutes=1)}

    @task(trigger_rule="none_failed", **PING_RETRY)
    def ping_ok(**context):
        summary = context["ti"].xcom_pull(task_ids="ingest")
        ping("whd-weekly", body=summary or "no new rows: ingest and dbt skipped")

    @task(trigger_rule="one_failed", **PING_RETRY)
    def ping_fail(**context):
        ping("whd-weekly", "/fail", body=f"run {context['run_id']} failed; read the task logs")

    @task(**PING_RETRY)
    def drift():
        revision = os.environ.get("PIPELINE_REVISION", "")
        files = drift_files(revision)
        if files:
            changed = "\n".join(files)
            ping("whd-drift", "/fail", body=f"host runs {revision[:7]}; main changed:\n{changed}")
        else:
            ping("whd-drift", body=f"host runs {revision[:7]}; no image path changed on main")

    ingest >> dbt >> ping_ok()
    [ingest, dbt] >> ping_fail()
    drift()

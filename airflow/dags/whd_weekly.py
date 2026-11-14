"""WHD pipeline, weekly: incremental ingest, then every dbt model and test through Cosmos.

The tasks wrap the M1 commands and do not rewrite them (ADR 0003). The full backfill is not a
DAG run: it takes about 6 hours and is started by hand (infra/airflow/README.md).
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import LoadMode

PIPELINE = "/opt/pipeline"
DBT = f"{PIPELINE}/dbt"

with DAG(
    dag_id="whd_weekly",
    # Weekly, not daily, under the 2-credit monthly cap. Estimate, unmeasured: back-to-back tasks
    # keep the warehouse awake, so a few minutes of XS time per run; the worst case (every one of
    # the 21 tasks waking it for 60 s) is ~0.35 credits. Read the first run off the monitor.
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
        bash_command=f"{PIPELINE}/.venv/bin/pipeline ingest --defer-load",
        # The API allows ~10 requests per 15 min; a week of new records is a few pages.
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

    ingest >> dbt

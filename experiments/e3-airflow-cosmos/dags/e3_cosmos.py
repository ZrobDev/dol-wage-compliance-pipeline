from datetime import datetime
from cosmos import DbtDag, ProjectConfig, ProfileConfig, ExecutionConfig, RenderConfig
from cosmos.constants import LoadMode

P = "/opt/airflow/dags/dbt/e3"
# dbt_ls parsing took >30 s on this CPU (dagbag import timeout); read a prebuilt manifest instead (built in CI for M3)
e3_cosmos = DbtDag(
    dag_id="e3_cosmos",
    project_config=ProjectConfig(P, manifest_path=f"{P}/target/manifest.json"),
    profile_config=ProfileConfig(profile_name="e3", target_name="dev", profiles_yml_filepath=f"{P}/profiles.yml"),
    execution_config=ExecutionConfig(dbt_executable_path="/opt/dbt-venv/bin/dbt"),
    render_config=RenderConfig(load_method=LoadMode.DBT_MANIFEST),
    schedule="*/5 * * * *", start_date=datetime(2026, 11, 1), catchup=False,
    max_active_runs=1, max_active_tasks=1,  # one duckdb file, one writer
)

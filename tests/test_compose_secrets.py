"""Guard over infra/airflow/compose.yaml: secrets travel as Compose secrets, never as env vars.

Fails if `env_file:` appears, if a secret's source env name appears anywhere but its own
`environment: NAME` source line, if a secret lacks its top-level source or a service grant, or if
the state volume could be silently created.
"""

from pathlib import Path

import pytest
import yaml

from pipeline.secrets import secret

COMPOSE = Path(__file__).resolve().parent.parent / "infra" / "airflow" / "compose.yaml"
# Every secret the stack needs, and the services that must be granted it.
EXPECTED = {
    "postgres_password": {"postgres", "airflow-init", "airflow-scheduler", "airflow-apiserver"},
    "airflow_fernet_key": {"airflow-init", "airflow-scheduler", "airflow-apiserver"},
    "airflow_jwt_secret": {"airflow-scheduler", "airflow-apiserver"},
    "airflow_api_secret_key": {"airflow-apiserver"},
    "dol_api_key": {"airflow-scheduler"},
    "snowflake_private_key": {"airflow-scheduler"},
}


def check(text: str) -> list[str]:
    problems = []
    if "env_file" in text:
        problems.append("env_file is banned")
    config = yaml.safe_load(text)
    sources = config.get("secrets") or {}
    for name in EXPECTED:
        source = (sources.get(name) or {}).get("environment")
        if not source:
            problems.append(f"secret {name} has no top-level environment source")
            continue
        # The source name may appear only on its own `environment: NAME` line.
        source_lines = [line for line in text.splitlines() if source in line]
        if source_lines != [f"    environment: {source}"]:
            problems.append(f"{source} appears outside its secret source line: {source_lines}")
    services = config.get("services") or {}
    for name, granted_to in EXPECTED.items():
        for service in granted_to:
            if name not in (services.get(service, {}).get("secrets") or []):
                problems.append(f"service {service} is not granted secret {name}")
    for service_name, service in services.items():
        env = service.get("environment") or {}
        for key, value in env.items() if isinstance(env, dict) else []:
            looks_secret = any(w in key.upper() for w in ("PASSWORD", "SECRET", "FERNET", "_KEY"))
            from_file = key.endswith(("_CMD", "_FILE")) or "/run/secrets/" in str(value)
            if looks_secret and not from_file:
                problems.append(f"{service_name}: {key} looks like a secret in environment:")
    scheduler = services.get("airflow-scheduler", {})
    if scheduler.get("environment", {}).get("PIPELINE_STATE_DIR") != "/var/lib/pipeline/state":
        problems.append("PIPELINE_STATE_DIR must be the literal mount target")
    binds = [v for v in scheduler.get("volumes", []) if isinstance(v, dict)]
    if not any(
        v.get("target") == "/var/lib/pipeline/state"
        and v.get("bind", {}).get("create_host_path") is False
        for v in binds
    ):
        problems.append("state dir must be a bind with create_host_path: false")
    return problems


def test_compose_file_passes_the_secrets_guard():
    assert check(COMPOSE.read_text()) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("  logs: {}", "  logs: {}\nx-bad:\n  env_file: .env", "env_file"),
        (
            "      POSTGRES_DB: airflow\n",
            "      POSTGRES_DB: airflow\n      DOL_API_KEY: ${DOL_API_KEY}\n",
            "DOL_API_KEY appears outside",
        ),
        ("      - dol_api_key\n", "", "not granted secret dol_api_key"),
        ("    environment: SNOWFLAKE_PRIVATE_KEY\n", "    file: ./key\n", "no top-level"),
        (
            "          create_host_path: false\n",
            "          create_host_path: true\n",
            "create_host_path",
        ),
        (
            "PIPELINE_STATE_DIR: /var/lib/pipeline/state",
            "PIPELINE_STATE_DIR: ${STATE}",
            "literal mount target",
        ),
        (
            "      POSTGRES_DB: airflow\n",
            "      POSTGRES_DB: airflow\n      POSTGRES_PASSWORD: hunter2\n",
            "looks like a secret",
        ),
    ],
)
def test_guard_catches_each_break(old, new, expected):
    text = COMPOSE.read_text()
    assert text.count(old) == 1, f"mutation did not match: {old!r}"
    assert any(expected in problem for problem in check(text.replace(old, new)))


def test_secret_file_wins_over_env(tmp_path, monkeypatch):
    (tmp_path / "dol_api_key").write_text("from-file\n")
    monkeypatch.setenv("DOL_API_KEY", "from-env")
    assert secret("DOL_API_KEY", tmp_path) == "from-file"


def test_secret_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DOL_API_KEY", "from-env")
    assert secret("DOL_API_KEY", tmp_path) == "from-env"


@pytest.mark.parametrize("file_value", [None, "", "\n"])
def test_secret_fails_closed_when_file_and_env_are_empty(tmp_path, monkeypatch, file_value):
    if file_value is not None:
        (tmp_path / "dol_api_key").write_text(file_value)
    monkeypatch.setenv("DOL_API_KEY", "")
    with pytest.raises(SystemExit, match="DOL_API_KEY is required"):
        secret("DOL_API_KEY", tmp_path)


def test_empty_secret_file_does_not_fall_back_to_env(tmp_path, monkeypatch):
    # A present-but-empty file means the deploy is broken; the env must not paper over it.
    (tmp_path / "dol_api_key").write_text("")
    monkeypatch.setenv("DOL_API_KEY", "from-env")
    with pytest.raises(SystemExit):
        secret("DOL_API_KEY", tmp_path)

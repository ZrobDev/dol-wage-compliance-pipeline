"""The repo is public: tool output, local state and secrets files must never be tracked.

.gitignore stops a file from being added by accident, but not one added on purpose or before
the ignore line existed (dbt/.user.yml was committed in #10 that way). This test reads what git
actually tracks, so it fails in CI whatever the route was.
"""

import fnmatch
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = [
    ".env",
    ".env.*",
    "*.pem",
    "*.p8",
    "*.pyc",
    "*/__pycache__/*",
    ".venv/*",
    "state/*",
    "*.json.gz",
    "dbt/.user.yml",
    "dbt/target/*",
    "dbt/logs/*",
    "dbt/dbt_packages/*",
    "*.duckdb",
    "*.tfstate*",
]
ALLOWED = [".env.example"]


def forbidden(paths: list[str]) -> list[str]:
    return [
        path
        for path in paths
        if path not in ALLOWED and any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN)
    ]


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return out.splitlines()


def test_no_tool_output_or_local_state_is_tracked():
    assert forbidden(tracked_files()) == []


def test_the_patterns_catch_what_they_name():
    planted = [
        "dbt/.user.yml",
        "dbt/target/manifest.json",
        "state/pages/whd_full_00000000_abc.json.gz",
        ".env",
        "src/pipeline/__pycache__/cli.cpython-313.pyc",
    ]
    assert forbidden(planted) == planted
    assert forbidden([".env.example", "dbt/models/staging/stg_whd__cases.sql"]) == []

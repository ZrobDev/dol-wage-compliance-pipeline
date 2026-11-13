"""The repo is public: nothing that .gitignore excludes may be tracked.

.gitignore stops a file from being added by accident, but not one added with `git add -f` or
before its ignore line existed (dbt/.user.yml was committed in #10 that way). `git ls-files
--cached --ignored --exclude-standard` lists exactly those files, at any depth, with git's own
matching rules, so .gitignore stays the one list of what must never be committed.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def tracked_but_ignored(repo: Path) -> list[str]:
    out = subprocess.run(
        # core.excludesFile off: only the repo's own .gitignore counts, as in CI.
        ["git", "-C", str(repo), "-c", "core.excludesFile=/dev/null", "ls-files", "--cached"]
        + ["--ignored", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return out.splitlines()


def test_no_ignored_file_is_tracked():
    # Skip only for a source tree with no .git at all (an sdist); in CI, or with .git present,
    # a git failure is a real failure.
    if not (ROOT / ".git").exists() and not os.environ.get("CI"):
        pytest.skip("not a git checkout")
    assert tracked_but_ignored(ROOT) == []


def test_force_added_ignored_files_are_caught(tmp_path):
    shutil.copy(ROOT / ".gitignore", tmp_path / ".gitignore")
    planted = [
        "dbt/.user.yml",
        "dbt/target/manifest.json",
        "state/pages/whd_full_00000000_abc.json.gz",
        ".env",
        ".envrc",
        "deploy/snowflake_rsa.p8",
        "analytics/.env.local",
        "src/pipeline/__pycache__/cli.cpython-313.pyc",
    ]
    for path in [*planted, ".env.example", "dbt/seeds/naics_sectors.csv"]:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "core.excludesFile=/dev/null", "add", "-f", "."],
        check=True,
    )
    assert sorted(tracked_but_ignored(tmp_path)) == sorted(planted)

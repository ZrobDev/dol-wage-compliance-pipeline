import json
import os
import subprocess
import sys

import httpx
import pytest

from pipeline import cli
from pipeline.ingest import IngestError, run
from pipeline.state import (
    ENV_VAR,
    EXIT_BAD_STATE_DIR,
    EXIT_LOCKED,
    LOCK_NAME,
    StateDirError,
    StateDirLocked,
    exclusive,
    resolve_state_dir,
)


def test_flag_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "env"))
    assert resolve_state_dir(tmp_path / "flag") == tmp_path / "flag"
    assert (tmp_path / "flag").is_dir()


def test_env_is_used_when_it_names_an_existing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    assert resolve_state_dir(None) == tmp_path


def test_env_dir_is_never_created(tmp_path, monkeypatch):
    # A missing mount must fail, not fall back to the container's writable layer.
    missing = tmp_path / "not-mounted"
    monkeypatch.setenv(ENV_VAR, str(missing))
    with pytest.raises(StateDirError, match="does not exist"):
        resolve_state_dir(None)
    assert not missing.exists()


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_env_is_refused_not_treated_as_unset(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(ENV_VAR, value)
    with pytest.raises(StateDirError, match="empty"):
        resolve_state_dir(None)
    assert not (tmp_path / "state").exists()


def test_env_must_be_absolute(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "state")
    with pytest.raises(StateDirError, match="absolute"):
        resolve_state_dir(None)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_env_must_be_writable(tmp_path, monkeypatch):
    read_only = tmp_path / "ro"
    read_only.mkdir(mode=0o555)
    monkeypatch.setenv(ENV_VAR, str(read_only))
    with pytest.raises(StateDirError, match="not writable"):
        resolve_state_dir(None)


def test_default_is_created_when_nothing_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_state_dir(None).resolve() == (tmp_path / "state").resolve()
    assert (tmp_path / "state").is_dir()


HOLDER = (
    "import sys, time; from pathlib import Path; from pipeline.state import exclusive\n"
    "with exclusive(Path(sys.argv[1])):\n"
    "    print('held', flush=True); time.sleep(30)"
)


def test_second_writer_is_refused_while_the_first_holds_the_lock(tmp_path):
    # The holder is another process, as an overlapping Airflow task would be.
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            HOLDER,
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(StateDirLocked), exclusive(tmp_path):
            pass
    finally:
        holder.kill()
        holder.wait()
    # The kernel drops the lock with the process: a killed task never leaves it stuck.
    with exclusive(tmp_path):
        pass


def test_cli_exits_with_bad_state_dir_code_and_touches_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "not-mounted"))
    assert cli.main(["load"]) == EXIT_BAD_STATE_DIR
    assert "does not exist" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_cli_exits_with_locked_code_before_connecting(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli.warehouse, "connect", lambda: pytest.fail("connected while the lock was held")
    )
    with exclusive(tmp_path):
        # flock locks belong to the open file, so a second open in this process conflicts.
        assert cli.main(["load", "--state-dir", str(tmp_path)]) == EXIT_LOCKED


def test_lock_file_is_outside_the_page_glob(tmp_path):
    with exclusive(tmp_path):
        pass
    assert (tmp_path / LOCK_NAME).exists()
    assert not list(tmp_path.glob("whd_*.json.gz"))


def test_checkpoint_records_when_it_was_written(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"data": [{"case_id": 1}, {"case_id": 2}]})
        raise httpx.ConnectError("down")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http, pytest.raises(IngestError):
        run(
            http,
            api_key="TESTKEY-not-real-123",
            state_dir=tmp_path,
            since=None,
            load_page=lambda page: 0,
            sleep=lambda seconds: None,
            page_size=2,
        )
    saved = json.loads((tmp_path / "whd_checkpoint.json").read_text())
    assert saved["offset"] == 2
    assert saved["written_at"].endswith("+00:00")
    # Atomic writes leave no temporary files behind.
    assert not list(tmp_path.rglob("*.tmp"))
    assert len(list((tmp_path / "pages").glob("whd_*.json.gz"))) == 1

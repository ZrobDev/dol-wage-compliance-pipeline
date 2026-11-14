"""Where the ingest checkpoint and page files live, and who may write them.

On the laptop the state dir is `./state`, created on first use. Under Airflow it is a mounted
volume named by PIPELINE_STATE_DIR. That path must already exist: creating it would silently put
the checkpoint in the container's writable layer, which vanishes when the container is recreated,
and an interrupted backfill would then restart from the watermark.
"""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ENV_VAR = "PIPELINE_STATE_DIR"
DEFAULT = Path("state")
# Outside the `whd_*.json.gz` page glob, so a load never picks it up.
LOCK_NAME = ".pipeline.lock"
EXIT_BAD_STATE_DIR = 4
EXIT_LOCKED = 3


class StateDirError(RuntimeError):
    exit_code = EXIT_BAD_STATE_DIR


class StateDirLocked(StateDirError):
    exit_code = EXIT_LOCKED


def resolve_state_dir(flag: Path | None) -> Path:
    """The --state-dir flag wins, then PIPELINE_STATE_DIR, then ./state."""
    if flag is not None:
        flag.mkdir(parents=True, exist_ok=True)
        return flag
    configured = os.environ.get(ENV_VAR)
    if configured is None:
        DEFAULT.mkdir(parents=True, exist_ok=True)
        return DEFAULT
    if not configured.strip():
        # Compose turns `${PIPELINE_STATE_DIR}` into "" when the variable is missing; falling
        # back to ./state would put the checkpoint in the container's writable layer.
        raise StateDirError(f"{ENV_VAR} is set but empty")
    path = Path(configured)
    if not path.is_absolute():
        # A task's working directory is not the repo, so a relative path lands somewhere else.
        raise StateDirError(f"{ENV_VAR} must be an absolute path, got {configured!r}")
    if not path.is_dir():
        raise StateDirError(f"{ENV_VAR}={configured} does not exist; mount the state volume there")
    if not os.access(path, os.W_OK | os.X_OK):
        raise StateDirError(f"{ENV_VAR}={configured} is not writable by this user")
    return path


@contextmanager
def exclusive(state_dir: Path) -> Iterator[None]:
    """Hold a non-blocking lock on the state dir for the whole command.

    Two writers would overwrite each other's checkpoint and unlink each other's pages. The lock
    is released by the kernel when the process dies, so a killed task never leaves it stuck.
    """
    with open(state_dir / LOCK_NAME, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StateDirLocked(
                f"another pipeline command holds {state_dir / LOCK_NAME}; wait for it to finish"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)

"""Read a secret from a Compose secret file first, then from the environment.

Under Airflow each secret is mounted at /run/secrets/<lowercase name> and never set as an env var.
On the laptop, `doppler run` sets the env var instead. The file wins, so a secret re-added to the
container's env cannot silently take over.
"""

import os
from pathlib import Path

SECRETS_DIR = Path("/run/secrets")


def secret(name: str, secrets_dir: Path = SECRETS_DIR) -> str:
    path = secrets_dir / name.lower()
    value = path.read_text().strip() if path.is_file() else os.environ.get(name, "").strip()
    if not value:
        # Fail closed: an empty Compose source starts the container with the file absent.
        raise SystemExit(f"{name} is required (file {path} or env {name})")
    return value

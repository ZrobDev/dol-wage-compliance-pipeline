"""Health pings and the image-drift check for whd_weekly.

Stdlib only and no Airflow import, so the offline test suite can load it. The pings go to a
healthchecks.io-compatible endpoint, outside the homelab, so a dead host still alerts (a check
that stops hearing from Airflow goes late on its own).
"""

import json
import urllib.request
from collections.abc import Callable
from pathlib import Path

SECRET = Path("/run/secrets/whd_ping_base")
REPO = "ZrobDev/dol-wage-compliance-pipeline"
# What decides how the deployed stack behaves. A docs-only commit on main is not drift (17 of the
# first 45 commits were docs only, so comparing bare shas would alert on most merges).
IMAGE_PATHS = (
    "src/",
    "dbt/",
    "airflow/",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "infra/airflow/Dockerfile",
    "infra/airflow/requirements-airflow.txt",
    "infra/airflow/compose.yaml",
)
BODY_LIMIT = 10_000  # healthchecks.io keeps the first 10 kB of a ping body


def ping_base(path: Path = SECRET) -> str:
    base = path.read_text().strip() if path.is_file() else ""
    if not base.startswith("https://"):
        # Never echo the value: the base URL carries the ping key.
        raise RuntimeError(f"{path} is missing, empty or not an https URL")
    return base.rstrip("/")


def ping(
    slug: str,
    suffix: str = "",
    body: str = "",
    *,
    base: str | None = None,
    opener: Callable = urllib.request.urlopen,
) -> None:
    request = urllib.request.Request(
        f"{base or ping_base()}/{slug}{suffix}",
        data=body.encode()[:BODY_LIMIT],
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            status = response.status
    except (OSError, ValueError) as error:  # URLError, HTTPError and timeouts are OSErrors
        # The exception text can carry the URL, and the URL carries the ping key. The status code
        # is safe and says what went wrong (404: no check has this slug under this ping key).
        code = getattr(error, "code", None)
        status = f" {code}" if isinstance(code, int) else ""
        raise RuntimeError(f"ping {slug}{suffix} failed: {type(error).__name__}{status}") from None
    if status != 200:
        raise RuntimeError(f"ping {slug}{suffix} answered HTTP {status}")


def _github_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "whd-airflow-drift"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def drift_files(revision: str, *, fetch: Callable[[str], dict] = _github_json) -> list[str]:
    """Files that decide the stack's behaviour and changed on main since `revision`."""
    if not revision:
        raise RuntimeError("PIPELINE_REVISION is empty; build the image with deploy.sh")
    data = fetch(f"https://api.github.com/repos/{REPO}/compare/{revision}...main")
    names = (entry.get("filename", "") for entry in data.get("files") or [])
    return sorted(name for name in names if name.startswith(IMAGE_PATHS))

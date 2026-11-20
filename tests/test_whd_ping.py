import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "airflow" / "dags"))
from whd_ping import drift_files, ping, ping_base

BASE = "https://hc-ping.example/PINGKEY-not-real"


class Response:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ping_base_fails_closed_and_never_echoes_the_value(tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        ping_base(tmp_path / "absent")
    (tmp_path / "base").write_text("http://PINGKEY-not-real\n")
    with pytest.raises(RuntimeError) as caught:
        ping_base(tmp_path / "base")
    assert "PINGKEY" not in str(caught.value)
    (tmp_path / "base").write_text(BASE + "/\n")
    assert ping_base(tmp_path / "base") == BASE


def test_ping_posts_slug_suffix_and_a_capped_body():
    sent = []

    def opener(request, timeout):
        sent.append((request.full_url, request.get_method(), request.data, timeout))
        return Response()

    ping("whd-weekly", "/fail", "x" * 20_000, base=BASE, opener=opener)
    ((url, method, data, timeout),) = sent
    assert (url, method, len(data), timeout) == (f"{BASE}/whd-weekly/fail", "POST", 10_000, 10)


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError(f"cannot reach {BASE}/whd-weekly"),
        urllib.error.HTTPError(f"{BASE}/whd-weekly", 404, "nope", {}, None),
        TimeoutError(f"timed out {BASE}"),
    ],
)
def test_ping_failure_hides_the_url(failure):
    def opener(request, timeout):
        raise failure

    with pytest.raises(RuntimeError) as caught:
        ping("whd-weekly", base=BASE, opener=opener)
    assert "PINGKEY" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    if isinstance(failure, urllib.error.HTTPError):
        assert str(caught.value) == "ping whd-weekly failed: HTTPError 404"


def test_ping_rejects_a_non_200_answer():
    with pytest.raises(RuntimeError, match="HTTP 201"):
        ping("whd-weekly", base=BASE, opener=lambda request, timeout: Response(201))


def test_drift_counts_only_files_that_change_the_stack():
    asked = []

    def fetch(url):
        asked.append(url)
        return {
            "files": [
                {"filename": "docs/retro/2026-11-20-x.md"},
                {"filename": "README.md"},
                {"filename": "infra/airflow/README.md"},
                {"filename": "src/pipeline/ingest.py"},
                {"filename": "infra/airflow/Dockerfile"},
                {"filename": "uv.lock"},
            ]
        }

    assert drift_files("abc1234", fetch=fetch) == [
        "infra/airflow/Dockerfile",
        "src/pipeline/ingest.py",
        "uv.lock",
    ]
    assert asked == [
        "https://api.github.com/repos/ZrobDev/dol-wage-compliance-pipeline/compare/abc1234...main"
    ]
    assert drift_files("abc1234", fetch=lambda url: {"files": [{"filename": "docs/a.md"}]}) == []
    assert drift_files("abc1234", fetch=lambda url: {"status": "identical", "files": []}) == []


def test_drift_refuses_an_image_without_a_revision():
    with pytest.raises(RuntimeError, match="PIPELINE_REVISION"):
        drift_files("", fetch=lambda url: {})

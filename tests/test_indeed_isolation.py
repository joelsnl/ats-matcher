import builtins
import json
import subprocess
from types import SimpleNamespace

import pytest

from ats_matcher.config import Settings
from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.registry import default_registry
from ats_matcher.jobs.providers.indeed import _isolated_scrape


def test_readiness_does_not_import_jobspy(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "jobspy" or name.startswith("jobspy."):
            pytest.fail("Readiness must not load JobSpy's native libraries")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert any(p["id"] == "indeed" for p in default_registry(Settings()).list_with_readiness())


def test_worker_returns_records(monkeypatch):
    def run(command, **kwargs):
        assert command[-1] == "ats_matcher.jobs.providers.indeed_worker"
        assert json.loads(kwargs["input"])["search_term"] == "engineer"
        return SimpleNamespace(returncode=0, stdout='[{"title":"Engineer"}]')

    monkeypatch.setattr(subprocess, "run", run)
    assert _isolated_scrape(search_term="engineer") == [{"title": "Engineer"}]


@pytest.mark.parametrize("timeout", [False, True])
def test_worker_failure_is_a_provider_error(monkeypatch, timeout):
    def run(command, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(command, 120)
        return SimpleNamespace(returncode=0x80000003, stdout="")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ProviderError) as error:
        _isolated_scrape(search_term="engineer")
    assert error.value.code == "fetch_error"

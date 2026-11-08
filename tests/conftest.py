"""Load job-tracker.py for testing without Google credentials or libraries."""
import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


@pytest.fixture(scope="session")
def tracker():
    """The job-tracker module, with the Google client libraries stubbed out."""
    import os

    os.environ.setdefault("SHEET_ID", "test-sheet-id")
    _stub("google")
    _stub("google.auth")
    _stub("google.auth.transport")
    _stub("google.auth.transport.requests", Request=object)
    _stub("google_auth_oauthlib")
    _stub("google_auth_oauthlib.flow", InstalledAppFlow=object)
    _stub("googleapiclient")
    _stub("googleapiclient.discovery", build=lambda *a, **k: None)

    spec = importlib.util.spec_from_file_location("job_tracker", ROOT / "job-tracker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

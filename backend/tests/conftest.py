"""Legacy tests opt into localhost compatibility; production defaults protected."""
import pytest

@pytest.fixture(autouse=True)
def local_legacy_compat(monkeypatch):
    monkeypatch.setenv("P2X_DEPLOYMENT_MODE", "local")

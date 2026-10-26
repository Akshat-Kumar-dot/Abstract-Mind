"""The extension popup preview at /_dev/extension/ is for local development only."""
from fastapi.testclient import TestClient

from app.main import create_app

from .helpers import client


def test_popup_preview_is_served_in_development():
    api = client()
    page = api.get("/_dev/extension/")
    assert page.status_code == 200
    assert page.text.index('src="chrome-stub.js"') < page.text.index('src="shared.js"')   # stub loads first
    assert api.get("/_dev/extension/chrome-stub.js").status_code == 200
    assert api.get("/_dev/extension/popup.js").status_code == 200
    assert api.get("/_dev/extension/lib/vault.js").status_code == 200


def test_popup_preview_does_not_exist_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    api = TestClient(create_app(), base_url="https://testserver")
    for path in ("/_dev/extension/", "/_dev/extension/chrome-stub.js", "/_dev/extension/popup.js"):
        assert api.get(path).status_code == 404, path

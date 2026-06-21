import pytest


def test_health_and_widget(booted_pack, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from paw_helper import common
    monkeypatch.setenv("PAW_HELPER_CONTENT", str(booted_pack))
    common.set_content_dir(booted_pack)

    # Imported after the content dir is set, so PIPE binds to the booted pack.
    from paw_helper.server.app import app

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert "page_classifier" in body["programs"]
    assert body["n_serving"] == 3  # no offline tools in this pack

    widget = client.get("/widget.js")
    assert widget.status_code == 200
    assert "application/javascript" in widget.headers["content-type"]
    assert widget.headers["access-control-allow-origin"] == "*"

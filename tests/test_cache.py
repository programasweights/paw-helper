import time

from paw_helper.cache import TTLCache


def test_disabled_when_ttl_zero():
    c = TTLCache(ttl_s=0)
    assert not c.enabled
    c.set("k", 1)
    assert c.get("k") is None  # never stores when disabled


def test_hit_then_expiry():
    c = TTLCache(ttl_s=0.05)
    c.set("k", {"type": "answer"})
    assert c.get("k") == {"type": "answer"}
    time.sleep(0.08)
    assert c.get("k") is None  # expired


def test_lru_eviction():
    c = TTLCache(ttl_s=100, max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")           # touch a -> b is now the oldest
    c.set("c", 3)        # evicts b
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_ask_uses_cache_and_skips_pipeline(booted_pack, monkeypatch):
    import pytest
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from paw_helper import common
    monkeypatch.setenv("PAW_HELPER_CONTENT", str(booted_pack))
    common.set_content_dir(booted_pack)

    from paw_helper.server import app as app_mod

    calls = {"n": 0}

    def fake_run(query, page="site"):
        calls["n"] += 1
        return {"result": {"type": "answer", "text": "hi"}, "domain": "site",
                "route": "question", "verdict": "yes"}

    monkeypatch.setattr(app_mod.PIPE, "run", fake_run)
    app_mod._CACHE = app_mod.cache_mod.TTLCache(ttl_s=60)  # enable for the test

    client = TestClient(app_mod.app)
    body = {"query": "what do you research", "page": "site"}
    r1 = client.post("/ask", json=body).json()
    r2 = client.post("/ask", json=body).json()
    assert r1 == r2 == {"type": "answer", "text": "hi"}
    assert calls["n"] == 1  # second request served from cache, pipeline not re-run

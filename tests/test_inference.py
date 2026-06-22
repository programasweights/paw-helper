from paw_helper import common, inference, pipeline


class FakeBackend:
    def __init__(self):
        self.calls = []

    def infer(self, name: str, text: str, max_tokens: int) -> str:
        self.calls.append((name, text, max_tokens))
        return "cv"


def test_pipeline_uses_injected_backend(booted_pack):
    common.set_content_dir(booted_pack)
    backend = FakeBackend()
    p = pipeline.Pipeline(inference_backend=backend)

    assert p.classify("site", "where is your cv") == "cv"
    assert backend.calls == [("page_classifier", "where is your cv", 8)]


def test_remote_infer_backend_posts_expected_payload(monkeypatch):
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": " docs "}

    def fake_post(endpoint, json, headers, timeout):
        calls.append((endpoint, json, headers, timeout))
        return Resp()

    monkeypatch.setattr(inference, "_auth_headers", lambda: {"Content-Type": "application/json"})
    monkeypatch.setattr(inference.httpx, "post", fake_post)

    backend = inference.RemoteInferBackend(
        {"page_classifier": "abc123"},
        endpoint="https://programasweights.com/api/v1/infer",
        timeout_s=12,
    )

    assert backend.infer("page_classifier", "documentation", 8) == "docs"
    assert calls == [(
        "https://programasweights.com/api/v1/infer",
        {
            "program_id": "abc123",
            "input": "documentation",
            "max_tokens": 8,
            "temperature": 0.0,
        },
        {"Content-Type": "application/json"},
        12,
    )]


def test_get_backend_selects_remote(monkeypatch):
    monkeypatch.setattr(inference, "_auth_headers", lambda: {})
    backend = inference.get_backend({"p": "id"}, mode="remote_infer")
    assert isinstance(backend, inference.RemoteInferBackend)

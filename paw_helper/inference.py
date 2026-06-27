"""Inference backends for running pinned PAW helper programs.

The pipeline is intentionally backend-agnostic: evals, the server, and content
packs should not care whether a PAW call runs through the local SDK runtime or
the central PAW `/api/v1/infer` endpoint.
"""

from __future__ import annotations

import os
import threading
from typing import Protocol

import httpx


class InferenceBackend(Protocol):
    def infer(self, name: str, text: str, max_tokens: int) -> str:
        """Run a named helper program and return stripped text output."""


# Backend mode aliases that select the offline/demo MockBackend (no PAW account,
# API key, or compiled programs.json required).
_MOCK_MODES = {"mock", "offline", "echo"}


def is_mock_mode(mode: str | None = None) -> bool:
    """True when the (env-)selected backend is the offline mock. The pipeline reads
    this to skip the programs.json requirement and run the no-compile demo."""
    mode = (mode or os.environ.get("PAW_HELPER_INFERENCE_BACKEND") or "local_sdk").strip().lower()
    return mode in _MOCK_MODES


class MockBackend:
    """Offline/demo backend: deterministic canned outputs with NO PAW account, API
    key, or compiled programs.json. Lets `paw-helper init -> validate -> serve` answer
    end-to-end so an adopter sees the shape before compiling anything. It branches on
    the program ROLE name (the pipeline always passes the role name, never an ID):
    validators say "yes", classifiers/routers/selectors/gates take the answer path,
    and every answerer returns a fixed placeholder string. It is never the default and
    must be selected explicitly via PAW_HELPER_INFERENCE_BACKEND=mock."""

    PLACEHOLDER = (
        "This is a placeholder answer from the paw-helper mock backend. Edit your "
        "content pack, then `paw-helper compile` and serve with a real backend "
        "(local_sdk or remote_infer) for grounded answers."
    )

    def __init__(self, programs: dict[str, str] | None = None):
        self.programs = programs or {}

    def infer(self, name: str, text: str, max_tokens: int) -> str:
        n = name.lower()
        if "validator" in n:
            return "yes"  # keep the answer (backtrack gates on a "yes" verdict)
        if any(k in n for k in ("classifier", "router", "selector", "gate")):
            # Route to the freeform answer path / no link / no branch selection, so
            # the demo deterministically shows an answer regardless of the query.
            return "question"
        return self.PLACEHOLDER


class LocalSdkBackend:
    """Current behavior: load and run PAW functions in this Python process."""

    def __init__(self, programs: dict[str, str]):
        self.programs = programs
        self._fns: dict[str, object] = {}
        self._lock = threading.Lock()

    def _fn(self, name: str):
        import programasweights as paw

        if name not in self._fns:
            self._fns[name] = paw.function(self.programs[name])
        return self._fns[name]

    def infer(self, name: str, text: str, max_tokens: int) -> str:
        with self._lock:
            return self._fn(name)(text, max_tokens=max_tokens, temperature=0.0).strip()


class RemoteInferBackend:
    """Run PAW inference through the central PAW API `/api/v1/infer` endpoint."""

    def __init__(
        self,
        programs: dict[str, str],
        endpoint: str | None = None,
        timeout_s: float | None = None,
    ):
        self.programs = programs
        self.endpoint = endpoint or _default_infer_endpoint()
        self.timeout_s = timeout_s or float(os.environ.get("PAW_HELPER_INFER_TIMEOUT_S", "60"))
        self._headers = _auth_headers()

    def infer(self, name: str, text: str, max_tokens: int) -> str:
        # The API can transiently return an EMPTY output (e.g. when rate-limited
        # under burst load) or a 429/5xx. These helper programs never legitimately
        # return empty, so an empty/error response is a transient failure: retry with
        # a short backoff rather than letting the helper answer with "" (which would
        # surface as a blank/"I don't have that" answer in production).
        import time

        body = {
            "program_id": self.programs[name],
            "input": text,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        last = ""
        for attempt in range(4):
            try:
                resp = httpx.post(self.endpoint, json=body, headers=self._headers,
                                  timeout=self.timeout_s)
                resp.raise_for_status()
                last = str(resp.json().get("output", "")).strip()
                if last:
                    return last
            except httpx.HTTPError:
                pass
            if attempt < 3:
                time.sleep(0.5 * (attempt + 1))
        return last


def _default_infer_endpoint() -> str:
    explicit = os.environ.get("PAW_HELPER_INFER_ENDPOINT")
    if explicit:
        return explicit
    api_url = os.environ.get("PAW_API_URL")
    if not api_url:
        try:
            from programasweights.config import get_api_url

            api_url = get_api_url()
        except Exception:
            api_url = "https://programasweights.com"
    return f"{api_url.rstrip('/')}/api/v1/infer"


def _auth_headers() -> dict[str, str]:
    """Reuse PAW SDK auth headers when available; otherwise fall back to JSON."""
    try:
        from programasweights.client import PAWClient
        from programasweights.config import get_api_key, get_api_url

        return PAWClient(api_url=get_api_url(), api_key=get_api_key())._headers()
    except Exception:
        return {"Content-Type": "application/json"}


def get_backend(programs: dict[str, str], mode: str | None = None) -> InferenceBackend:
    mode = (mode or os.environ.get("PAW_HELPER_INFERENCE_BACKEND") or "local_sdk").strip().lower()
    if mode in {"local", "local_sdk", "sdk"}:
        return LocalSdkBackend(programs)
    if mode in {"remote", "remote_infer", "api", "infer"}:
        return RemoteInferBackend(programs)
    if mode in _MOCK_MODES:
        return MockBackend(programs)
    raise ValueError(
        "unknown PAW_HELPER_INFERENCE_BACKEND="
        f"{mode!r}; expected local_sdk, remote_infer, or mock"
    )

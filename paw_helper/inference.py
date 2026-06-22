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
        resp = httpx.post(
            self.endpoint,
            json={
                "program_id": self.programs[name],
                "input": text,
                "max_tokens": max_tokens,
                "temperature": 0.0,
            },
            headers=self._headers,
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        return str(resp.json().get("output", "")).strip()


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
    raise ValueError(
        "unknown PAW_HELPER_INFERENCE_BACKEND="
        f"{mode!r}; expected local_sdk or remote_infer"
    )

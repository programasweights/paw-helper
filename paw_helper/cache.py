"""A tiny thread-safe TTL + LRU cache for /ask responses.

Optional load-hardening for high-traffic bursts (e.g. a launch/demo): the same few
questions get asked over and over, and helper answers are deterministic (temperature 0),
so a short-lived cache absorbs most of the load without changing behavior. Disabled by
default (ttl_s <= 0); the server enables it from HELPER_CACHE_TTL_S. Keys are per (page,
normalized query), so different pages/sites never share an entry.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, ttl_s: float, max_entries: int = 512):
        self.ttl = float(ttl_s)
        self.max = max(1, int(max_entries))
        self._d: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.ttl > 0

    def get(self, key: str):
        if not self.enabled:
            return None
        now = time.time()
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < now:
                del self._d[key]
                return None
            self._d.move_to_end(key)  # LRU: mark recently used
            return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._d[key] = (time.time() + self.ttl, value)
            self._d.move_to_end(key)
            while len(self._d) > self.max:
                self._d.popitem(last=False)  # evict oldest

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

from __future__ import annotations
from collections import OrderedDict
from threading import Lock
from time import monotonic
from ats_matcher.schemas.jobs import ProviderResult


class JobCache:
    """Bounded, in-memory cache. Callers cannot mutate cached results."""
    def __init__(self, ttl: float = 3600, max_entries: int = 128, clock=monotonic):
        self.ttl, self.max_entries, self.clock = ttl, max_entries, clock
        self._entries = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> ProviderResult | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires, result = entry
            if expires <= self.clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return result.model_copy(deep=True)

    def set(self, key: str, result: ProviderResult) -> None:
        if self.ttl <= 0 or self.max_entries <= 0:
            return
        with self._lock:
            self._entries[key] = (self.clock() + self.ttl, result.model_copy(deep=True))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

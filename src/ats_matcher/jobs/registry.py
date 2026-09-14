from __future__ import annotations
from threading import Lock
from ats_matcher.config import Settings
from ats_matcher.jobs.providers.linkedin import LinkedInProvider


class ProviderRegistry:
    """Register a factory once. The CLI and HTTP API share its provider contract."""
    def __init__(self):
        self._factories, self._instances, self._labels = {}, {}, {}
        self._lock = Lock()

    def register(self, name, factory, *, label=None):
        name = name.strip().lower()
        if not name or name in self._factories:
            raise ValueError(f"Invalid or duplicate job provider: {name}")
        self._factories[name], self._labels[name] = factory, label or name

    def get(self, name):
        with self._lock:
            if name not in self._factories:
                raise ValueError(f"Unknown job provider '{name}'. Available: {', '.join(self._factories)}")
            if name not in self._instances:
                self._instances[name] = self._factories[name]()
            return self._instances[name]

    def list(self):
        return [{"id": name, "label": self._labels[name]} for name in self._factories]


def default_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        "linkedin",
        lambda: LinkedInProvider(
            timeout=settings.jobs_timeout,
            delay=settings.jobs_request_delay,
            retries=settings.jobs_retries,
            max_pages=settings.jobs_max_pages,
            cache_ttl=settings.jobs_cache_ttl,
            fetch_descriptions=settings.jobs_fetch_descriptions,
        ),
        label="LinkedIn",
    )
    return registry

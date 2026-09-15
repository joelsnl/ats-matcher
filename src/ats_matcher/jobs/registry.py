from __future__ import annotations
from threading import Lock
from ats_matcher.config import Settings
from ats_matcher.jobs.providers.linkedin import LinkedInProvider
from ats_matcher.jobs.providers.indeed import IndeedProvider
from ats_matcher.jobs.providers.freehire import FreehireProvider
from ats_matcher.jobs.providers.greenhouse import GreenhouseProvider
from ats_matcher.jobs.providers.lever import LeverProvider
from ats_matcher.jobs.providers.ashby import AshbyProvider
from ats_matcher.jobs.provider_readiness import get_provider_readiness


class ProviderRegistry:
    """Register a factory once. The CLI and HTTP API share its provider contract."""
    def __init__(self, settings: Settings | None = None):
        self._factories, self._instances, self._labels = {}, {}, {}
        self._lock = Lock()
        self._settings = settings

    def set_settings(self, settings: Settings) -> None:
        """Set settings for readiness checking."""
        self._settings = settings

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

    def list_with_readiness(self):
        """List providers with readiness metadata."""
        result = []
        for name in self._factories:
            provider_info = {"id": name, "label": self._labels[name]}
            if self._settings:
                readiness = get_provider_readiness(name, self._settings, self)
                provider_info["readiness"] = readiness.model_dump(mode="json")
            result.append(provider_info)
        return result


def default_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry(settings)
    public_options = dict(timeout=settings.jobs_timeout, delay=settings.jobs_request_delay,
                          retries=settings.jobs_retries, cache_ttl=settings.jobs_cache_ttl,
                          fetch_descriptions=settings.jobs_fetch_descriptions)
    registry.register("linkedin", lambda: LinkedInProvider(**public_options, max_pages=settings.jobs_max_pages), label="LinkedIn")
    for name, adapter, label in (("greenhouse", GreenhouseProvider, "Greenhouse"),
                                  ("lever", LeverProvider, "Lever"), ("ashby", AshbyProvider, "Ashby")):
        configured = getattr(settings, f"jobs_{name}_boards")
        boards = None if configured is None else [token.strip() for token in configured.split(",") if token.strip()]
        registry.register(name, lambda adapter=adapter, boards=boards: adapter(
            **public_options, boards=boards, max_pages=settings.jobs_max_pages), label=label)
    registry.register("freehire", lambda: FreehireProvider(**public_options), label="Freehire")
    registry.register("indeed", lambda: IndeedProvider(country=settings.jobs_indeed_country,
        cache_ttl=settings.jobs_cache_ttl, fetch_descriptions=settings.jobs_fetch_descriptions), label="Indeed")
    return registry

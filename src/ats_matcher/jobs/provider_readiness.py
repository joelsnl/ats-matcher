"""Provider readiness detection and metadata management."""
from __future__ import annotations

import logging
from importlib.util import find_spec
from datetime import datetime, timezone
from typing import Optional

from ats_matcher.schemas.jobs import ProviderReadiness


logger = logging.getLogger(__name__)


class ProviderMetadata:
    """Collects and manages provider capability metadata."""

    def __init__(self):
        self._metadata: dict[str, ProviderReadiness] = {}
        self._check_times: dict[str, str] = {}

    def register_metadata(self, provider_id: str, metadata: ProviderReadiness) -> None:
        """Register metadata for a provider."""
        self._metadata[provider_id] = metadata
        self._check_times[provider_id] = datetime.now(timezone.utc).isoformat()

    def get_metadata(self, provider_id: str) -> ProviderReadiness:
        """Get metadata for a provider, or a default unavailable state."""
        if provider_id in self._metadata:
            metadata = self._metadata[provider_id]
            # Update last_check timestamp
            metadata.last_check = self._check_times.get(provider_id)
            return metadata
        return ProviderReadiness(available=False, unavailable_reason="Provider metadata not loaded")

    def mark_unavailable(self, provider_id: str, reason: str) -> None:
        """Mark a provider as unavailable with a reason."""
        metadata = self._metadata.get(provider_id) or ProviderReadiness()
        metadata.available = False
        metadata.unavailable_reason = reason
        self.register_metadata(provider_id, metadata)

    def mark_available(self, provider_id: str, boards: int = 0) -> None:
        """Mark a provider as available."""
        metadata = self._metadata.get(provider_id) or ProviderReadiness()
        metadata.available = True
        metadata.unavailable_reason = None
        metadata.configured_boards = boards
        self.register_metadata(provider_id, metadata)


def get_provider_readiness(provider_id: str, settings, registry) -> ProviderReadiness:
    """Determine if a provider is ready and collect its metadata."""

    readiness = ProviderReadiness()
    readiness.last_check = datetime.now(timezone.utc).isoformat()

    if provider_id == "linkedin":
        readiness.kind = "job_site"
        readiness.available = True
        readiness.supported_filters = [
            "keywords", "location", "workplace_type", "job_type",
            "experience_level", "date_since_posted", "salary", "has_verification"
        ]
        readiness.unsupported_filters = ["career_url"]
        readiness.default_date_behavior = "past_week"
        readiness.countries = ["worldwide"]

    elif provider_id == "indeed":
        readiness.kind = "job_site"
        readiness.default_date_behavior = "any"
        readiness.supported_filters = ["keywords", "location", "date_since_posted"]
        readiness.unsupported_filters = ["workplace_type", "job_type", "experience_level", "salary", "has_verification"]
        readiness.countries = ["usa", "uk", "canada", "australia", "france", "germany", "netherlands", "se"]
        # Check if JobSpy is installed
        if find_spec("jobspy") is not None:
            readiness.available = True
        else:
            readiness.available = False
            readiness.unavailable_reason = 'Install with: pip install ".[indeed]"'
            readiness.requires_dependency = "python-jobspy"

    elif provider_id in ("greenhouse", "lever", "ashby"):
        readiness.kind = "company_board"
        readiness.unsupported_filters = ["experience_level", "salary", "has_verification", "under_10_applicants"]

        # Count configured boards
        boards_config = getattr(settings, f"jobs_{provider_id}_boards", None)
        if boards_config:
            board_list = [b.strip() for b in boards_config.split(",") if b.strip()]
            readiness.configured_boards = len(board_list)
        else:
            # Count default boards from company registry
            try:
                from ats_matcher.jobs.company_registry import CompanyRegistry
                registry_obj = CompanyRegistry()
                defaults = [c.board_slug for c in registry_obj.list_by_ats(provider_id)]
                readiness.configured_boards = len(defaults)
            except Exception as e:
                logger.warning(f"Could not load default {provider_id} boards: {e}")

        readiness.available = readiness.configured_boards > 0
        if not readiness.available:
            readiness.unavailable_reason = f"No {provider_id.capitalize()} boards configured"

        readiness.supported_filters = ["keywords", "location", "date_since_posted"]
        if provider_id == "greenhouse":
            readiness.default_date_behavior = "any"
        else:
            readiness.default_date_behavior = "any"
        readiness.countries = ["worldwide"]

    elif provider_id == "freehire":
        readiness.kind = "job_site"
        readiness.available = True
        readiness.supported_filters = ["keywords", "location", "date_since_posted", "job_type", "workplace_type"]
        readiness.unsupported_filters = ["experience_level", "salary", "has_verification", "temporary", "volunteer"]
        readiness.default_date_behavior = "any"
        readiness.countries = ["worldwide"]

    return readiness

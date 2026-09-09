from __future__ import annotations

from ats_matcher.schemas.cv import CvExtract
from ats_matcher.schemas.profile import GitHubProfile


class GitHubEnricher:
    """Official GitHub API enricher. Implemented in Phase 3."""

    def enrich(self, profile: CvExtract) -> GitHubProfile:
        raise NotImplementedError("GitHub enrichment is Phase 3.")

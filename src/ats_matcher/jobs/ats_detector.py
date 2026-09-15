"""Recognize hosted career URLs without fetching user-supplied pages."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

BOARD_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
SEARCHABLE_ATS = frozenset({"greenhouse", "lever", "ashby"})


class ATSDetector:
    @staticmethod
    def detect(url: str) -> tuple[str, str] | None:
        if not isinstance(url, str) or not url.strip():
            return None
        value = url.strip()
        if "://" not in value:
            value = "https://" + value
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                return None
            if parsed.port not in {None, 80, 443}:
                return None
            host = (parsed.hostname or "").lower()
        except ValueError:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        routes = {
            "boards.greenhouse.io": ("greenhouse", 0),
            "job-boards.greenhouse.io": ("greenhouse", 0),
            "boards-api.greenhouse.io": ("greenhouse", 2),
            "jobs.lever.co": ("lever", 0),
            "api.lever.co": ("lever", 2),
            "jobs.eu.lever.co": ("lever", 0),
            "api.eu.lever.co": ("lever", 2),
            "jobs.ashbyhq.com": ("ashby", 0),
            "api.ashbyhq.com": ("ashby", 2),
            "jobs.smartrecruiters.com": ("smartrecruiters", 0),
        }
        if host in routes:
            ats, index = routes[host]
            prefixes = {"greenhouse": ["v1", "boards"], "lever": ["v0", "postings"], "ashby": ["posting-api", "job-board"]}
            if index and parts[:index] != prefixes[ats]:
                return None
            if len(parts) <= index or not BOARD_SLUG.fullmatch(parts[index]):
                return None
            slug = parts[index]
            return ats, ("eu:" + slug if host.endswith("eu.lever.co") else slug)
        for suffix, ats in (("greenhouse.io", "greenhouse"), ("lever.co", "lever"),
                            ("ashbyhq.com", "ashby"), ("myworkdayjobs.com", "workday"),
                            ("teamtailor.com", "teamtailor"), ("recruitee.com", "recruitee"),
                            ("icims.com", "icims"), ("workable.com", "workable")):
            if host.endswith("." + suffix):
                subdomain = host[:-(len(suffix) + 1)]
                if ats == "workday":
                    subdomain = subdomain.split(".")[0]
                if subdomain not in {"www", "api", "jobs", "boards", "apply"} and BOARD_SLUG.fullmatch(subdomain):
                    return ats, subdomain
        return None

    @staticmethod
    def suggest_providers(url: str) -> list[str]:
        match = ATSDetector.detect(url)
        return [match[0]] if match and match[0] in SEARCHABLE_ATS else []

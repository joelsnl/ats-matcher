"""Packaged example boards; this is not a comprehensive company directory."""
from __future__ import annotations

import csv
from importlib.resources import files
from typing import NamedTuple


class Company(NamedTuple):
    slug: str
    name: str
    industry: str
    ats_type: str
    board_slug: str
    country: str
    hq_location: str


class CompanyRegistry:
    def __init__(self):
        self.companies: dict[str, Company] = {}
        self.by_board: dict[tuple[str, str], Company] = {}
        resource = files("ats_matcher.jobs").joinpath("data/companies.csv")
        with resource.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                company = Company(**{key: value.strip() for key, value in row.items()})
                if company.slug in self.companies or (company.ats_type, company.board_slug) in self.by_board:
                    raise ValueError(f"Duplicate company board: {company.slug}")
                self.companies[company.slug] = company
                self.by_board[company.ats_type, company.board_slug] = company

    def search(self, query: str) -> list[Company]:
        query = query.casefold().strip()
        if not query:
            return []
        matches = [c for c in self.companies.values() if query in c.name.casefold() or query in c.slug.casefold()]
        return sorted(matches, key=lambda c: (query not in {c.slug.casefold(), c.name.casefold()}, c.name.casefold()))[:10]

    def get(self, slug: str) -> Company | None:
        return self.companies.get(slug.strip().lower())

    def get_by_board(self, ats_type: str, board_slug: str) -> Company | None:
        return self.by_board.get((ats_type, board_slug))

    def list_by_ats(self, ats_type: str) -> list[Company]:
        return [c for c in self.companies.values() if c.ats_type == ats_type.strip().lower()]

    def list_all(self) -> list[Company]:
        return sorted(self.companies.values(), key=lambda c: c.name.casefold())

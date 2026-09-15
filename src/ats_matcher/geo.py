"""Turn extracted CV locations into LinkedIn-friendly 'City, Country' queries."""
from __future__ import annotations

from ats_matcher.schemas.cv import Location

# ISO 3166-1 alpha-2 plus a few alpha-3 / aliases LinkedIn search understands.
_COUNTRY_NAMES: dict[str, str] = {
    "ad": "Andorra", "ae": "United Arab Emirates", "af": "Afghanistan", "al": "Albania",
    "am": "Armenia", "ao": "Angola", "ar": "Argentina", "at": "Austria", "au": "Australia",
    "az": "Azerbaijan", "ba": "Bosnia and Herzegovina", "bd": "Bangladesh", "be": "Belgium",
    "bg": "Bulgaria", "bh": "Bahrain", "br": "Brazil", "by": "Belarus", "ca": "Canada",
    "ch": "Switzerland", "cl": "Chile", "cn": "China", "co": "Colombia", "cr": "Costa Rica",
    "cy": "Cyprus", "cz": "Czechia", "de": "Germany", "deu": "Germany", "dk": "Denmark",
    "ee": "Estonia", "eg": "Egypt", "es": "Spain", "fi": "Finland", "fr": "France",
    "gb": "United Kingdom", "ge": "Georgia", "gr": "Greece", "hk": "Hong Kong",
    "hr": "Croatia", "hu": "Hungary", "id": "Indonesia", "ie": "Ireland", "il": "Israel",
    "in": "India", "iq": "Iraq", "ir": "Iran", "is": "Iceland", "it": "Italy",
    "jp": "Japan", "ke": "Kenya", "kr": "South Korea", "kw": "Kuwait", "kz": "Kazakhstan",
    "lb": "Lebanon", "lk": "Sri Lanka", "lt": "Lithuania", "lu": "Luxembourg", "lv": "Latvia",
    "ma": "Morocco", "mt": "Malta", "mx": "Mexico", "my": "Malaysia", "ng": "Nigeria",
    "nl": "Netherlands", "nld": "Netherlands", "no": "Norway", "np": "Nepal", "nz": "New Zealand",
    "om": "Oman", "pe": "Peru", "ph": "Philippines", "pk": "Pakistan", "pl": "Poland",
    "pt": "Portugal", "qa": "Qatar", "ro": "Romania", "rs": "Serbia", "ru": "Russia",
    "sa": "Saudi Arabia", "se": "Sweden", "sg": "Singapore", "si": "Slovenia", "sk": "Slovakia",
    "th": "Thailand", "tr": "Turkey", "tw": "Taiwan", "ua": "Ukraine", "uk": "United Kingdom",
    "us": "United States", "usa": "United States", "uy": "Uruguay", "uz": "Uzbekistan",
    "vn": "Vietnam", "za": "South Africa",
    "the netherlands": "Netherlands", "holland": "Netherlands",
    "united states of america": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "great britain": "United Kingdom", "england": "United Kingdom",
    "czech republic": "Czechia", "south korea": "South Korea", "korea": "South Korea",
}

# Unambiguous city → country fills when the CV only names the city.
_CITY_COUNTRY: dict[str, str] = {
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands",
    "eindhoven": "Netherlands", "the hague": "Netherlands", "den haag": "Netherlands",
    "groningen": "Netherlands", "haarlem": "Netherlands", "tilburg": "Netherlands",
    "berlin": "Germany", "munich": "Germany", "münchen": "Germany", "hamburg": "Germany",
    "frankfurt": "Germany", "cologne": "Germany", "köln": "Germany", "stuttgart": "Germany",
    "düsseldorf": "Germany", "dortmund": "Germany", "nuremberg": "Germany",
    "vienna": "Austria", "wien": "Austria", "brussels": "Belgium", "brussel": "Belgium",
    "antwerp": "Belgium", "ghent": "Belgium", "zurich": "Switzerland", "zürich": "Switzerland",
    "geneva": "Switzerland", "basel": "Switzerland", "copenhagen": "Denmark",
    "stockholm": "Sweden", "gothenburg": "Sweden", "oslo": "Norway", "helsinki": "Finland",
    "dublin": "Ireland", "lisbon": "Portugal", "porto": "Portugal", "madrid": "Spain",
    "barcelona": "Spain", "valencia": "Spain", "rome": "Italy", "milan": "Italy",
    "milano": "Italy", "turin": "Italy", "naples": "Italy", "warsaw": "Poland",
    "krakow": "Poland", "kraków": "Poland", "prague": "Czechia", "praha": "Czechia",
    "budapest": "Hungary", "bucharest": "Romania", "sofia": "Bulgaria", "athens": "Greece",
    "tallinn": "Estonia", "riga": "Latvia", "vilnius": "Lithuania", "luxembourg": "Luxembourg",
    "london": "United Kingdom", "manchester": "United Kingdom", "edinburgh": "United Kingdom",
    "birmingham": "United Kingdom", "bristol": "United Kingdom", "leeds": "United Kingdom",
    "glasgow": "United Kingdom", "cambridge": "United Kingdom", "oxford": "United Kingdom",
    "paris": "France", "lyon": "France", "marseille": "France", "toulouse": "France",
    "lille": "France", "nantes": "France", "bordeaux": "France",
    "new york": "United States", "san francisco": "United States", "seattle": "United States",
    "austin": "United States", "boston": "United States", "chicago": "United States",
    "los angeles": "United States", "denver": "United States", "atlanta": "United States",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "ottawa": "Canada",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia",
    "singapore": "Singapore", "tokyo": "Japan", "osaka": "Japan", "seoul": "South Korea",
    "bangalore": "India", "bengaluru": "India", "hyderabad": "India", "mumbai": "India",
    "pune": "India", "chennai": "India", "delhi": "India", "new delhi": "India",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "tel aviv": "Israel", "cape town": "South Africa", "johannesburg": "South Africa",
    "sao paulo": "Brazil", "são paulo": "Brazil", "mexico city": "Mexico",
}


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def expand_country(value: str | None) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return _COUNTRY_NAMES.get(text.lower().replace(".", ""), text)


def country_for_city(city: str | None) -> str | None:
    text = _clean(city)
    if not text:
        return None
    return _CITY_COUNTRY.get(text.lower())


def enrich_location(location: Location) -> Location:
    """Fill a full country name when the city is unambiguous or the country is a code."""
    city = _clean(location.city)
    country = expand_country(location.country) or country_for_city(city)
    return location.model_copy(update={"city": city, "country": country, "raw": _clean(location.raw)})


def format_search_location(location: Location | None) -> str | None:
    """LinkedIn guest search is more reliable with 'City, Country' than a city alone."""
    if location is None:
        return None
    filled = enrich_location(location)
    city, country = filled.city, filled.country
    if city and country:
        if country.lower() in city.lower() or city.lower() in country.lower():
            return city
        return f"{city}, {country}"
    return city or country or _clean(filled.raw)


def normalize_location_str(value: str | None) -> str:
     """Normalize a location string for substring matching."""
     text = _clean(value)
     if not text:
         return ""
     # Lowercase and remove common punctuation/whitespace variations
     return text.lower().replace(",", "").replace("  ", " ").strip()


def locations_match_flexible(query_location: str | None, job_location: str | None) -> bool:
     """Check if job location matches query location with flexible matching.

     Handles:
     - "Berlin" matches "Berlin, Germany" or "Berlin"
     - "Germany" matches any location with "Germany"
     - "Berlin, Germany" matches "Berlin" or "Berlin, Germany"
     """
     if not query_location or not job_location:
         return not query_location and not job_location

     query_norm = normalize_location_str(query_location)
     job_norm = normalize_location_str(job_location)

     # Split by common delimiters to get components
     query_parts = [p.strip() for p in query_norm.split(" ") if p.strip()]
     job_text = job_norm

     # Check if all query parts are in the job location
     return all(part in job_text for part in query_parts)

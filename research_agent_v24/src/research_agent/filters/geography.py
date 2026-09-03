"""Vacancy-level geography filter; company discovery geography is deliberately ignored."""

from __future__ import annotations

from pathlib import Path

from research_agent.config import PROJECT_ROOT, load_yaml
from research_agent.filters.common import FilterResult, contains_term, normalize_text


class GeographyFilter:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or PROJECT_ROOT / "config" / "geographies.yaml"
        config = load_yaml(path)
        self.configuration = config
        self.target_countries = tuple(str(value) for value in config.get("target_countries", []))
        aliases = config.get("aliases", {})
        self.aliases = {
            normalize_text(str(alias)): str(country) for alias, country in aliases.items()
        }
        codes = config.get("country_codes", {})
        self.country_codes = {
            normalize_text(str(code)): str(country) for code, country in codes.items()
        }
        self.excluded_regions = tuple(
            str(value) for value in config.get("explicitly_excluded_regions", [])
        )
        self.excluded_countries = tuple(
            str(value) for value in config.get("explicitly_excluded_countries", [])
        )
        self.known_out_of_scope_countries = tuple(
            str(value) for value in config.get("known_out_of_scope_countries", [])
        )
        out_codes = config.get("out_of_scope_country_codes", {})
        self.out_of_scope_country_codes = {
            normalize_text(str(code)): str(country) for code, country in out_codes.items()
        }
        self.included_region_aliases = tuple(
            str(value) for value in config.get("included_region_aliases", [])
        )

    def evaluate(
        self,
        *,
        location: str,
        country: str | None = None,
        workplace_type: str | None = None,
    ) -> FilterResult:
        if country and country.strip():
            resolved = self._resolve_structured_country(country)
            if resolved in self.target_countries:
                return FilterResult(
                    status="INCLUDE",
                    reason="structured vacancy country is in target scope",
                    matched_terms=(resolved,),
                    category=resolved,
                )
            if resolved is not None:
                return FilterResult(
                    status="EXCLUDE",
                    reason="structured vacancy country is known and outside target scope",
                    matched_terms=(resolved,),
                )
            return FilterResult(
                status="REVIEW",
                reason="structured vacancy country is unknown to the configured taxonomy",
                matched_terms=(country.strip(),),
            )

        normalized_location = normalize_text(location)
        target_matches = self._target_matches(normalized_location)
        if target_matches:
            return FilterResult(
                status="INCLUDE",
                reason="vacancy location contains a target country",
                matched_terms=target_matches,
                category=target_matches[0],
            )

        excluded_matches = tuple(
            value
            for value in (*self.excluded_regions, *self.excluded_countries)
            if contains_term(normalized_location, value)
        )
        if excluded_matches:
            return FilterResult(
                status="EXCLUDE",
                reason="vacancy location is explicitly outside scope",
                matched_terms=excluded_matches,
            )

        included_regions = tuple(
            value
            for value in self.included_region_aliases
            if contains_term(normalized_location, value)
        )
        if included_regions:
            return FilterResult(
                status="INCLUDE",
                reason="vacancy location is explicitly EU-scoped",
                matched_terms=included_regions,
                category="European Union",
            )

        remote = normalize_text(workplace_type or "") == "remote" or contains_term(
            normalized_location, "remote"
        )
        if remote:
            return FilterResult(
                status="REVIEW",
                reason="remote vacancy has no unambiguous target country",
            )
        return FilterResult(
            status="REVIEW",
            reason="vacancy geography could not be resolved to target scope",
        )

    def _resolve_structured_country(self, value: str) -> str | None:
        normalized = normalize_text(value)
        canonical = {normalize_text(country): country for country in self.target_countries}
        known_out = {
            normalize_text(country): country
            for country in (*self.excluded_countries, *self.known_out_of_scope_countries)
        }
        return (
            canonical.get(normalized)
            or self.aliases.get(normalized)
            or self.country_codes.get(normalized)
            or known_out.get(normalized)
            or self.out_of_scope_country_codes.get(normalized)
        )

    def _target_matches(self, normalized_location: str) -> tuple[str, ...]:
        matched: list[str] = []
        for country in self.target_countries:
            if contains_term(normalized_location, country):
                matched.append(country)
        for alias, country in self.aliases.items():
            if contains_term(normalized_location, alias) and country not in matched:
                matched.append(country)
        return tuple(matched)

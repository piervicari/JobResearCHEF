"""Config-driven, broad cybersecurity relevance filter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_agent.config import PROJECT_ROOT, load_yaml
from research_agent.filters.common import FilterResult, contains_term, normalize_text


@dataclass(frozen=True)
class ContextualTerm:
    term: str
    category: str
    context_markers: tuple[str, ...]


class CyberFilter:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or PROJECT_ROOT / "config" / "cyber_keywords.yaml"
        config = load_yaml(path)
        self.configuration = config
        raw_categories = config.get("categories")
        if not isinstance(raw_categories, dict):
            raise ValueError("cyber_keywords.yaml must define a categories mapping")
        self.categories: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
            (str(category), tuple(str(term) for term in terms))
            for category, terms in raw_categories.items()
            if isinstance(terms, list)
        )
        raw_contextual = config.get("contextual_terms", [])
        self.contextual_terms = tuple(
            ContextualTerm(
                term=str(item["term"]),
                category=str(item["category"]),
                context_markers=tuple(str(marker) for marker in item["context_markers"]),
            )
            for item in raw_contextual
            if isinstance(item, dict)
        )
        self.negative_title_phrases = tuple(
            str(value) for value in config.get("negative_title_phrases", [])
        )
        self.negative_override_terms = tuple(
            str(value) for value in config.get("negative_override_terms", [])
        )
        self.always_excluded_title_functions = tuple(
            str(value) for value in config.get("always_excluded_title_functions", [])
        )
        self.description_only_title_markers = tuple(
            str(value) for value in config.get("description_only_title_markers", [])
        )
        self.generic_title_exclusions = tuple(
            str(value) for value in config.get("generic_title_exclusions", [])
        )
        self.description_only_title_exclusions = tuple(
            str(value) for value in config.get("description_only_title_exclusions", [])
        )

    def evaluate(
        self,
        *,
        title: str,
        description: str = "",
        employment_type: str | None = None,
    ) -> FilterResult:
        normalized_title = normalize_text(title)
        normalized_description = normalize_text(description)
        normalized_employment = normalize_text(employment_type or "")
        title_matches = self._category_matches(normalized_title)

        always_excluded = tuple(
            term
            for term in self.always_excluded_title_functions
            if contains_term(normalized_title, term)
        )
        if always_excluded:
            return FilterResult(
                status="EXCLUDE",
                reason="explicit non-target job function in title",
                matched_terms=always_excluded,
            )

        negative_matches = tuple(
            term
            for term in self.negative_title_phrases
            if contains_term(normalized_title, term)
        )
        negative_overrides = tuple(
            term
            for term in self.negative_override_terms
            if contains_term(normalized_title, term)
        )
        if negative_matches and not negative_overrides:
            return FilterResult(
                status="EXCLUDE",
                reason="non-cyber security context in title",
                matched_terms=negative_matches,
            )

        if title_matches:
            category, terms = self._most_specific_match(title_matches)
            return FilterResult(
                status="INCLUDE",
                reason="explicit cyber taxonomy match in title",
                matched_terms=terms,
                category=category,
            )

        generic_matches = tuple(
            term
            for term in self.generic_title_exclusions
            if contains_term(normalized_title, term)
        )
        if generic_matches:
            return FilterResult(
                status="EXCLUDE",
                reason="generic non-security role title",
                matched_terms=generic_matches,
            )

        non_cyber_function_matches = tuple(
            term
            for term in self.description_only_title_exclusions
            if contains_term(normalized_title, term)
        )
        if non_cyber_function_matches:
            return FilterResult(
                status="EXCLUDE",
                reason="non-cyber job function in title; description-only evidence ignored",
                matched_terms=non_cyber_function_matches,
            )

        description_matches = self._category_matches(normalized_description)
        description_eligible = any(
            contains_term(normalized_title, term)
            or contains_term(normalized_employment, term)
            for term in self.description_only_title_markers
        )
        if description_matches and description_eligible:
            category, terms = self._most_specific_match(description_matches)
            return FilterResult(
                status="INCLUDE",
                reason="explicit cyber taxonomy match in description",
                matched_terms=terms,
                category=category,
            )
        if description_matches:
            return FilterResult(
                status="EXCLUDE",
                reason="description-only cyber evidence lacks an early-career title/type marker",
                matched_terms=self._most_specific_match(description_matches)[1],
            )

        combined = f"{normalized_title} {normalized_description}".strip()
        for item in self.contextual_terms:
            if contains_term(combined, item.term) and any(
                contains_term(combined, marker) for marker in item.context_markers
            ) and description_eligible:
                return FilterResult(
                    status="INCLUDE",
                    reason="contextual cyber term with required marker",
                    matched_terms=(item.term,),
                    category=item.category,
                )

        return FilterResult(status="EXCLUDE", reason="no cyber taxonomy evidence")

    def _category_matches(self, normalized_text: str) -> list[tuple[str, tuple[str, ...]]]:
        matches: list[tuple[str, tuple[str, ...]]] = []
        for category, terms in self.categories:
            matched = tuple(term for term in terms if contains_term(normalized_text, term))
            if matched:
                matches.append((category, matched))
        return matches

    @staticmethod
    def _most_specific_match(
        matches: list[tuple[str, tuple[str, ...]]],
    ) -> tuple[str, tuple[str, ...]]:
        return max(
            matches,
            key=lambda match: max(len(normalize_text(term)) for term in match[1]),
        )

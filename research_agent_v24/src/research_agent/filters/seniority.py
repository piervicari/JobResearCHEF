"""Strict junior/internship seniority gate."""

from __future__ import annotations

import re
from pathlib import Path

from research_agent.config import PROJECT_ROOT, load_yaml
from research_agent.filters.common import FilterResult, contains_term, normalize_text


class SeniorityFilter:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or PROJECT_ROOT / "config" / "seniority.yaml"
        config = load_yaml(path)
        self.configuration = config
        self.include_terms = tuple(str(value) for value in config.get("include_terms", []))
        self.exclude_terms = tuple(str(value) for value in config.get("exclude_terms", []))
        self.max_early_career_years = int(config.get("max_early_career_years", 3))

    def evaluate(
        self,
        *,
        title: str,
        employment_type: str | None = None,
        description: str = "",
    ) -> FilterResult:
        normalized_title = normalize_text(title)
        experience = _experience_signal(description, self.max_early_career_years)
        excluded = tuple(
            term for term in self.exclude_terms if contains_term(normalized_title, term)
        )
        if excluded:
            return FilterResult(
                status="EXCLUDE",
                reason="explicit seniority exclusion in title",
                matched_terms=excluded,
            )

        included = tuple(
            term for term in self.include_terms if contains_term(normalized_title, term)
        )
        if included:
            if experience is not None and experience.status == "EXCLUDE":
                return FilterResult(
                    status="REVIEW",
                    reason="early-career title conflicts with higher experience requirement",
                    matched_terms=(*included, *experience.matched_terms),
                )
            return FilterResult(
                status="INCLUDE",
                reason="explicit junior/internship marker in title",
                matched_terms=included,
                category=_seniority_category(included),
            )

        normalized_employment = normalize_text(employment_type or "")
        employment_matches = tuple(
            term for term in self.include_terms if contains_term(normalized_employment, term)
        )
        if employment_matches:
            if experience is not None and experience.status == "EXCLUDE":
                return FilterResult(
                    status="REVIEW",
                    reason=(
                        "early-career employment type conflicts with higher experience requirement"
                    ),
                    matched_terms=(*employment_matches, *experience.matched_terms),
                )
            return FilterResult(
                status="INCLUDE",
                reason="explicit junior/internship marker in employment type",
                matched_terms=employment_matches,
                category=_seniority_category(employment_matches),
            )

        ordinal = _ordinal_signal(title)
        if ordinal is not None:
            return ordinal
        if experience is not None:
            return experience

        return FilterResult(
            status="REVIEW",
            reason="no explicit junior/internship or senior marker",
        )


def _seniority_category(terms: tuple[str, ...]) -> str:
    internship_terms = {"intern", "internship", "stage", "working student", "thesis"}
    return (
        "internship"
        if any(normalize_text(term) in internship_terms for term in terms)
        else "junior"
    )


_EXPERIENCE_RANGE = re.compile(
    r"\b(?P<minimum>\d{1,2})\s*(?:-|–|—|to)\s*(?P<maximum>\d{1,2})\s*"
    r"(?:years?|yrs?)(?:\s+of)?(?:\s+relevant)?\s+experience\b",
    re.IGNORECASE,
)
_EXPERIENCE_UP_TO = re.compile(
    r"\bup\s+to\s+(?P<maximum>\d{1,2})\s*(?:years?|yrs?)(?:\s+of)?"
    r"(?:\s+relevant)?\s+experience\b",
    re.IGNORECASE,
)
_EXPERIENCE_MINIMUM = re.compile(
    r"\b(?:minimum(?:\s+of)?|at\s+least)\s+(?P<minimum>\d{1,2})\s*"
    r"(?:years?|yrs?)(?:\s+of)?(?:\s+relevant)?\s+experience\b",
    re.IGNORECASE,
)
_EXPERIENCE_PLUS = re.compile(
    r"\b(?P<minimum>\d{1,2})\s*\+\s*(?:years?|yrs?)(?:\s+of)?"
    r"(?:\s+relevant)?\s+experience\b",
    re.IGNORECASE,
)
_EXPERIENCE_EXACT = re.compile(
    r"\b(?P<years>\d{1,2})\s*(?:years?|yrs?)(?:\s+of)?(?:\s+relevant)?"
    r"\s+experience\b",
    re.IGNORECASE,
)
_ORDINAL_ROLE = re.compile(
    r"\b(?:engineer|analyst|consultant|specialist)\s+(?P<roman>I{1,3}|IV)\b",
    re.IGNORECASE,
)
_ORDINAL_LEVEL = re.compile(r"\blevel\s+(?P<level>[1-4])\b", re.IGNORECASE)


def _experience_signal(description: str, maximum_early_years: int) -> FilterResult | None:
    if match := _EXPERIENCE_RANGE.search(description):
        minimum = int(match.group("minimum"))
        maximum = int(match.group("maximum"))
        token = match.group(0)
        if maximum <= maximum_early_years:
            return FilterResult("INCLUDE", "experience range is early-career", (token,), "junior")
        if minimum > maximum_early_years:
            return FilterResult("EXCLUDE", "experience range is above early-career scope", (token,))
        return FilterResult("REVIEW", "experience range crosses early-career threshold", (token,))
    if match := _EXPERIENCE_UP_TO.search(description):
        maximum = int(match.group("maximum"))
        token = match.group(0)
        if maximum <= maximum_early_years:
            return FilterResult("INCLUDE", "maximum experience is early-career", (token,), "junior")
        return FilterResult("REVIEW", "maximum experience crosses early-career threshold", (token,))
    if match := _EXPERIENCE_MINIMUM.search(description):
        minimum = int(match.group("minimum"))
        token = match.group(0)
        if minimum > maximum_early_years:
            return FilterResult(
                "EXCLUDE", "minimum experience is above early-career scope", (token,)
            )
        return FilterResult("REVIEW", "open-ended minimum experience is ambiguous", (token,))
    if match := _EXPERIENCE_PLUS.search(description):
        minimum = int(match.group("minimum"))
        token = match.group(0)
        if minimum > maximum_early_years:
            return FilterResult(
                "EXCLUDE", "open-ended experience is above early-career scope", (token,)
            )
        return FilterResult("REVIEW", "open-ended experience is ambiguous", (token,))
    if match := _EXPERIENCE_EXACT.search(description):
        years = int(match.group("years"))
        token = match.group(0)
        if years <= maximum_early_years:
            return FilterResult(
                "INCLUDE", "experience requirement is early-career", (token,), "junior"
            )
        return FilterResult(
            "EXCLUDE", "experience requirement is above early-career scope", (token,)
        )
    return None


def _ordinal_signal(title: str) -> FilterResult | None:
    match = _ORDINAL_ROLE.search(title)
    if match:
        level = {"I": 1, "II": 2, "III": 3, "IV": 4}[match.group("roman").upper()]
        token = match.group(0)
    else:
        level_match = _ORDINAL_LEVEL.search(title)
        if level_match is None:
            return None
        level = int(level_match.group("level"))
        token = level_match.group(0)
    if level == 1:
        return FilterResult("INCLUDE", "entry ordinal level in title", (token,), "junior")
    if level == 2:
        return FilterResult("REVIEW", "second ordinal level is employer-dependent", (token,))
    return FilterResult("EXCLUDE", "higher ordinal level is outside early-career scope", (token,))

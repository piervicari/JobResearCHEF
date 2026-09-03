"""Combined vacancy filtering with auditable component decisions."""

from __future__ import annotations

from dataclasses import dataclass

from research_agent.filters.common import FilterResult
from research_agent.filters.cyber import CyberFilter
from research_agent.filters.geography import GeographyFilter
from research_agent.filters.seniority import SeniorityFilter
from research_agent.sources.base import RawJob


@dataclass(frozen=True)
class VacancyFilterResult:
    status: str
    cyber: FilterResult
    seniority: FilterResult
    geography: FilterResult


class VacancyFilter:
    def __init__(
        self,
        cyber: CyberFilter | None = None,
        seniority: SeniorityFilter | None = None,
        geography: GeographyFilter | None = None,
    ) -> None:
        self.cyber = cyber or CyberFilter()
        self.seniority = seniority or SeniorityFilter()
        self.geography = geography or GeographyFilter()

    def config_snapshot(self) -> dict[str, object]:
        """Return the exact parsed taxonomy used for an auditable processing run."""

        return {
            "cyber": self.cyber.configuration,
            "seniority": self.seniority.configuration,
            "geography": self.geography.configuration,
        }

    def evaluate(self, job: RawJob, *, country: str | None = None) -> VacancyFilterResult:
        cyber = self.cyber.evaluate(
            title=job.title,
            description=job.description,
            employment_type=job.employment_type,
        )
        seniority = self.seniority.evaluate(
            title=job.title,
            employment_type=job.employment_type,
            description=job.description,
        )
        geography = self.geography.evaluate(
            location=job.location,
            country=country or job.country,
            workplace_type=job.workplace_type,
        )
        components = (cyber, seniority, geography)
        if any(component.status == "EXCLUDE" for component in components):
            status = "EXCLUDE"
        elif any(component.status == "REVIEW" for component in components):
            status = "REVIEW"
        else:
            status = "INCLUDE"
        return VacancyFilterResult(
            status=status,
            cyber=cyber,
            seniority=seniority,
            geography=geography,
        )

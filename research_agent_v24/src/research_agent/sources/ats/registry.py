"""Default adapter registry ordered from most specific to fallback."""

from collections.abc import Iterable

from research_agent.sources.ats.ashby import AshbyAdapter
from research_agent.sources.ats.avature import AvatureAdapter
from research_agent.sources.ats.greenhouse import GreenhouseAdapter
from research_agent.sources.ats.google_careers import GoogleCareersAdapter
from research_agent.sources.ats.lever import LeverAdapter
from research_agent.sources.ats.oracle import OracleRecruitingCloudAdapter
from research_agent.sources.ats.phenom import PhenomAdapter
from research_agent.sources.ats.radancy import RadancyAdapter
from research_agent.sources.ats.smartrecruiters import SmartRecruitersAdapter
from research_agent.sources.ats.successfactors import SuccessFactorsRmkAdapter
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.base import AdapterRegistry, SourceAdapter
from research_agent.sources.official.generic import GenericOfficialHtmlAdapter


def structured_adapter_registry(
    declarative_adapters: Iterable[SourceAdapter] = (),
) -> AdapterRegistry:
    """Legacy structured registry, optionally extended with declarative siblings.

    With no arguments the registry — and its adapter order — is exactly
    what it was before declarative sources existed. Declarative adapters
    are appended AFTER the legacy adapters: they only match explicitly
    bound portal URLs, so order is irrelevant to them, and legacy
    priority is preserved for everything else.
    """
    return AdapterRegistry(
        [
            GreenhouseAdapter(),
            GoogleCareersAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            SmartRecruitersAdapter(),
            RadancyAdapter(),
            SuccessFactorsRmkAdapter(),
            WorkdayAdapter(),
            PhenomAdapter(),
            OracleRecruitingCloudAdapter(),
            AvatureAdapter(),
            *declarative_adapters,
        ]
    )


def default_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry(
        [
            GreenhouseAdapter(),
            GoogleCareersAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            SmartRecruitersAdapter(),
            RadancyAdapter(),
            SuccessFactorsRmkAdapter(),
            WorkdayAdapter(),
            PhenomAdapter(),
            OracleRecruitingCloudAdapter(),
            AvatureAdapter(),
            GenericOfficialHtmlAdapter(),
        ]
    )

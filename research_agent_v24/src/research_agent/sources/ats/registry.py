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
from research_agent.sources.ats.teamtailor import TeamtailorAdapter
from research_agent.sources.ats.workable import WorkableAdapter
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.base import AdapterRegistry, SourceAdapter
from research_agent.sources.official.generic import GenericOfficialHtmlAdapter


def structured_adapter_registry(
    declarative_adapters: Iterable[SourceAdapter] = (),
) -> AdapterRegistry:
    """Legacy structured registry, optionally extended with declarative siblings.

    With no arguments the registry — and its adapter order — is exactly
    what it was before declarative sources existed. When declarative
    adapters are provided, they come FIRST: an explicit portal binding
    is an operator decision and must win over any legacy ATS-family
    heuristic (AdapterRegistry.select uses first-match semantics, so
    appending declarative adapters after legacy ones would let a legacy
    heuristic shadow an explicit binding). Declarative adapters only
    match exactly-bound portal URLs, so unbound portals still fall
    through to the legacy adapters in their original order.
    """
    return AdapterRegistry(
        [
            *declarative_adapters,
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
            TeamtailorAdapter(),
            WorkableAdapter(),
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
            TeamtailorAdapter(),
            WorkableAdapter(),
            GenericOfficialHtmlAdapter(),
        ]
    )

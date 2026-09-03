"""Default adapter registry ordered from most specific to fallback."""

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
from research_agent.sources.base import AdapterRegistry
from research_agent.sources.official.generic import GenericOfficialHtmlAdapter


def structured_adapter_registry() -> AdapterRegistry:
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

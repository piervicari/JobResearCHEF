from research_agent.sources.ats.greenhouse import GreenhouseAdapter
from research_agent.sources.base import PortalTarget


def test_greenhouse_declares_one_shot_bulk_catalog() -> None:
    adapter = GreenhouseAdapter()
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://job-boards.greenhouse.io/stripe",
        normalized_jobs_url="https://job-boards.greenhouse.io/stripe",
        host="job-boards.greenhouse.io",
        ats_families=("Greenhouse",),
        ats_confidences=("Verified",),
    )
    assert adapter.bulk_catalog is True
    assert adapter.supports(target) is True
    assert adapter.board_token(target) == "stripe"

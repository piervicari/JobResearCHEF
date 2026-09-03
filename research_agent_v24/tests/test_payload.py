from research_agent.pipeline.payload import serialize_observation_payload
from research_agent.sources.base import RawJob


def _job(*, location: str = "Milan, Italy", native_extra: object = None) -> RawJob:
    return RawJob(
        source="fixture",
        source_job_id="same-id",
        source_url="https://jobs.example.test/role",
        apply_url=f"https://jobs.example.test/apply?location={location}",
        title="Security Engineer",
        company="Example",
        location=location,
        country="IT",
        city=location.split(",", 1)[0],
        description="The same recycled description.",
        raw_payload={"id": "same-id", "volatile": native_extra},
    )


def test_location_is_part_of_application_owned_content_hash() -> None:
    _, milan_hash = serialize_observation_payload(
        _job(location="Milan, Italy"),
        company_id="CG-1",
        company_name="Example",
        adapter="fixture",
    )
    _, rome_hash = serialize_observation_payload(
        _job(location="Rome, Italy"),
        company_id="CG-1",
        company_name="Example",
        adapter="fixture",
    )
    assert milan_hash != rome_hash


def test_native_provider_noise_does_not_change_canonical_content_hash() -> None:
    _, first = serialize_observation_payload(
        _job(native_extra="request-1"),
        company_id="CG-1",
        company_name="Example",
        adapter="fixture",
    )
    _, second = serialize_observation_payload(
        _job(native_extra="request-2"),
        company_id="CG-1",
        company_name="Example",
        adapter="fixture",
    )
    assert first == second


def test_audit_payload_contains_required_source_truth() -> None:
    payload_json, _ = serialize_observation_payload(
        _job(),
        company_id="CG-1",
        company_name="Example Resolved",
        adapter="fixture",
    )
    for expected in (
        '"company_name_raw":"Example"',
        '"company_name_resolved":"Example Resolved"',
        '"job_title":"Security Engineer"',
        '"location":"Milan, Italy"',
        '"job_description":"The same recycled description."',
    ):
        assert expected in payload_json

from research_agent.pipeline.dedup import (
    DedupCandidate,
    DedupIndex,
    canonical_application_url,
    canonical_fingerprint,
)
from research_agent.pipeline.normalizer import html_to_text, normalize_location


def _candidate(**overrides: object) -> DedupCandidate:
    values: dict[str, object] = {
        "canonical_job_id": "CJ-1",
        "source": "greenhouse",
        "source_job_id": "101",
        "apply_url": "https://jobs.example.test/roles/101",
        "corporate_cluster_id": "CG-1",
        "title": "Junior Security Analyst",
        "location": "Milan, Italy",
        "ats_job_id": None,
        "requisition_id": "SEC-101",
    }
    values.update(overrides)
    return DedupCandidate(**values)  # type: ignore[arg-type]


def test_application_url_removes_only_known_tracking_parameters() -> None:
    first = canonical_application_url(
        "HTTPS://Jobs.Example.test:443/roles/101/?tenant=abc&utm_source=linkedin&gh_src=x#top"
    )
    second = canonical_application_url("https://jobs.example.test/roles/101?tenant=abc")
    assert first == second
    assert "tenant=abc" in first


def test_application_url_preserves_meaningful_job_query() -> None:
    first = canonical_application_url("https://example.test/apply?job=101")
    second = canonical_application_url("https://example.test/apply?job=102")
    assert first != second


def test_dedup_prefers_source_identity_when_vacancy_shape_is_compatible() -> None:
    index = DedupIndex()
    index.add(_candidate())
    match = index.match(_candidate(canonical_job_id="incoming"))
    assert match is not None
    assert match.canonical_job_id == "CJ-1"
    assert match.method == "source_job_id"


def test_source_id_conflict_does_not_merge_location_variant() -> None:
    index = DedupIndex()
    index.add(_candidate())
    match = index.match(
        _candidate(
            canonical_job_id="incoming",
            location="Rome, Italy",
            apply_url="https://jobs.example.test/roles/101-rome",
        )
    )
    assert match is None


def test_cross_source_dedup_uses_canonical_apply_url() -> None:
    index = DedupIndex()
    index.add(_candidate())
    match = index.match(
        _candidate(
            canonical_job_id="incoming",
            source="linkedin",
            source_job_id="li-999",
            apply_url="https://jobs.example.test/roles/101/?utm_source=linkedin",
        )
    )
    assert match is not None
    assert match.method == "canonical_apply_url"


def test_cross_source_dedup_uses_ats_id_when_other_dimensions_are_compatible() -> None:
    index = DedupIndex()
    index.add(_candidate(ats_job_id="ATS-1", apply_url=""))
    match = index.match(
        _candidate(
            canonical_job_id="incoming",
            source="linkedin",
            source_job_id="li-999",
            apply_url="",
            ats_job_id="ATS-1",
        )
    )
    assert match is not None
    assert match.method == "ats_job_id"


def test_same_ats_id_with_different_location_is_not_merged() -> None:
    index = DedupIndex()
    index.add(_candidate(ats_job_id="ATS-1", apply_url=""))
    match = index.match(
        _candidate(
            canonical_job_id="incoming",
            source="other",
            source_job_id="other-1",
            apply_url="",
            ats_job_id="ATS-1",
            location="Rome, Italy",
        )
    )
    assert match is None


def test_ats_id_is_not_global_across_corporate_clusters() -> None:
    index = DedupIndex()
    index.add(_candidate(ats_job_id="101"))
    match = index.match(
        _candidate(
            canonical_job_id="incoming",
            source="other",
            source_job_id="other-101",
            apply_url="https://different.test/apply",
            ats_job_id="101",
            corporate_cluster_id="CG-2",
        )
    )
    assert match is None


def test_normalized_fingerprint_is_cluster_scoped() -> None:
    first = canonical_fingerprint(
        corporate_cluster_id="CG-1",
        title="Junior Security Analyst",
        location="Italy | Remote",
        requisition_id=None,
    )
    reordered = canonical_fingerprint(
        corporate_cluster_id="CG-1",
        title="  junior  security analyst ",
        location="Remote | Italy",
        requisition_id=None,
    )
    other_cluster = canonical_fingerprint(
        corporate_cluster_id="CG-2",
        title="Junior Security Analyst",
        location="Italy | Remote",
        requisition_id=None,
    )
    assert first == reordered
    assert first != other_cluster


def test_html_and_location_normalization_are_deterministic() -> None:
    assert html_to_text("<p>Cloud &amp; application <b>security</b></p>") == (
        "Cloud & application security"
    )
    assert normalize_location("Remote | Milan, Italy | Remote") == (
        "milan italy | remote"
    )

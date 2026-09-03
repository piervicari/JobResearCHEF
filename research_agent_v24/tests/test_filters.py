import pytest

from research_agent.filters.cyber import CyberFilter
from research_agent.filters.geography import GeographyFilter
from research_agent.filters.seniority import SeniorityFilter
from research_agent.pipeline.filter import VacancyFilter
from research_agent.sources.base import RawJob


@pytest.mark.parametrize(
    ("title", "description", "category"),
    [
        ("Junior SOC Analyst", "", "security_operations"),
        ("DFIR Intern", "", "incident_response_forensics"),
        ("Graduate Application Security Engineer", "", "application_product_security"),
        ("IAM Working Student", "identity and access security", "identity_access"),
        ("GRC Trainee", "cyber governance and controls", "governance_risk_compliance"),
        ("OT Security Apprentice", "", "ot_ics_industrial"),
        ("Automotive Cybersecurity Thesis", "", "automotive_embedded_iot"),
        ("Privacy Engineering Intern", "technical privacy controls", "privacy_security"),
        ("Software Engineer, Security", "", "application_product_security"),
        ("AI Research Engineer, Security", "", "research_cryptography"),
    ],
)
def test_cyber_filter_is_broad_across_required_taxonomy(
    title: str, description: str, category: str
) -> None:
    result = CyberFilter().evaluate(title=title, description=description)
    assert result.status == "INCLUDE"
    assert result.category == category


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Software Engineer Intern", "The team also follows security best practices."),
        ("Physical Security Analyst Intern", "Protect offices and facilities."),
        ("Security Guard Apprentice", "Patrol the premises."),
        ("Junior Product Manager", "Build a general SaaS product."),
        (
            "Customer Success Manager",
            "Help customers deploy our application security platform.",
        ),
        ("Director of Sales", "Sell cloud security products."),
        ("AI Engineer", "The company builds cybersecurity products."),
        ("Writer, Threat Intelligence & Communications", "Write CTI reports."),
    ],
)
def test_cyber_filter_excludes_generic_or_physical_security(
    title: str, description: str
) -> None:
    assert CyberFilter().evaluate(title=title, description=description).status == "EXCLUDE"


def test_cyber_filter_uses_description_for_non_generic_title() -> None:
    result = CyberFilter().evaluate(
        title="Technology Graduate Programme",
        description="Rotation in threat intelligence and incident response.",
    )
    assert result.status == "INCLUDE"
    assert result.category == "threat_intelligence"


def test_description_only_match_can_use_structured_internship_type() -> None:
    result = CyberFilter().evaluate(
        title="Technology Analyst",
        description="Rotation in incident response and threat hunting.",
        employment_type="Internship",
    )
    assert result.status == "INCLUDE"


@pytest.mark.parametrize(
    "title",
    [
        "Business Analyst",
        "Payroll Analyst",
        "Site Reliability Engineer",
        "Product Support Specialist",
    ],
)
def test_vendor_boilerplate_does_not_make_non_early_role_cyber(title: str) -> None:
    result = CyberFilter().evaluate(
        title=title,
        description="Our application security platform supports threat intelligence teams.",
    )
    assert result.status == "EXCLUDE"


def test_general_internship_application_is_not_assumed_cyber() -> None:
    result = CyberFilter().evaluate(
        title="Submitting for a General Internship Application",
        description="We build secure software and manage cybersecurity risk.",
    )
    assert result.status == "EXCLUDE"


@pytest.mark.parametrize(
    "title",
    [
        "Cybersecurity Intern",
        "Junior Security Analyst",
        "Information Security Graduate",
        "AppSec Working Student",
        "Security Apprentice",
        "Cybersecurity Stage",
    ],
)
def test_seniority_filter_includes_explicit_early_career_terms(title: str) -> None:
    assert SeniorityFilter().evaluate(title=title).status == "INCLUDE"


@pytest.mark.parametrize(
    "title",
    [
        "Senior Security Analyst",
        "Security Engineering Manager",
        "Principal AppSec Engineer",
        "VP Information Security",
        "Head of Cybersecurity",
    ],
)
def test_seniority_filter_excludes_senior_roles(title: str) -> None:
    assert SeniorityFilter().evaluate(title=title).status == "EXCLUDE"


def test_seniority_filter_uses_structured_employment_type() -> None:
    result = SeniorityFilter().evaluate(
        title="Security Analyst", employment_type="Internship"
    )
    assert result.status == "INCLUDE"
    assert result.category == "internship"


def test_seniority_without_evidence_requires_review() -> None:
    assert SeniorityFilter().evaluate(title="Security Analyst").status == "REVIEW"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Requires 0-2 years of experience.", "INCLUDE"),
        ("You have 1 to 3 years relevant experience.", "INCLUDE"),
        ("Requires 2-4 years of experience.", "REVIEW"),
        ("Requires 3+ years of experience.", "REVIEW"),
        ("Minimum of 5 years of experience.", "EXCLUDE"),
    ],
)
def test_seniority_parses_bounded_experience(description: str, expected: str) -> None:
    result = SeniorityFilter().evaluate(title="Security Analyst", description=description)
    assert result.status == expected


def test_seniority_keeps_conflicting_junior_and_high_experience_for_review() -> None:
    result = SeniorityFilter().evaluate(
        title="Junior Security Analyst",
        description="Minimum of 5 years of experience.",
    )
    assert result.status == "REVIEW"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Security Engineer I", "INCLUDE"),
        ("Security Engineer II", "REVIEW"),
        ("Security Engineer III", "EXCLUDE"),
        ("Security Analyst Level 1", "INCLUDE"),
        ("Security Analyst Level 2", "REVIEW"),
    ],
)
def test_seniority_parses_ordinal_levels(title: str, expected: str) -> None:
    assert SeniorityFilter().evaluate(title=title).status == expected


@pytest.mark.parametrize(
    "location",
    ["Milan, Italy", "London, UK", "Remote - United States", "Sydney, Australia"],
)
def test_geography_includes_target_vacancy_locations(location: str) -> None:
    assert GeographyFilter().evaluate(location=location).status == "INCLUDE"


@pytest.mark.parametrize(
    "location",
    ["Dubai, United Arab Emirates", "Riyadh, Saudi Arabia", "Auckland, New Zealand"],
)
def test_geography_excludes_out_of_scope_locations(location: str) -> None:
    assert GeographyFilter().evaluate(location=location).status == "EXCLUDE"


def test_geography_handles_structured_country_codes() -> None:
    geography = GeographyFilter()
    assert geography.evaluate(location="Milan", country="IT").status == "INCLUDE"
    assert geography.evaluate(location="Dubai", country="AE").status == "EXCLUDE"


def test_unknown_structured_country_requires_review() -> None:
    result = GeographyFilter().evaluate(location="New Arcadia", country="Republic of Arcadia")
    assert result.status == "REVIEW"
    assert "unknown" in result.reason


@pytest.mark.parametrize("location", ["Remote", "EMEA", "Europe"])
def test_ambiguous_geography_requires_review(location: str) -> None:
    assert GeographyFilter().evaluate(location=location).status == "REVIEW"


def test_explicit_eu_scope_is_included() -> None:
    assert GeographyFilter().evaluate(location="Remote - European Union").status == "INCLUDE"


def test_combined_filter_requires_all_three_gates() -> None:
    accepted = RawJob(
        source="fixture",
        source_job_id="1",
        source_url="https://example.test/1",
        apply_url="https://example.test/1/apply",
        title="Junior Cloud Security Analyst",
        location="Rome, Italy",
    )
    senior = RawJob(
        source="fixture",
        source_job_id="2",
        source_url="https://example.test/2",
        apply_url="https://example.test/2/apply",
        title="Senior Cloud Security Analyst",
        location="Rome, Italy",
    )
    assert VacancyFilter().evaluate(accepted).status == "INCLUDE"
    assert VacancyFilter().evaluate(senior).status == "EXCLUDE"

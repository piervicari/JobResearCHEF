import pytest

from research_agent.company.portal_registry import PortalRegistryError, normalize_jobs_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Example.COM:443/jobs/", "https://example.com/jobs"),
        ("http://Example.com:80//jobs///search/", "http://example.com/jobs/search"),
        (
            "https://example.com/jobs?q=hashicorp#results",
            "https://example.com/jobs?q=hashicorp",
        ),
        ("https://example.com/", "https://example.com/"),
    ],
)
def test_normalize_jobs_url_is_conservative(raw: str, expected: str) -> None:
    assert normalize_jobs_url(raw) == expected


def test_normalize_jobs_url_preserves_query_order_and_values() -> None:
    raw = "https://EXAMPLE.com/jobs?tenant=abc&locale=en-US"
    assert normalize_jobs_url(raw) == "https://example.com/jobs?tenant=abc&locale=en-US"


@pytest.mark.parametrize(
    "raw", ["", "example.com/jobs", "ftp://example.com/jobs", "https://user@example.com/jobs"]
)
def test_normalize_jobs_url_rejects_unsafe_or_non_http_values(raw: str) -> None:
    with pytest.raises(PortalRegistryError):
        normalize_jobs_url(raw)

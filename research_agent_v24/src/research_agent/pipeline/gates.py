"""Post-fetch gate that prevents suspect cohorts from advancing vacancy lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass

from research_agent.pipeline.scanner import ScanSummary


@dataclass(frozen=True)
class ScanGatePolicy:
    max_failure_rate: float = 0.10
    max_retry_rate: float = 0.20
    max_http_429: int = 0
    max_unexpected_empty_complete: int = 0


@dataclass(frozen=True)
class ScanGateResult:
    passed: bool
    failure_rate: float
    retry_rate: float
    http_429_count: int
    unexpected_empty_complete: int
    reasons: tuple[str, ...]


def assess_scan_gate(scan: ScanSummary, policy: ScanGatePolicy) -> ScanGateResult:
    failure_rate = scan.failure_count / scan.portal_count if scan.portal_count else 1.0
    retry_rate = scan.retry_count / scan.request_count if scan.request_count else 0.0
    http_429_count = sum(
        attempt.status_code == 429
        for result in scan.portal_results
        for attempt in result.fetch_attempts
    )
    unexpected_empty_complete = sum(
        result.status == "SUCCESS"
        and result.complete_snapshot
        and not result.jobs
        and "upstream reports zero active jobs" not in result.warnings
        for result in scan.portal_results
    )
    reasons: list[str] = []
    if failure_rate > policy.max_failure_rate:
        reasons.append(
            f"failure rate {failure_rate:.1%} exceeds {policy.max_failure_rate:.1%}"
        )
    if retry_rate > policy.max_retry_rate:
        reasons.append(f"retry rate {retry_rate:.1%} exceeds {policy.max_retry_rate:.1%}")
    if http_429_count > policy.max_http_429:
        reasons.append(f"HTTP 429 count {http_429_count} exceeds {policy.max_http_429}")
    if unexpected_empty_complete > policy.max_unexpected_empty_complete:
        reasons.append(
            "unexpected complete empty snapshots "
            f"{unexpected_empty_complete} exceed {policy.max_unexpected_empty_complete}"
        )
    return ScanGateResult(
        passed=not reasons,
        failure_rate=failure_rate,
        retry_rate=retry_rate,
        http_429_count=http_429_count,
        unexpected_empty_complete=unexpected_empty_complete,
        reasons=tuple(reasons),
    )

#!/usr/bin/env python3
"""Wave 1 controlled live probes (sequential, minimal, stop on 403/429/challenge).

Uses the JobResearCHEF HttpFetcher (budgets, circuit breaker, pacing).
One catalog request per ATS first; extras only with inline justification.
Saves raw bodies under external_reuse_audit/wave1_probes/ for offline parsing.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/pierfrancescovicari/hermes-job-benchmark/JobResearCHEF/research_agent_v24/src")

from research_agent.pipeline.http import FetchRequest, HttpFetcher  # noqa: E402

OUT = Path("/Users/pierfrancescovicari/hermes-job-benchmark/external_reuse_audit/wave1_probes")
OUT.mkdir(exist_ok=True)

PROBES = [
    ("bamboohr_embed", "https://hp.bamboohr.com/jobs/embed2.php", {}),
    ("teamtailor_rss", "https://canva.teamtailor.com/jobs.rss",
     {"Accept": "application/rss+xml, text/xml"}),
    ("workable_widget", "https://apply.workable.com/api/v1/widget/accounts/apple",
     {"Accept": "application/json"}),
]

CHALLENGE_MARKERS = (b"just a moment", b"cf-chl-", b"verify you are human", b"px-captcha")


async def main() -> None:
    log = []
    fetcher = HttpFetcher(
        per_domain_min_interval_seconds=2.0,
        max_retries=0,
        max_requests_per_run=10,
        max_requests_per_host_per_run=4,
    )
    async with fetcher:
        for name, url, headers in PROBES:
            try:
                response = await fetcher.fetch(FetchRequest(url, headers=headers or None))
            except Exception as exc:  # noqa: BLE001 - stop rules need the class name
                print(f"{name}: STOP {type(exc).__name__}: {exc}")
                log.append({"name": name, "url": url, "error": type(exc).__name__})
                if type(exc).__name__ in ("HostCircuitOpenError", "AccessChallengeError"):
                    break
                continue
            body = response.content
            flagged = [m.decode() for m in CHALLENGE_MARKERS if m in body[:200000].lower()]
            print(f"{name}: HTTP {response.status_code} bytes={len(body)} "
                  f"attempts={len(response.attempts)} challenge={flagged or None}")
            (OUT / f"{name}.status.json").write_text(json.dumps({
                "url": url, "status": response.status_code,
                "final_url": response.final_url, "bytes": len(body),
                "attempts": len(response.attempts), "challenge": flagged,
            }, indent=1))
            (OUT / f"{name}.body.bin").write_bytes(body[:500000])
            log.append({"name": name, "url": url, "status": response.status_code,
                        "bytes": len(body)})
            if response.status_code in (403, 429) or flagged:
                print("STOP rule hit, ending round 1")
                break
            await asyncio.sleep(3)
    print("wire attempts total:", fetcher.request_count)


if __name__ == "__main__":
    asyncio.run(main())

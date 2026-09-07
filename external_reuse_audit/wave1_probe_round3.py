#!/usr/bin/env python3
"""Wave 1.1 micro-probes (sequential, max ~5 wire, stop on 403/429/challenge).

1. Teamtailor polestar jobs.json (verified tenant) -> compare vs saved RSS.
2. Workable starling-bank widget ?details=true -> compare vs saved widget.
3. BambooHR armis embed2.php -> seek non-empty board.
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
    ("teamtailor_json", "https://polestar.teamtailor.com/jobs.json",
     {"Accept": "application/json"}),
    ("workable_details", "https://apply.workable.com/api/v1/widget/accounts/starling-bank?details=true",
     {"Accept": "application/json"}),
    ("bamboohr_embed_armis", "https://armis.bamboohr.com/jobs/embed2.php", {}),
]

CHALLENGE_MARKERS = (b"just a moment", b"cf-chl-", b"verify you are human", b"px-captcha")


async def main() -> None:
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
            except Exception as exc:  # noqa: BLE001
                print(f"{name}: STOP {type(exc).__name__}: {exc}", flush=True)
                if type(exc).__name__ in ("HostCircuitOpenError", "AccessChallengeError"):
                    break
                continue
            body = response.content
            flagged = [m.decode() for m in CHALLENGE_MARKERS if m in body[:200000].lower()]
            print(f"{name}: HTTP {response.status_code} bytes={len(body)} "
                  f"attempts={len(response.attempts)} challenge={flagged or None}", flush=True)
            (OUT / f"{name}.status.json").write_text(json.dumps({
                "url": url, "status": response.status_code,
                "final_url": response.final_url, "bytes": len(body),
                "attempts": len(response.attempts), "challenge": flagged,
            }, indent=1))
            (OUT / f"{name}.body.bin").write_bytes(body[:500000])
            if response.status_code in (403, 429) or flagged:
                print("STOP rule hit", flush=True)
                break
            await asyncio.sleep(3)
    print("wire attempts total:", fetcher.request_count, flush=True)


if __name__ == "__main__":
    asyncio.run(main())

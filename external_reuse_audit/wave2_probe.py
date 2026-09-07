#!/usr/bin/env python3
"""Wave 2 micro-probes (sequential, max 4 wire, stop on 403/429/challenge).

1. successfactors_sitemal: careers.kpmg.it/sitemal.xml (HIGH x2, JRC KPMG
   SF canary precedent) -> does the RSS feed exist? (decides RSS vs HTML)
2. oracle_limit200: Honeywell Oracle REST with limit=200 (HIGH x2, exact
   URL+site) -> does limit=200 hold? (decides 25 vs 200 page size)
3. lever_skiplimit: sophos postings ?mode=json&skip=0&limit=1 (HIGH x2) ->
   are skip/limit honored? (decides JRC pagination validity)
4. ashby_comp: snyk board ?includeCompensation=true (HIGH) -> compensation
   present without 404? (decides expansion-flag adoption)
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/pierfrancescovicari/hermes-job-benchmark/JobResearCHEF/research_agent_v24/src")

from research_agent.pipeline.http import FetchRequest, HttpFetcher  # noqa: E402

OUT = Path("/Users/pierfrancescovicari/hermes-job-benchmark/JobResearCHEF/external_reuse_audit/wave2_probes")
OUT.mkdir(exist_ok=True)

PROBES = [
    ("successfactors_sitemal", "https://careers.kpmg.it/sitemal.xml",
     {"Accept": "application/rss+xml, application/xml, text/xml"}),
    ("oracle_limit200",
     "https://ibqbjb.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
     "?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber=CX_1,limit=200,offset=0",
     {"Accept": "application/json"}),
    ("lever_skiplimit", "https://api.lever.co/v0/postings/sophos?mode=json&skip=0&limit=1",
     {"Accept": "application/json"}),
    ("ashby_comp", "https://api.ashbyhq.com/posting-api/job-board/snyk?includeCompensation=true",
     {"Accept": "application/json"}),
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

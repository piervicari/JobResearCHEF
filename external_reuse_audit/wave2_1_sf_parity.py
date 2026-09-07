#!/usr/bin/env python3
"""Wave 2.1 SuccessFactors parity: saved-truncated RSS was insufficient for
totals (500KB of 4.2MB), so ONE full RSS re-fetch (unavoidable) + ONE bounded
RMK walk of the same KPMG tenant with the production adapter. Ceiling: 12 new
wire attempts TOTAL (1 RSS + <=11 RMK). Sequential, retries 0, stop 403/429.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

# Portable paths: repo root is the parent of external_reuse_audit/
# (script -> wave2_1_sf_parity.py -> external_reuse_audit -> JobResearCHEF).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "research_agent_v24" / "src"))

from research_agent.pipeline.http import FetchRequest, HttpFetcher  # noqa: E402
from research_agent.sources.ats.successfactors import SuccessFactorsRmkAdapter  # noqa: E402
from research_agent.sources.base import PortalScanContext, PortalTarget  # noqa: E402

OUT = Path(__file__).resolve().parent / "wave2_probes"
RSS_URL = "https://careers.kpmg.it/sitemal.xml"
RMK_PORTAL = "https://careers.kpmg.it/"


def norm_url(u: str) -> str:
    p = urlsplit(u.strip())
    path = re.sub(r"/{2,}", "/", p.path.rstrip("/")).lower()
    return f"{p.hostname or ''}{path}"


def trailing_id(u: str) -> str:
    m = re.search(r"/(\d+)/?$", urlsplit(u).path)
    return m.group(1) if m else ""


async def main() -> None:
    wire = 0
    # Phase 1: full RSS (1 wire).
    f1 = HttpFetcher(per_domain_min_interval_seconds=2.0, max_retries=0,
                     max_requests_per_run=2, max_requests_per_host_per_run=2)
    async with f1:
        rss = await f1.fetch(FetchRequest(
            RSS_URL, headers={"Accept": "application/rss+xml, application/xml, text/xml"}))
    wire += f1.request_count
    assert rss.status_code == 200, rss.status_code
    (OUT / "sf_parity_rss_full.body.bin").write_bytes(rss.content)
    root = ET.fromstring(rss.content)
    rss_items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "").strip()
        gid = ""
        for c in it:
            if c.tag.endswith("}id") and (c.text or "").strip().isdigit():
                gid = c.text.strip()
        if link:
            rss_items.append({"url": link, "nurl": norm_url(link),
                              "id": gid or trailing_id(link), "title": title})
    print(f"RSS: {len(rss_items)} items ({len(rss.content)} bytes)", flush=True)

    # Phase 2: RMK walk with the PRODUCTION adapter (<=11 wire).
    f2 = HttpFetcher(per_domain_min_interval_seconds=2.0, max_retries=0,
                     max_requests_per_run=11, max_requests_per_host_per_run=11)
    async with f2:
        ctx = PortalScanContext(fetcher=f2, max_pages_per_portal=30,
                                max_jobs_per_portal=2000)
        target = PortalTarget(portal_id=0, jobs_search_url=RMK_PORTAL,
                              normalized_jobs_url=RMK_PORTAL,
                              host="careers.kpmg.it",
                              ats_families=("SuccessFactors Recruiting Marketing",),
                              ats_confidences=("Verified",))
        result = await SuccessFactorsRmkAdapter().scan(target, ctx)
    wire += f2.request_count
    rmk = [{"url": j.apply_url, "nurl": norm_url(j.apply_url),
            "id": trailing_id(j.apply_url) or j.source_job_id,
            "title": j.title} for j in result.jobs]
    print(f"RMK: {len(rmk)} jobs complete={result.is_complete_snapshot} warnings={result.warnings}", flush=True)

    rss_urls = {x["nurl"] for x in rss_items}
    rmk_urls = {x["nurl"] for x in rmk}
    rss_ids = {x["id"] for x in rss_items if x["id"]}
    rmk_ids = {x["id"] for x in rmk if x["id"]}
    inter_url = rss_urls & rmk_urls
    inter_id = rss_ids & rmk_ids
    union_url = rss_urls | rmk_urls
    union_id = rss_ids | rmk_ids
    report = {
        "rss_items": len(rss_items), "rmk_jobs": len(rmk),
        "rmk_complete": result.is_complete_snapshot, "rmk_warnings": list(result.warnings),
        "url_intersection": len(inter_url), "url_union": len(union_url),
        "url_parity_pct": round(100 * len(inter_url) / max(len(union_url), 1), 1),
        "id_intersection": len(inter_id), "id_union": len(union_id),
        "id_parity_pct": round(100 * len(inter_id) / max(len(union_id), 1), 1),
        "rss_only_urls": sorted(rss_urls - rmk_urls)[:10],
        "rmk_only_urls": sorted(rmk_urls - rss_urls)[:10],
        "new_wire_requests": wire,
    }
    (OUT / "sf_parity_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1)[:1500], flush=True)
    print("new wire total:", wire, flush=True)


if __name__ == "__main__":
    asyncio.run(main())

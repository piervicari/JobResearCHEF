"""Workday selective detail validation (Phase 8).

Step 1 (0 wires): select_detail_candidates dry check — verifies the EXISTING
renderer produces the correct CXS detail URL from the stored catalog row.
Step 2 (<=3 wires): real enrich_official_html_details, limit=1 per portal,
sequential with pacing. Bodies persist in the validation detail cache dir.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.detail_enrichment import (  # noqa: E402
    enrich_official_html_details,
    select_detail_candidates,
)

OUT = Path("output/workday_wave_20260908").resolve()
DB_PATH = OUT / "validation.db"
DETAIL_CACHE = OUT / "detail_cache"
TENANTS = [511, 265, 5]


def main() -> None:
    engine = create_db_engine(f"sqlite:///{DB_PATH}")
    print("== dry render check (0 wires) ==")
    for pid in TENANTS:
        cands = select_detail_candidates(engine, limit=1, portal_ids={pid})
        assert len(cands) == 1, f"portal {pid}: expected 1 candidate, got {len(cands)}"
        c = cands[0]
        print(f"portal {pid}: job_id={c.job_id} adapter={c.adapter} structured={c.structured}")
        print(f"  request_url={c.request_url}")
        assert "/wday/cxs/" in c.request_url, "renderer did not produce a CXS detail URL"
    print("== live detail (<=3 wires) ==")
    prod_settings = get_settings()
    settings = prod_settings.scanner.model_copy(
        update={
            "global_concurrency": 1,
            "per_domain_concurrency": 1,
            "per_domain_min_interval_seconds": 5.0,
            "max_retries": 0,
            "jitter_seconds": 0.0,
            "max_requests_per_host_per_run": 2,
            "max_requests_per_run": 2,
        }
    )
    for i, pid in enumerate(TENANTS):
        if i:
            print("pacing 10s between detail requests...")
            time.sleep(10)
        before = set(DETAIL_CACHE.glob("*.json.gz")) if DETAIL_CACHE.exists() else set()

        def progress(event: dict) -> None:
            print("  progress:", {k: event.get(k) for k in ("event", "status", "description_chars", "parser")})

        summary = asyncio.run(
            enrich_official_html_details(
                engine,
                settings,
                limit=1,
                min_description_chars=500,
                max_jobs_per_host=1,
                inter_job_wait_seconds=5.0,
                cache_directory=DETAIL_CACHE,
                progress_callback=progress,
                portal_ids={pid},
            )
        )
        print(f"portal {pid} detail summary:", summary)
        after = set(DETAIL_CACHE.glob("*.json.gz")) if DETAIL_CACHE.exists() else set()
        print(f"  new cache bodies: {sorted(p.name for p in after - before)}")


if __name__ == "__main__":
    main()

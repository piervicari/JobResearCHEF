"""Phase 6 NVIDIA structured detail (1 wire budget left: 7 used of 8)."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from sqlalchemy.orm import Session  # noqa: E402

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.models import SourceJob  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.detail_enrichment import (  # noqa: E402
    enrich_official_html_details,
    select_detail_candidates,
)

OUT = Path("output/eightfold_nvidia_20260908").resolve()
DB_PATH = OUT / "validation.db"
DETAIL_CACHE = OUT / "detail_cache"


def main() -> None:
    engine = create_db_engine(f"sqlite:///{DB_PATH}")
    with Session(engine) as s, s.begin():
        row = s.query(SourceJob).order_by(SourceJob.id).first()
        print("candidate:", row.id, row.native_source_job_id, repr((row.raw_title or '')[:60]),
              "desc_len:", len(row.raw_description or ''))
        row.ai_status = "NEEDS_MORE_DETAIL"
    cands = select_detail_candidates(engine, limit=1)
    assert len(cands) == 1, cands
    c = cands[0]
    print("rendered:", c.adapter, c.structured, c.request_url)
    assert "/api/pcsx/position_details" in c.request_url
    assert "jobs.nvidia.com" in c.request_url
    settings = get_settings().scanner.model_copy(update={
        "global_concurrency": 1, "per_domain_concurrency": 1,
        "per_domain_min_interval_seconds": 2.0,
        "max_retries": 0, "jitter_seconds": 0.0,
        "max_requests_per_host_per_run": 1, "max_requests_per_run": 1,
    })

    def progress(event: dict) -> None:
        print("  progress:", {k: event.get(k) for k in ("event", "status", "description_chars", "parser")})

    summary = asyncio.run(enrich_official_html_details(
        engine, settings, limit=1, min_description_chars=500,
        max_jobs_per_host=1, inter_job_wait_seconds=2.0,
        cache_directory=DETAIL_CACHE, progress_callback=progress))
    print("detail summary:", summary)
    print("cache bodies:", [p.name for p in DETAIL_CACHE.glob("*.json.gz")])


if __name__ == "__main__":
    main()

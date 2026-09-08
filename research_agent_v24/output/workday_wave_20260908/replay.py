"""Replay saved Workday live bodies through the real scan path (0 wires).

Real: scanner -> registry select -> WorkdayAdapter -> HttpFetcher ->
gate -> persist_scan_discoveries -> disposable DB.
Only the transport is substituted with saved live bytes (MockTransport).
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, "src")

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.discovery import persist_scan_discoveries  # noqa: E402
from research_agent.pipeline.gates import ScanGatePolicy, assess_scan_gate  # noqa: E402
from research_agent.pipeline.scanner import scan_portals  # noqa: E402
from research_agent.sources.ats.registry import default_adapter_registry  # noqa: E402

OUT = Path("output/workday_wave_20260908").resolve()
BODIES = OUT / "bodies"
CACHE = OUT / "cache"
DB_PATH = OUT / "validation.db"
TENANTS = [511, 265, 5]


def load_wires() -> list[dict]:
    wires = []
    for path in sorted(BODIES.glob("wire_*.json")):
        wires.append(json.loads(path.read_text()))
    return wires


def raw_body(wire: dict) -> bytes:
    if "response_body" in wire:
        return wire["response_body"].encode("utf-8")
    return base64.b64decode(wire["response_body_base64"])


def make_handler(wires: list[dict]):
    posts: dict[tuple[str, int], dict] = {}
    for wire in wires:
        if wire["method"] == "POST":
            offset = json.loads(wire["request_body"]).get("offset")
            posts[(wire["url"], offset)] = wire

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            offset = json.loads(request.content.decode()).get("offset")
            wire = posts[(str(request.url), offset)]
        else:
            cands = [w for w in wires if w["method"] == "GET" and w["url"] == str(request.url)]
            assert len(cands) == 1, f"no unique GET wire for {request.url}"
            wire = cands[0]
        return httpx.Response(200, content=raw_body(wire), request=request)

    return handler


async def replay_one(engine, settings, portal_id: int, wires: list[dict]):
    transport = httpx.MockTransport(make_handler(wires))
    summary = await scan_portals(
        engine,
        default_adapter_registry(),
        settings,
        portal_ids={portal_id},
        cache_directory=CACHE,
        transport=transport,
        run_source="workday_validation_replay_20260908",
    )
    result = summary.portal_results[0]
    print(f"portal {portal_id}: status={result.status} adapter={result.adapter} "
          f"jobs={len(result.jobs)} complete={result.complete_snapshot} warnings={result.warnings}")
    assert result.status == "SUCCESS" and result.adapter == "workday", result
    gate = assess_scan_gate(
        summary,
        ScanGatePolicy(max_failure_rate=0.0, max_retry_rate=0.0, max_http_429=0,
                       max_unexpected_empty_complete=0),
    )
    print(f"  gate passed={gate.passed}")
    assert gate.passed
    persisted = persist_scan_discoveries(engine, summary)
    print(f"  persisted new={persisted.new_source_jobs} updated={persisted.updated_source_jobs} "
          f"pending_ai={persisted.pending_ai}")
    return persisted


def main() -> None:
    wires = load_wires()
    print(f"loaded {len(wires)} saved wires (0 live wires this run)")
    prod_settings = get_settings()
    settings = prod_settings.scanner.model_copy(
        update={
            "global_concurrency": 1,
            "per_domain_concurrency": 1,
            "max_retries": 0,
            "max_requests_per_host_per_run": 7,
            "max_requests_per_run": 7,
            "max_pages_per_portal": 5,
            "max_jobs_per_portal": 500,
            "bulk_catalog_max_jobs_per_portal": 5000,
            "host_cooldown_hours": 0.0,
            "run_timeout_seconds": 300.0,
        }
    )
    engine = create_db_engine(f"sqlite:///{DB_PATH}")
    for pid in TENANTS:
        asyncio.run(replay_one(engine, settings, pid, wires))
    print("REPLAY_DONE_NO_WIRES")


if __name__ == "__main__":
    main()

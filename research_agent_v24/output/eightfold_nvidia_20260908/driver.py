"""Eightfold NVIDIA bounded canary driver (2026-09-08).

Real path: scan_portals -> structured_adapter_registry([load_declarative_adapter()])
(versioned bindings.json + specs/nvidia.json) -> HttpFetcher -> gate ->
persist_scan_discoveries -> disposable DB.
RecordingTransport is a passthrough to the real network saving every wire body.
Registry gap note: production registry holds no portal matching the NVIDIA
binding (443 routes to generic HTML); the bound portal row is seeded in the
DISPOSABLE db only, mirroring the operator import flow. Production untouched.
"""
import asyncio
import base64
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, "src")

from sqlalchemy.orm import Session  # noqa: E402

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.migrations import create_schema  # noqa: E402
from research_agent.db.models import ImportBatch, Portal  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.discovery import persist_scan_discoveries  # noqa: E402
from research_agent.pipeline.gates import ScanGatePolicy, assess_scan_gate  # noqa: E402
from research_agent.pipeline.scanner import scan_portals  # noqa: E402
from research_agent.sources.ats.registry import structured_adapter_registry  # noqa: E402
from research_agent.sources.declarative import load_declarative_adapter  # noqa: E402
from research_agent.pipeline.pilot import prepare_pilot_database  # noqa: E402

ROOT = Path(".").resolve()
OUT = ROOT / "output" / "eightfold_nvidia_20260908"
BODIES = OUT / "bodies"
CACHE = OUT / "cache"
DB_PATH = OUT / "validation.db"

NVIDIA_URL = "https://jobs.nvidia.com/careers"


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, body_dir: Path) -> None:
        self._real = httpx.AsyncHTTPTransport()
        self._dir = body_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self.wires: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._real.handle_async_request(request)
        body = await response.aread()
        idx = len(self.wires)
        try:
            text = body.decode("utf-8", errors="replace")
            json.loads(text)
            payload: dict = {
                "index": idx, "method": request.method, "url": str(request.url),
                "request_body": request.content.decode("utf-8", errors="replace"),
                "status": response.status_code, "response_body": text,
            }
        except (ValueError, UnicodeDecodeError):
            payload = {
                "index": idx, "method": request.method, "url": str(request.url),
                "request_body": "",
                "status": response.status_code,
                "response_body_base64": base64.b64encode(body).decode("ascii"),
            }
        (self._dir / f"wire_{idx:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.wires.append({"index": idx, "method": request.method,
                           "url": str(request.url), "status": response.status_code,
                           "bytes": len(body)})
        return httpx.Response(
            response.status_code,
            headers=[(k, v) for k, v in response.headers.multi_items()
                     if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")],
            content=body, request=request)

    async def aclose(self) -> None:
        await self._real.aclose()


def seed_bound_portal(engine) -> int:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(source_kind="eightfold_nvidia_canary",
                            source_filename="bindings.json",
                            source_path="src/research_agent/sources/declarative/bindings.json",
                            source_sha256="n/a-disposable-canary", source_version="v0.1",
                            status="COMPLETED")
        session.add(batch)
        session.flush()
        portal = Portal(normalized_jobs_url=NVIDIA_URL, jobs_search_url=NVIDIA_URL,
                        scheme="https", host="jobs.nvidia.com",
                        ats_families_json=json.dumps(["Eightfold"]),
                        ats_confidences_json='["Verified"]',
                        metadata_conflict=False, cluster_count=1,
                        active_in_registry=True, import_batch_id=batch.id)
        session.add(portal)
        session.flush()
        return portal.id


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        shutil.rmtree(CACHE)
    CACHE.mkdir(parents=True, exist_ok=True)
    if BODIES.exists():
        shutil.rmtree(BODIES)
    BODIES.mkdir(parents=True, exist_ok=True)

    prod_settings = get_settings()
    print("prod_db_url:", prod_settings.database_url, flush=True)
    print("prod defaults untouched: jobs", prod_settings.scanner.max_jobs_per_portal,
          "pages", prod_settings.scanner.max_pages_per_portal, flush=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    prepare_pilot_database(create_db_engine(prod_settings.database_url), DB_PATH, replace=True)
    engine = create_db_engine(f"sqlite:///{DB_PATH}")
    pid = seed_bound_portal(engine)
    print("seeded bound portal id:", pid, NVIDIA_URL, flush=True)

    settings = prod_settings.scanner.model_copy(update={
        "global_concurrency": 1, "per_domain_concurrency": 1,
        "per_domain_min_interval_seconds": 2.0,
        "max_retries": 0, "jitter_seconds": 0.0,
        "max_requests_per_host_per_run": 7, "max_requests_per_run": 7,
        "max_pages_per_portal": 7, "max_jobs_per_portal": 5000,
        "bulk_catalog_max_jobs_per_portal": 5000,
        "host_cooldown_hours": 72.0, "run_timeout_seconds": 300.0,
    })
    registry = structured_adapter_registry(declarative_adapters=[load_declarative_adapter()])
    recorder = RecordingTransport(BODIES)
    manifest: dict = {"portal_id": pid, "wires": [], "stop": None}

    summary = asyncio.run(scan_portals(
        engine, registry, settings, portal_ids={pid},
        cache_directory=CACHE, transport=recorder,
        run_source="eightfold_nvidia_canary_20260908"))
    result = summary.portal_results[0]
    manifest["status"] = result.status
    manifest["adapter"] = result.adapter
    manifest["final_http_status"] = result.final_http_status
    manifest["complete_snapshot"] = result.complete_snapshot
    manifest["warnings"] = list(result.warnings)
    manifest["adapter_jobs"] = len(result.jobs)
    manifest["retry_count"] = result.retry_count
    manifest["cache_hit"] = result.cache_hit
    manifest["error_type"] = result.error_type
    manifest["error_message"] = result.error_message
    manifest["wires"] = list(recorder.wires)
    print(json.dumps({k: v for k, v in manifest.items() if k != "wires"}), flush=True)
    for w in recorder.wires:
        print("  wire:", w, flush=True)

    bad = [w for w in recorder.wires if w["status"] in (401, 403, 429)]
    if bad or result.error_type in ("AccessChallengeError", "RobotsDisallowed") \
            or result.final_http_status in (401, 403, 429):
        manifest["stop"] = "safety signal"
        print("STOP signal; no persist", flush=True)
    elif result.status == "SUCCESS":
        gate = assess_scan_gate(summary, ScanGatePolicy(
            max_failure_rate=0.0, max_retry_rate=0.0, max_http_429=0,
            max_unexpected_empty_complete=0))
        print("gate passed:", gate.passed, flush=True)
        if gate.passed:
            p = persist_scan_discoveries(engine, summary)
            manifest["persistence"] = {"new": p.new_source_jobs,
                                       "updated": p.updated_source_jobs,
                                       "pending_ai": p.pending_ai}
            print("persist:", manifest["persistence"], flush=True)
        else:
            manifest["stop"] = "gate failed"
    else:
        manifest["stop"] = f"non-success: {result.error_type}"
    manifest["total_wires"] = len(recorder.wires)
    (OUT / "catalog_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("TOTAL_WIRES:", len(recorder.wires), flush=True)


if __name__ == "__main__":
    main()

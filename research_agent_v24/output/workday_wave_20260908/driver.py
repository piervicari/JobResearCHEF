"""Workday multi-tenant validation wave driver (2026-09-08).

Real path only: scanner -> WorkdayAdapter -> HttpFetcher -> persistence ->
disposable DB. RecordingTransport is a passthrough to the real network that
saves every wire body to disk for offline reparse (0 extra wires).
Validation-only settings; production defaults untouched.
"""
import asyncio
import base64
import gzip
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, "src")

from sqlalchemy import create_engine  # noqa: E402

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.pilot import prepare_pilot_database  # noqa: E402
from research_agent.pipeline.discovery import persist_scan_discoveries  # noqa: E402
from research_agent.pipeline.gates import ScanGatePolicy, assess_scan_gate  # noqa: E402
from research_agent.pipeline.scanner import scan_portals  # noqa: E402
from research_agent.sources.ats.registry import default_adapter_registry  # noqa: E402

ROOT = Path(".").resolve()
OUT = ROOT / "output" / "workday_wave_20260908"
BODIES = OUT / "bodies"
CACHE = OUT / "cache"
DB_PATH = OUT / "validation.db"

TENANTS = [511, 265, 5]  # brunellocucinelli, proofpoint, airbus


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passthrough to the real network; saves every wire body to disk."""

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
            json.loads(text)  # validate JSON-ness only
            payload: dict = {
                "index": idx,
                "method": request.method,
                "url": str(request.url),
                "request_body": request.content.decode("utf-8", errors="replace"),
                "status": response.status_code,
                "response_body": text,
            }
        except (ValueError, UnicodeDecodeError):
            payload = {
                "index": idx,
                "method": request.method,
                "url": str(request.url),
                "request_body": "",
                "status": response.status_code,
                "response_body_base64": base64.b64encode(body).decode("ascii"),
            }
        (self._dir / f"wire_{idx:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        self.wires.append(
            {
                "index": idx,
                "method": request.method,
                "url": str(request.url),
                "status": response.status_code,
                "bytes": len(body),
            }
        )
        return httpx.Response(
            response.status_code,
            headers=[
                (k, v)
                for k, v in response.headers.multi_items()
                if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
            ],
            content=body,
            request=request,
        )

    async def aclose(self) -> None:
        await self._real.aclose()


async def scan_one(engine, settings, portal_id: int, recorder: RecordingTransport):
    start_wires = len(recorder.wires)
    summary = await scan_portals(
        engine,
        default_adapter_registry(),
        settings,
        portal_ids={portal_id},
        cache_directory=CACHE,
        transport=recorder,
        run_source="workday_validation_20260908",
    )
    return summary, recorder.wires[start_wires:]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        shutil.rmtree(CACHE)
    CACHE.mkdir(parents=True, exist_ok=True)

    prod_settings = get_settings()
    prod_engine = create_db_engine(prod_settings.database_url)
    print("prod_db_url:", prod_settings.database_url, flush=True)
    print("prod_default max_jobs_per_portal:", prod_settings.scanner.max_jobs_per_portal, flush=True)
    print("prod_default max_pages_per_portal:", prod_settings.scanner.max_pages_per_portal, flush=True)

    if DB_PATH.exists():
        DB_PATH.unlink()
    prepare_pilot_database(prod_engine, DB_PATH, replace=True)
    engine = create_db_engine(f"sqlite:///{DB_PATH}")

    settings = prod_settings.scanner.model_copy(
        update={
            "global_concurrency": 1,
            "per_domain_concurrency": 1,
            "per_domain_min_interval_seconds": 5.0,
            "max_retries": 0,
            "jitter_seconds": 0.0,
            "max_requests_per_host_per_run": 7,
            "max_requests_per_run": 7,
            "max_pages_per_portal": 5,
            "max_jobs_per_portal": 500,
            "bulk_catalog_max_jobs_per_portal": 5000,
            "host_cooldown_hours": 72.0,
            "run_timeout_seconds": 300.0,
        }
    )
    print("validation settings: concurrency=1 retries=0 pages<=5 jobs<=500/run wires<=7", flush=True)

    recorder = RecordingTransport(BODIES)
    manifest: dict = {"tenants": [], "total_wires": 0, "stop": None}
    for i, pid in enumerate(TENANTS):
        if len(recorder.wires) + 7 > 21:
            manifest["stop"] = f"wire budget guard before {pid}: {len(recorder.wires)} used"
            print(manifest["stop"], flush=True)
            break
        if i:
            print("pacing 10s between tenants...", flush=True)
            time.sleep(10)
        print(f"=== tenant {pid} ===", flush=True)
        summary = None
        try:
            summary, wires = asyncio.run(scan_one(engine, settings, pid, recorder))
        except Exception as exc:  # isolation: record and stop
            print(f"portal {pid} SCAN EXCEPTION: {type(exc).__name__}: {exc}", flush=True)
            manifest["tenants"].append({"portal_id": pid, "exception": f"{type(exc).__name__}: {exc}"})
            manifest["stop"] = f"exception on {pid}"
            break
        result = summary.portal_results[0]
        persisted_info: dict = {"persisted": False}
        if result.status == "SUCCESS":
            gate = assess_scan_gate(
                summary,
                ScanGatePolicy(
                    max_failure_rate=0.0,
                    max_retry_rate=0.0,
                    max_http_429=0,
                    max_unexpected_empty_complete=0,
                ),
            )
            print(f"  gate passed={gate.passed}", flush=True)
            if gate.passed:
                persisted = persist_scan_discoveries(engine, summary)
                persisted_info = {
                    "persisted": True,
                    "new": persisted.new_source_jobs,
                    "updated": persisted.updated_source_jobs,
                    "pending_ai": persisted.pending_ai,
                }
                print(f"  persist: {persisted_info}", flush=True)
            else:
                print(f"  persist SKIPPED: gate failed", flush=True)
        tenant = {
            "portal_id": pid,
            "status": result.status,
            "adapter": result.adapter,
            "final_http_status": result.final_http_status,
            "complete_snapshot": result.complete_snapshot,
            "warnings": list(result.warnings),
            "adapter_jobs": len(result.jobs),
            "retry_count": result.retry_count,
            "cache_hit": result.cache_hit,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "persistence": persisted_info,
            "wires": wires,
        }
        print(json.dumps({k: v for k, v in tenant.items() if k != "wires"}, ensure_ascii=False), flush=True)
        for w in wires:
            print("  wire:", w, flush=True)
        manifest["tenants"].append(tenant)
        bad = [w for w in wires if w["status"] in (401, 403, 429)]
        challenge = result.error_type in ("AccessChallengeError", "RobotsDisallowed")
        if bad or challenge or result.final_http_status in (401, 403, 429):
            manifest["stop"] = f"safety signal on {pid}"
            print(f"STOP signal on {pid}; aborting remaining tenants", flush=True)
            break
        if result.status != "SUCCESS":
            manifest["stop"] = f"non-success on {pid}: {result.error_type}"
            print(f"non-success on {pid}; aborting remaining tenants", flush=True)
            break

    manifest["total_wires"] = len(recorder.wires)
    (OUT / "catalog_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("TOTAL_WIRES:", len(recorder.wires), flush=True)
    print("manifest:", OUT / "catalog_manifest.json", flush=True)


if __name__ == "__main__":
    main()

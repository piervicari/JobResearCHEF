"""Phase 4 NVIDIA exact accounting (0 wires)."""
import base64
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, "src")

from research_agent.sources.declarative import executor  # noqa: E402
from research_agent.sources.declarative.adapter import (  # noqa: E402
    load_declarative_adapter,
    normalized_job_to_raw_job,
)

OUT = Path("output/eightfold_nvidia_20260908").resolve()
DB = OUT / "validation.db"


def body_of(wire: dict) -> str:
    if "response_body" in wire:
        return wire["response_body"]
    return base64.b64decode(wire["response_body_base64"]).decode("utf-8")


def main() -> None:
    manifest = json.loads((OUT / "catalog_manifest.json").read_text())
    pid = manifest["portal_id"]
    adapter = load_declarative_adapter()
    spec = adapter._specs["https://jobs.nvidia.com/careers"]
    wires = [json.loads(p.read_text()) for p in sorted((OUT / "bodies").glob("wire_*.json"))]
    print(f"saved wires: {len(wires)}")
    api_ids: list[str] = []
    adapter_ids: list[str] = []
    skipped: list[str] = []
    for w in wires:
        q = parse_qs(urlsplit(w["url"]).query)
        payload = json.loads(body_of(w))
        items, total = executor.extract_page(spec, payload)
        print(f"  [{w['index']}] start={q.get('start')} items={len(items)} total={total}")
        for i, raw in enumerate(items):
            item = raw if isinstance(raw, dict) else {}
            sid = item.get("id")
            api_ids.append(str(sid))
            try:
                partial = executor.extract_item(spec, item)
                normalized = executor.normalize_job(spec, partial, "2026-09-08T00:00:00+00:00")
                adapter_ids.append(normalized_job_to_raw_job(spec, normalized, native_item=item).source_job_id)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{q.get('start')}[{i}]: {exc}")
    print(f"api_rows={len(api_ids)} adapter_rows={len(adapter_ids)} skipped={len(skipped)} {skipped[:3]}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select id,native_source_job_id,ats_job_id,raw_title,raw_location,raw_description,"
        "source_url,apply_url from source_jobs where portal_id=? order by id", (pid,)).fetchall()
    db_ids = [r[1] for r in rows]
    print(f"persisted={len(rows)} unique={len(set(db_ids))}")
    a, d, p = set(api_ids), set(adapter_ids), set(db_ids)
    print("API==adapter:", a == d, " adapter==persisted:", d == p, " API==persisted:", a == p)
    if a != p:
        print("  missing:", sorted(a - p)[:5], " unexpected:", sorted(p - a)[:5])
    print("dups:", len(adapter_ids) - len(d))
    n = len(rows)
    print("title:", sum(1 for r in rows if (r[3] or '').strip()), "/", n,
          "location:", sum(1 for r in rows if (r[4] or '').strip()), "/", n,
          "desc:", sum(1 for r in rows if (r[5] or '').strip()), "/", n)
    r0 = rows[0]
    print("sample id:", r0[0], "native:", r0[1], "ats:", r0[2])
    print("  title:", (r0[3] or '')[:100])
    print("  loc:", (r0[4] or '')[:100], " desc_chars:", len(r0[5] or ''))
    print("  source_url:", r0[6])
    print("  apply_url:", (r0[7] or '')[:100])
    att = con.execute("select snapshot_complete,http_status,retries,jobs_observed from portal_scan_attempts"
                      " where portal_id=? order by id desc limit 1", (pid,)).fetchone()
    print("scan_attempt complete:", att[0], "http:", att[1], "retries:", att[2], "observed:", att[3])
    con.close()


if __name__ == "__main__":
    main()

"""Offline analysis of the Workday validation wave (0 wires).

Reads output/workday_wave_20260908/bodies/wire_*.json + catalog_manifest.json
+ validation.db and proves per tenant:
  API/native ID set == adapter ID set == unique ID set == persisted ID set,
plus coverage stats and pagination accounting.
"""
import base64
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")

from research_agent.sources.ats.workday import WorkdayAdapter  # noqa: E402

OUT = Path("output/workday_wave_20260908")
BODIES = OUT / "bodies"
DB = OUT / "validation.db"


def body_of(wire: dict) -> str:
    if "response_body" in wire:
        return wire["response_body"]
    return base64.b64decode(wire["response_body_base64"]).decode("utf-8", errors="replace")


def adapter_ids_for(postings: list, site_url: str) -> tuple[list[str], list[str]]:
    ad = WorkdayAdapter()
    ids, skipped = [], []
    for i, job in enumerate(postings):
        try:
            ids.append(ad._parse_job(job, site_url=site_url, index=i).source_job_id)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{i}: {exc}")
    return ids, skipped


def main() -> None:
    manifest = json.loads((OUT / "catalog_manifest.json").read_text())
    wires_all = []
    for path in sorted(BODIES.glob("wire_*.json")):
        wires_all.append(json.loads(path.read_text()))
    print(f"saved wires on disk: {len(wires_all)}")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for tenant in manifest["tenants"]:
        pid = tenant["portal_id"]
        twires = tenant.get("wires", [])
        print(f"--- portal {pid} status={tenant.get('status')} adapter={tenant.get('adapter')} "
              f"complete={tenant.get('complete_snapshot')} warnings={tenant.get('warnings')}")
        landing = [w for w in twires if w["method"] == "GET"]
        posts = [w for w in twires if w["method"] == "POST"]
        print(f"  wires={len(twires)} (GET={len(landing)} POST={len(posts)}) retries={tenant.get('retry_count')} cache_hit={tenant.get('cache_hit')}")
        for w in twires:
            print(f"    [{w['index']}] {w['method']} {w['url'][:110]} -> {w['status']} ({w['bytes']}b)")

        # bootstrap identifiers from saved landing body (offline)
        if landing:
            lwire = next(w for w in wires_all if w["index"] == landing[0]["index"])
            html = body_of(lwire)
            t_match, s_match = WorkdayAdapter._TENANT.search(html), WorkdayAdapter._SITE.search(html)
            print(f"  bootstrap tenant={t_match.group(1) if t_match else None} site={s_match.group(1) if s_match else None}")

        # catalog pages offline
        api_ids: list[str] = []
        offsets = []
        totals = set()
        for w in posts:
            pw = next(x for x in wires_all if x["index"] == w["index"])
            req = json.loads(pw["request_body"])
            payload = json.loads(body_of(pw))
            postings = payload.get("jobPostings", [])
            offsets.append(req.get("offset"))
            totals.add(payload.get("total"))
            print(f"    offset={req.get('offset')} limit={req.get('limit')} items={len(postings)} total={payload.get('total')}")
            for job in postings:
                bullets = job.get("bulletFields") or []
                req_id = next((b.strip() for b in bullets if isinstance(b, str) and b.strip()), "")
                api_ids.append(req_id or job.get("externalPath", ""))
        print(f"  offsets={offsets} totals_seen={sorted(totals)} api_rows={len(api_ids)}")

        # adapter replay offline (real _parse_job, 0 wires)
        site_url = ""
        if posts:
            from urllib.parse import urlsplit
            first_url = posts[0]["url"]
            parts = urlsplit(first_url)
            origin = f"{parts.scheme}://{parts.netloc}"
            segs = [s for s in parts.path.split('/') if s]
            site_url = f"{origin}/{segs[2]}" if len(segs) >= 3 else origin
        parsed_ids, skipped = [], []
        for w in posts:
            pw = next(x for x in wires_all if x["index"] == w["index"])
            payload = json.loads(body_of(pw))
            ids, sk = adapter_ids_for(payload.get("jobPostings", []), site_url)
            parsed_ids.extend(ids)
            skipped.extend(sk)
        print(f"  adapter_rows={len(parsed_ids)} skipped={len(skipped)} {skipped[:3]}")

        rows = con.execute(
            "select native_source_job_id, ats_job_id, requisition_id, raw_title, raw_location,"
            " raw_employment_type, raw_workplace_type, raw_description, source_url, raw_payload_json"
            " from source_jobs where portal_id=?", (pid,)).fetchall()
        db_ids = [r[0] for r in rows]
        print(f"  persisted={len(rows)} unique_db_ids={len(set(db_ids))}")
        api_set, ad_set, db_set = set(api_ids), set(parsed_ids), set(db_ids)
        print(f"  API==adapter: {api_set == ad_set}  adapter==persisted: {ad_set == db_set}  "
              f"API==persisted: {api_set == db_set}")
        if api_set != db_set:
            print(f"    missing_in_db={sorted(api_set - db_set)[:5]} unexpected_in_db={sorted(db_set - api_set)[:5]}")
        dups = len(parsed_ids) - len(ad_set)
        print(f"  duplicates={dups} malformed_skipped={len(skipped)}")
        n = max(len(rows), 1)
        cov = {
            "title": sum(1 for r in rows if (r[3] or '').strip()),
            "location": sum(1 for r in rows if (r[4] or '').strip()),
            "employment": sum(1 for r in rows if (r[5] or '').strip()),
            "workplace": sum(1 for r in rows if (r[6] or '').strip()),
            "requisition": sum(1 for r in rows if (r[2] or '').strip()),
            "description": sum(1 for r in rows if (r[7] or '').strip()),
        }
        print("  coverage:", {k: f"{v}/{len(rows)}" for k, v in cov.items()})
        descs = [len(r[7] or '') for r in rows if (r[7] or '').strip()]
        if descs:
            s = sorted(descs)
            print(f"  desc_len min/med/max: {s[0]}/{s[len(s)//2]}/{s[-1]}")
        extpaths = sum(1 for r in rows if json.loads(r[9] or '{}').get('externalPath'))
        print(f"  rows_with_externalPath={extpaths}/{len(rows)}")
        attempt = con.execute(
            "select snapshot_complete, http_status, retries, jobs_observed from portal_scan_attempts"
            " where portal_id=? order by id desc limit 1", (pid,)).fetchone()
        print(f"  scan_attempt: complete={attempt[0]} http={attempt[1]} retries={attempt[2]} observed={attempt[3]}")
    con.close()


if __name__ == "__main__":
    main()

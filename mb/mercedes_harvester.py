#!/usr/bin/env python3
"""
Mercedes-Benz career harvester — conservative, idempotent, deterministic.

Design goals (in order of priority):
  1. Never get the IP blocked. 403/429 → abort cleanly.
  2. No concurrency, no UA rotation, no proxy, no CAPTCHA.
  3. Only the endpoint verified during discovery is used.
  4. The catalog response already contains the full MatchedObjectDescriptor
     (description + qualifications). We DO NOT issue a second "detail" pass.
     Change detection uses a lightweight content_hash on catalog fields.
     When content_hash differs we recompute full_hash from the SAME
     response's description fields and re-flag for semantic analysis.
  5. Semantic classification is OUT OF SCOPE here — we only produce
     new_or_changed_jobs.json for an LLM to read later.

Run modes:
  python3 mercedes_harvester.py --bootstrap   # first run: populate SQLite
  python3 mercedes_harvester.py              # normal incremental run

Reads:
  harvester_config.json

Writes:
  mercedes_jobs.db                  SQLite state
  output/run_summary.json           run stats (every run)
  output/new_or_changed_jobs.json   only jobs that need LLM analysis
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "harvester_config.json")


# ---------- config ----------

def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------- safety ----------

class SafetyAbort(Exception):
    """Raised when we must stop making requests for safety reasons."""

    def __init__(self, reason: str, status: int | None = None, url: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.url = url


# ---------- single-flight pacing ----------

class Pacer:
    """One-request-at-a-time pacer with jitter and a long pause every N requests."""

    def __init__(self, min_seconds: float, jitter_max: float,
                 long_every: int, long_seconds: float):
        self.min_seconds = min_seconds
        self.jitter_max = jitter_max
        self.long_every = long_every
        self.long_seconds = long_seconds
        self._last_ts: float = 0.0
        self._req_count = 0

    def wait(self) -> None:
        # Sleep at least (min_seconds + small jitter), and add a longer
        # pause every N requests. The jitter is small and uniform; it is
        # NOT meant to evade any anti-bot system, only to spread load.
        now = time.monotonic()
        elapsed = now - self._last_ts
        base = self.min_seconds + random.uniform(0.0, self.jitter_max)
        sleep_for = max(0.0, base - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._req_count += 1
        if self.long_every > 0 and self._req_count % self.long_every == 0:
            time.sleep(self.long_seconds)


# ---------- HTTP ----------

class Harvester:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        api = cfg["api"]
        self.search_url = api["search_url"]
        self.headers = dict(api["headers"])
        self.page_size = int(api["page_size"])
        self.timeout = int(api["request_timeout_seconds"])

        pacing = cfg["pacing"]
        self.pacer = Pacer(
            min_seconds=float(pacing["min_seconds_between_requests"]),
            jitter_max=float(pacing["jitter_seconds_max"]),
            long_every=int(pacing["long_pause_every_n_requests"]),
            long_seconds=float(pacing["long_pause_seconds"]),
        )
        self.retry_after_5xx = float(pacing["retry_after_5xx_seconds"])

        safety = cfg["safety"]
        self.max_requests_per_run = int(safety["max_requests_per_run"])
        self.abort_on_403 = bool(safety["abort_on_http_403"])
        self.abort_on_429 = bool(safety["abort_on_http_429"])
        self.max_retries_5xx = int(safety["max_retries_on_5xx"])
        self.max_consecutive_errors = int(safety["max_consecutive_errors"])

        # runtime counters
        # http_requests_total counts EVERY real attempt to talk to the wire:
        # first try, retries after 5xx, retries after network errors. The
        # safety circuit breaker uses this counter — it is the only counter
        # that reflects the actual cost paid to the upstream.
        self.http_requests_total = 0
        # logical metrics, useful for run_summary.json
        self.catalog_requests = 0
        self.detail_requests = 0
        self.http_403_count = 0
        self.http_429_count = 0
        self.http_5xx_count = 0
        self.http_network_error_count = 0
        self.errors: list[str] = []
        self._consecutive_errors = 0
        self.aborted_for_safety = False
        self.abort_reason: str | None = None

        # the only endpoint we ever hit
        self._allowed_hosts = {"jobs.api.mercedes-benz.com"}

    # ---- low-level POST (the only HTTP entry point) ----

    def _post(self, payload: dict) -> dict:
        from urllib.parse import urlparse
        host_ok = urlparse(self.search_url).hostname in self._allowed_hosts
        if not host_ok:
            raise SafetyAbort(f"refusing to call non-allowed host: {self.search_url}")

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.search_url,
            data=body,
            headers=dict(self.headers),
            method="POST",
        )
        attempts = 0
        while True:
            attempts += 1
            # Increment the wire counter ONLY for attempts that actually
            # touch the network. The breaker check happens BEFORE the
            # increment so an over-cap call costs us 0 wire attempts.
            if self.http_requests_total >= self.max_requests_per_run:
                raise SafetyAbort("max_requests_per_run reached")

            self.http_requests_total += 1
            self.pacer.wait()

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    status = resp.status
            except urllib.error.HTTPError as e:
                status = e.code
                raw = b""
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                status = -1
                raw = b""
                self.http_network_error_count += 1
                self._consecutive_errors += 1
                self.errors.append(f"network: {e!r}")
                # Retry semantics:
                #   attempts == 1   → the original wire attempt. We may retry.
                #   attempts == max_retries_5xx + 1 → we've used up our retry
                #                                 budget. Abort.
                # Concretely: max_retries_on_5xx = 1 means EXACTLY 1 original
                # + 1 retry = 2 wire attempts.
                if attempts <= self.max_retries_5xx and self._consecutive_errors <= self.max_consecutive_errors:
                    time.sleep(self.retry_after_5xx)
                    continue
                if self._consecutive_errors > self.max_consecutive_errors:
                    raise SafetyAbort(
                        f"too many consecutive errors ({self._consecutive_errors})"
                    )
                raise SafetyAbort(f"network error after retries: {e!r}")

            if status == 403 and self.abort_on_403:
                self.http_403_count += 1
                self._consecutive_errors += 1
                raise SafetyAbort("HTTP 403 from Mercedes", status=status, url=self.search_url)
            if status == 429 and self.abort_on_429:
                self.http_429_count += 1
                self._consecutive_errors += 1
                raise SafetyAbort("HTTP 429 from Mercedes", status=status, url=self.search_url)
            if 500 <= status < 600:
                self.http_5xx_count += 1
                self._consecutive_errors += 1
                self.errors.append(f"5xx: {status}")
                if attempts <= self.max_retries_5xx and self._consecutive_errors <= self.max_consecutive_errors:
                    time.sleep(self.retry_after_5xx)
                    continue
                if self._consecutive_errors > self.max_consecutive_errors:
                    raise SafetyAbort(
                        f"too many consecutive errors ({self._consecutive_errors})"
                    )
                raise SafetyAbort(f"HTTP {status} after retries", status=status, url=self.search_url)

            # success path
            self._consecutive_errors = 0
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise SafetyAbort(f"non-JSON response: {e!r}")

    # ---- semantic wrappers ----

    def catalog_request(self, keyword: str, lang: str, first: int) -> dict:
        """Single endpoint, single payload shape. Counts as a catalog request
        in the logical metric; bumps http_requests_total inside _post.
        """
        payload = {
            "LanguageCode": lang,
            "SearchParameters": {
                "FirstItem": first,
                "CountItem": self.page_size,
                "Sort": [{
                    "Criterion": self.cfg["search"]["sort_criterion"],
                    "Direction": "DESC",
                }],
            },
            "SearchCriteria": [{
                "CriterionName": "PositionFormattedDescription.Content",
                "CriterionValue": [keyword],
            }],
        }
        self.catalog_requests += 1
        return self._post(payload)


# ---------- change detection ----------
#
# Three hashes with disjoint responsibilities:
#
#   metadata_hash    — everything NOT used to decide "needs semantic
#                       re-classification". Catches location/date/URL/
#                       apply-URI/contact/career-level tweaks that don't
#                       change what the job IS, only how it's displayed.
#
#   description_hash — ONLY the Tasks + Qualifications text (HTML stripped,
#                       whitespace normalised). Detects edits to the job
#                       description without touching metadata.
#
#   semantic_hash    — the union of fields that, when ANY of them changes,
#                       warrant re-running the downstream LLM classifier.
#                       Today this is title + department + description text.
#                       We deliberately EXCLUDE company, location, dates,
#                       URLs, and other metadata: those never affect whether
#                       a job is "cyber".
#
# All three hashes are computed from data that is already in the catalog
# response. No additional HTTP requests are needed.
#
# Decision rule for `needs_semantic_analysis`:
#   semantic_hash changed (and PID was known)         → 1
#   metadata_hash changed but semantic_hash unchanged  → 0 (DB updated,
#                                                       no LLM call)
#   PID unseen                                         → 1 (always new)
#   everything unchanged                               → 0

METADATA_FIELDS = [
    "PositionTitle", "DepartmentName", "ParentOrganizationName",
    "PublicationStartDate", "PublicationEndDate", "PositionStartDate",
    "PositionLocation", "CareerLevel", "JobCategory", "TargetGroup",
    "PositionOfferingType", "PositionSchedule",
    "PositionURI", "ApplyURI",
]

SEMANTIC_FIELDS = [
    "PositionTitle", "DepartmentName",
    "_Tasks", "_Qualifications",   # synthetic keys produced by _flatten_description
]


def _strip_html(s: str) -> str:
    """Strip HTML tags and normalise whitespace. Used so that a re-render
    of the same description with new tags / new indentation doesn't
    produce a spurious description_hash mismatch.
    """
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _location_summary(locs) -> str:
    if not locs:
        return ""
    out = []
    for l in locs:
        out.append(
            f"{l.get('CityName','')}|{l.get('CountryCode','')}|"
            f"{l.get('CountryName','')}|{l.get('DisplayName','')}"
        )
    return "\n".join(out)


def _flatten_description(md: dict) -> tuple[str, str]:
    """Return (tasks_text, qualifications_text) — HTML-stripped, joined
    across all entries in PositionFormattedDescription.
    """
    desc = md.get("PositionFormattedDescription") or []
    tasks_parts: list[str] = []
    quals_parts: list[str] = []
    if isinstance(desc, list):
        for d in desc:
            t = d.get("Tasks") or ""
            q = d.get("Qualifications") or ""
            if t:
                tasks_parts.append(_strip_html(t))
            if q:
                quals_parts.append(_strip_html(q))
    return "\n".join(tasks_parts), "\n".join(quals_parts)


def _normalise_list_field(v) -> str:
    """Normalise a list field for hashing.

    Items may be either dicts (e.g. CareerLevel, JobCategory with
    {Code, Name} pairs) or plain strings (e.g. entries of ApplyURI).
    """
    if not isinstance(v, list):
        return ""
    parts: list[str] = []
    for x in v:
        if isinstance(x, dict):
            parts.append(f"{x.get('Code','')}:{x.get('Name','')}")
        else:
            parts.append(str(x))
    return "|".join(sorted(parts))


def metadata_hash(md: dict) -> str:
    """Hash over all METADATA fields. Sensitive to location, dates, URLs,
    career level, org name, etc. Insensitive to description text."""
    parts: list[str] = []
    for f in METADATA_FIELDS:
        v = md.get(f)
        if f == "PositionLocation":
            v = _location_summary(v or [])
        elif isinstance(v, list):
            v = _normalise_list_field(v)
        parts.append(f"{f}={v}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def description_hash(md: dict) -> str:
    """Hash over description + qualifications ONLY (HTML-stripped,
    whitespace-normalised). Independent of metadata."""
    tasks, quals = _flatten_description(md)
    payload = f"TASKS={tasks}\nQUALS={quals}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_hash(md: dict) -> str:
    """Hash over the SEMANTIC fields — title + department + description
    text. If this hash differs from the stored one, the job needs a new
    classification from the LLM. We do NOT include company/location/dates
    here: those never affect whether the job is cyber.
    """
    tasks, quals = _flatten_description(md)
    parts = [
        f"PositionTitle={md.get('PositionTitle') or ''}",
        f"DepartmentName={md.get('DepartmentName') or ''}",
        f"_Tasks={tasks}",
        f"_Qualifications={quals}",
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# ---------- sqlite ----------

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    source_job_id        TEXT PRIMARY KEY,
    internal_id          TEXT,
    title                TEXT NOT NULL,
    company              TEXT,
    department           TEXT,
    locations_json       TEXT,
    job_url              TEXT,
    apply_url            TEXT,
    publication_start    TEXT,
    publication_end      TEXT,
    position_start       TEXT,
    description          TEXT,
    qualifications       TEXT,
    metadata_hash        TEXT NOT NULL,
    description_hash     TEXT,
    semantic_hash        TEXT,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    last_seen_run_at     TEXT NOT NULL,
    is_open              INTEGER NOT NULL,
    needs_semantic_analysis INTEGER NOT NULL,
    last_seen_keyword    TEXT
);

CREATE INDEX IF NOT EXISTS ix_jobs_is_open ON jobs(is_open);
CREATE INDEX IF NOT EXISTS ix_jobs_needs_semantic ON jobs(needs_semantic_analysis);
"""


# Schema migrations for DBs created by previous harvester versions.
# Each ALTER is wrapped to tolerate the column already existing.
MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN metadata_hash TEXT",
    "ALTER TABLE jobs ADD COLUMN description_hash TEXT",
    "ALTER TABLE jobs ADD COLUMN semantic_hash TEXT",
]


def db_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    for stmt in DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)
    # Run migrations. Old DBs may still have the legacy content_hash /
    # full_hash columns; we ignore them (they will simply not be written
    # by the new code path) and add the three new hash columns.
    for stmt in MIGRATIONS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def md_to_row(md: dict, *, first_seen: str, last_seen: str, run_at: str,
              keyword: str, store_full: bool) -> dict:
    tasks, quals = _flatten_description(md)
    locs = md.get("PositionLocation") or []
    apply = md.get("ApplyURI") or []
    apply_url = apply[0] if apply else None

    return {
        "source_job_id": md.get("PositionID") or md.get("ID"),
        "internal_id": str(md.get("ID")) if md.get("ID") is not None else None,
        "title": md.get("PositionTitle"),
        "company": md.get("ParentOrganizationName"),
        "department": md.get("DepartmentName"),
        "locations_json": json.dumps(locs, ensure_ascii=False, sort_keys=True),
        "job_url": md.get("PositionURI"),
        "apply_url": apply_url,
        "publication_start": md.get("PublicationStartDate"),
        "publication_end": md.get("PublicationEndDate"),
        "position_start": md.get("PositionStartDate"),
        # description/qualifications are stored HTML-stripped. We keep the
        # raw HTML out of the DB on purpose: the hash uses the stripped
        # form and the LLM downstream will also receive the stripped text.
        "description": tasks if store_full else None,
        "qualifications": quals if store_full else None,
        "metadata_hash": metadata_hash(md),
        "description_hash": description_hash(md),
        "semantic_hash": semantic_hash(md),
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "last_seen_run_at": run_at,
        "is_open": 1,
        "needs_semantic_analysis": 0,
        "last_seen_keyword": keyword,
    }


# ---------- harvesting logic ----------

def fetch_keyword(h: Harvester, keyword: str, lang: str) -> dict | None:
    """Pull all pages for one keyword. The response already contains the
    full MatchedObjectDescriptor (description + qualifications) for every
    item, so we never need a second pass.

    Returns a dict with keys: keyword, total, items, complete (bool).
    `complete` is False ONLY if the global circuit breaker tripped before
    we reached SearchResultCountAll. There is intentionally NO per-keyword
    page cap: the global breaker is the single authority for "stop
    pulling".
    """
    first = 1
    aggregated: list[dict] = []
    total = None
    complete = True
    while True:
        try:
            res = h.catalog_request(keyword, lang, first)
        except SafetyAbort:
            raise
        if total is None:
            total = res["SearchResult"]["SearchResultCountAll"]
        aggregated.extend(res["SearchResult"]["SearchResultItems"])
        fetched = len(res["SearchResult"]["SearchResultItems"])
        if fetched == 0:
            break
        if first + fetched > total:
            break
        first += fetched
    # dedupe by PositionID keeping the English variant (Code=="1")
    by_pid: dict[str, dict] = {}
    for it in aggregated:
        md = it["MatchedObjectDescriptor"]
        pid = md.get("PositionID")
        if not pid:
            continue
        cur_lang = (md.get("PublicationLanguage") or {}).get("Code", "")
        if pid in by_pid:
            prev_lang = (by_pid[pid].get("PublicationLanguage") or {}).get("Code", "")
            if prev_lang == "1":
                continue
            if cur_lang == "1":
                by_pid[pid] = md
        else:
            by_pid[pid] = md
    return {
        "keyword": keyword,
        "total": total or 0,
        "items": list(by_pid.values()),
        "complete": complete,
    }


def harvest_catalog(h: Harvester, cfg: dict) -> tuple[dict[str, dict], dict[str, list[str]], bool]:
    """Run every keyword. Returns (by_pid, by_keyword, catalog_complete).

    catalog_complete is True iff EVERY keyword's pagination ended because
    we reached its own SearchResultCountAll. If even one keyword was cut
    short by SafetyAbort (breaker, 403/429, network) we mark the whole
    catalog as incomplete — there is no per-keyword page cap any more,
    so the only way a keyword can be cut short is a safety event.
    """
    keywords = list(cfg["search"]["keywords"])[:int(cfg["search"].get("max_keywords_per_run", 22))]
    lang = cfg["search"]["language"]

    by_pid: dict[str, dict] = {}
    by_keyword: dict[str, list[str]] = {}
    catalog_complete = True

    for kw in keywords:
        try:
            r = fetch_keyword(h, kw, lang)
        except SafetyAbort as e:
            h.aborted_for_safety = True
            h.abort_reason = str(e)
            catalog_complete = False
            break
        if not r:
            continue
        if not r["complete"]:
            catalog_complete = False
        by_keyword[kw] = []
        for it in r["items"]:
            md = it
            pid = md.get("PositionID")
            if not pid:
                continue
            if pid not in by_pid:
                by_pid[pid] = md
                by_keyword[kw].append(pid)
            else:
                prev = by_pid[pid]
                prev_lang = (prev.get("PublicationLanguage") or {}).get("Code", "")
                cur_lang = (md.get("PublicationLanguage") or {}).get("Code", "")
                if prev_lang != "1" and cur_lang == "1":
                    by_pid[pid] = md
                    by_keyword[kw].append(pid)
    return by_pid, by_keyword, catalog_complete


# ---------- main ----------

def run(cfg: dict, mode: str) -> dict:
    storage = cfg["storage"]
    db_path = os.path.join(HERE, storage["db_path"])
    out_dir = os.path.join(HERE, storage["output_dir"])
    os.makedirs(out_dir, exist_ok=True)

    started_at = now_iso()
    summary = {
        "started_at": started_at,
        "mode": mode,
        "catalog_complete": True,
        "catalog_incomplete_reason": None,
        "catalog_jobs_seen": 0,
        "new_jobs": 0,
        "changed_jobs": 0,
        "unchanged_jobs": 0,
        "seeded_jobs": 0,                # bootstrap only
        "closed_jobs": 0,
        "http_requests_total": 0,
        "catalog_requests": 0,
        "detail_requests": 0,
        "http_403_count": 0,
        "http_429_count": 0,
        "http_5xx_count": 0,
        "http_network_error_count": 0,
        "errors": [],
        "aborted_for_safety": False,
        "abort_reason": None,
        "closed_calculation_skipped": False,
    }

    h = Harvester(cfg)
    conn = db_connect(db_path)

    # Wrap the entire body in try/finally so that on SafetyAbort we
    # still flush DB writes and emit the summary. The whole point is
    # that a partial catalog must leave a consistent DB behind and the
    # caller must still get a run_summary.json describing the partial
    # state.
    by_pid: dict[str, dict] = {}
    by_keyword: dict[str, list[str]] = {}
    catalog_complete = True
    new_jobs_out: list[dict] = []
    closed_pids: set[str] = set()
    new_pids: set[str] = set()
    possibly_changed_pids: set[str] = set()
    unchanged_pids: set[str] = set()
    seeded_count = 0
    try:
        # 1. Catalog pass
        by_pid, by_keyword, catalog_complete = harvest_catalog(h, cfg)
        # Reflect the catalog completeness in the summary immediately so
        # that downstream branches in the run can rely on it.
        summary["catalog_complete"] = catalog_complete
        summary["catalog_incomplete_reason"] = h.abort_reason if not catalog_complete else None
        summary["aborted_for_safety"] = h.aborted_for_safety
        summary["abort_reason"] = h.abort_reason
        summary["catalog_requests"] = h.catalog_requests
        summary["http_requests_total"] = h.http_requests_total
        summary["detail_requests"] = h.detail_requests
        summary["catalog_jobs_seen"] = len(by_pid)

        # 2. Load known PIDs from DB. We need:
        #    - metadata_hash + description_hash + is_open  for CHANGE DETECTION
        #    - semantic_hash            for SEMANTIC RECLASSIFICATION decision
        cur = conn.execute(
            "SELECT source_job_id, metadata_hash, description_hash, semantic_hash, is_open FROM jobs"
        )
        known: dict[str, dict] = {
            row[0]: {"meta": row[1], "desc": row[2], "sem": row[3], "is_open": row[4]}
            for row in cur.fetchall()
        }

        seen_pids = set(by_pid.keys())

        # Classify. A job is "possibly_changed" if ANY of metadata_hash or
        # description_hash differs from what we previously stored. We do
        # NOT yet decide whether it needs a new semantic classification —
        # that's done below by comparing semantic_hash.
        for pid, md in by_pid.items():
            prev = known.get(pid)
            new_meta = metadata_hash(md)
            new_desc = description_hash(md)
            if prev is None:
                new_pids.add(pid)
            elif prev["meta"] != new_meta or prev.get("desc") != new_desc:
                possibly_changed_pids.add(pid)
            else:
                unchanged_pids.add(pid)

        # CLOSED is ONLY computed and applied when the catalog is complete.
        # A partial catalog must NEVER mark jobs as closed — that would be
        # a destructive update based on absence of evidence.
        if catalog_complete:
            closed_pids = {pid for pid, st in known.items()
                           if st["is_open"] == 1 and pid not in seen_pids}
        else:
            summary["closed_calculation_skipped"] = True

        run_at = now_iso()

        # 4. Upsert rows (single source of truth: the catalog response we
        # already have — no second "detail" pass).
        for pid, md in by_pid.items():
            existing = known.get(pid)
            if mode == "bootstrap":
                # Bootstrap seeds the DB without flagging anything for
                # semantic analysis. The next normal run will compare
                # semantic_hash and re-flag if needed.
                row = md_to_row(md, first_seen=run_at, last_seen=run_at,
                                run_at=run_at,
                                keyword=_keyword_for(pid, by_keyword),
                                store_full=True)
                row["needs_semantic_analysis"] = 0
                upsert(conn, row)
                seeded_count += 1
            elif pid in new_pids:
                # First time we see this PID → re-classification is owed.
                row = md_to_row(md, first_seen=run_at, last_seen=run_at,
                                run_at=run_at,
                                keyword=_keyword_for(pid, by_keyword),
                                store_full=True)
                row["needs_semantic_analysis"] = 1
                upsert(conn, row)
                new_jobs_out.append(row_for_output(row, md, classification="new"))
            elif pid in possibly_changed_pids:
                # metadata changed. Update the row, but only re-flag for
                # semantic analysis if the semantic_hash differs.
                row = md_to_row(md, first_seen=run_at, last_seen=run_at,
                                run_at=run_at,
                                keyword=_keyword_for(pid, by_keyword),
                                store_full=True)
                cur = conn.execute(
                    "SELECT first_seen_at, semantic_hash FROM jobs WHERE source_job_id=?",
                    (pid,),
                )
                prev = cur.fetchone()
                if prev:
                    row["first_seen_at"] = prev[0] or run_at
                    prev_semantic = prev[1]
                else:
                    prev_semantic = None
                row["needs_semantic_analysis"] = (
                    0 if prev_semantic == row["semantic_hash"] else 1
                )
                upsert(conn, row)
                if row["needs_semantic_analysis"]:
                    new_jobs_out.append(row_for_output(row, md, classification="changed"))
            else:
                # metadata unchanged — just bump last_seen_run_at and refresh
                # the keyword attribution.
                conn.execute(
                    "UPDATE jobs SET last_seen_run_at=?, is_open=1, last_seen_keyword=? "
                    "WHERE source_job_id=?",
                    (run_at, _keyword_for(pid, by_keyword), pid),
                )

        # 5. Apply CLOSED — only if catalog was complete
        if closed_pids:
            conn.executemany(
                "UPDATE jobs SET is_open=0, last_seen_run_at=? WHERE source_job_id=?",
                [(run_at, pid) for pid in closed_pids],
            )
        summary["seeded_jobs"] = seeded_count
    except SafetyAbort as e:
        # Anything that was raised mid-run is recorded and we fall through
        # to the summary/output section below.
        h.aborted_for_safety = True
        h.abort_reason = str(e)
        summary["aborted_for_safety"] = True
        summary["abort_reason"] = h.abort_reason
        summary["catalog_complete"] = False
        summary["catalog_incomplete_reason"] = h.abort_reason
    finally:
        # 6. Counts (always emitted, even on partial/aborted runs).
        # - new_jobs / changed_jobs are counted from new_jobs_out.
        # - unchanged_jobs is the EXACT number of PIDs that we saw AND
        #   whose metadata_hash matched the stored one.
        # - seeded_jobs is bootstrap-specific.
        # - closed_jobs is 0 by construction if catalog_complete is False.
        summary["new_jobs"] = sum(1 for r in new_jobs_out if r.get("_classification") == "new")
        summary["changed_jobs"] = sum(1 for r in new_jobs_out if r.get("_classification") == "changed")
        summary["unchanged_jobs"] = len(unchanged_pids)
        summary["seeded_jobs"] = seeded_count
        summary["closed_jobs"] = len(closed_pids)
        summary["http_requests_total"] = h.http_requests_total
        summary["catalog_requests"] = h.catalog_requests
        summary["detail_requests"] = h.detail_requests  # always 0 now
        summary["catalog_jobs_seen"] = len(by_pid)
        summary["http_403_count"] = h.http_403_count
        summary["http_429_count"] = h.http_429_count
        summary["http_5xx_count"] = h.http_5xx_count
        summary["http_network_error_count"] = h.http_network_error_count
        summary["errors"] = h.errors
        summary["finished_at"] = now_iso()

        # 7. Outputs (always written, even on abort)
        with open(os.path.join(out_dir, "run_summary.json"), "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        for row in new_jobs_out:
            row.pop("_classification", None)
        with open(os.path.join(out_dir, "new_or_changed_jobs.json"), "w") as f:
            json.dump(new_jobs_out, f, indent=2, ensure_ascii=False)

        try:
            conn.commit()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    return summary


def _keyword_for(pid: str, by_keyword: dict[str, list[str]]) -> str:
    for kw, pids in by_keyword.items():
        if pid in pids:
            return kw
    return ""


def upsert(conn: sqlite3.Connection, row: dict) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    col_list = ",".join(cols)
    upd = ",".join(f"{c}=excluded.{c}" for c in cols if c != "source_job_id")
    sql = (f"INSERT INTO jobs ({col_list}) VALUES ({placeholders}) "
           f"ON CONFLICT(source_job_id) DO UPDATE SET {upd}")
    conn.execute(sql, [row[c] for c in cols])


def row_for_output(row: dict, detailed: dict, classification: str = "new") -> dict:
    return {
        "source_job_id": row["source_job_id"],
        "title": row["title"],
        "company": row["company"],
        "department": row["department"],
        "job_url": row["job_url"],
        "apply_url": row["apply_url"],
        "publication_start": row["publication_start"],
        "publication_end": row["publication_end"],
        "position_start": row["position_start"],
        "description": row["description"],
        "qualifications": row["qualifications"],
        "publication_language": (detailed.get("PublicationLanguage") or {}).get("Code"),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "_classification": classification,
    }


# ---------- entrypoint ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true",
                        help="First run: populate SQLite without flagging everything as needing semantic analysis.")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--probe-full-catalog", action="store_true",
                        help="Probe-only mode: ask the API for a single empty-criteria "
                             "search to learn the total catalog size. No further sweep.")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.probe_full_catalog:
        return run_probe(cfg)

    mode = "bootstrap" if args.bootstrap else "normal"

    def _sigint(_sig, _frm):
        print("\nSIGINT received — aborting current run.", file=sys.stderr)
        sys.exit(130)
    signal.signal(signal.SIGINT, _sigint)

    summary = run(cfg, mode)
    print(json.dumps(summary, indent=2))
    return 0


def run_probe(cfg: dict) -> int:
    """Send AT MOST 2 minimal POSTs to determine whether the API supports
    an empty SearchCriteria (i.e. a full-catalog query). Print what we
    learned and exit. No DB writes, no state changes.
    """
    api = cfg["api"]
    body = json.dumps({
        "LanguageCode": cfg["search"]["language"],
        "SearchParameters": {
            "FirstItem": 1,
            "CountItem": 1,                 # probe with page size = 1
            "Sort": [{"Criterion": cfg["search"]["sort_criterion"], "Direction": "DESC"}],
        },
        "SearchCriteria": [],               # no criteria — full catalog
    }).encode("utf-8")
    req = urllib.request.Request(api["search_url"], data=body,
                                 headers=api["headers"], method="POST")
    print("Sending probe to", api["search_url"], "...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=api["request_timeout_seconds"]) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(json.dumps({
            "probe": "empty_criteria",
            "ok": False,
            "status": e.code,
            "note": "API rejected empty SearchCriteria. Cannot use full-catalog sweep.",
        }, indent=2))
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(json.dumps({"probe": "empty_criteria", "ok": False, "error": repr(e)}, indent=2))
        return 1
    total = data.get("SearchResult", {}).get("SearchResultCountAll")
    page_size = int(api["page_size"])
    est_requests = ((int(total) + page_size - 1) // page_size) if total else None
    result = {
        "probe": "empty_criteria",
        "ok": True,
        "total_full_catalog": total,
        "page_size_observed": len(data.get("SearchResult", {}).get("SearchResultItems", [])),
        "page_size_used_for_estimate": page_size,
        "estimated_full_catalog_requests": est_requests,
        "current_keyword_sweep_requests": int(cfg["search"].get("max_keywords_per_run", 22)) * 2,
        "more_efficient": "keyword_sweep" if (est_requests or 999999) > int(cfg["search"].get("max_keywords_per_run", 22)) * 2 else "full_catalog",
        "better_recall": "full_catalog",
        "note": ("full_catalog is strictly more complete because keyword search may miss cyber "
                 "positions whose description does not contain any of our 22 keywords. full_catalog "
                 "trades completeness for ~Nx higher request count.") if est_requests else None,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

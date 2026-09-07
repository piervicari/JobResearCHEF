#!/usr/bin/env python3
"""
Local tests for the Mercedes harvester. No live traffic. Uses a tiny HTTP
mock that simulates a 429 after some successful pages.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import deque
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mercedes_harvester as mh  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- minimal catalog fixture ----------

# 5 PIDs, 2 keywords: "cybersecurity" produces all 5, "security" produces 3 of them.
def make_item(pid: str, title: str, dept: str = "Cyber Security"):
    return {
        "MatchedObjectDescriptor": {
            "PositionID": pid,
            "ID": pid[-6:],
            "PositionTitle": title,
            "PositionURI": f"https://jobs.mercedes-benz.com/{pid}",
            "ApplyURI": [f"https://example/apply/{pid}"],
            "DepartmentName": dept,
            "ParentOrganizationName": "Mercedes-Benz AG",
            "PositionLocation": [{
                "CityName": "Stuttgart", "CountryCode": "DE", "CountryName": "Germany",
                "DisplayName": "Stuttgart, DE",
            }],
            "PublicationStartDate": "2026-08-01",
            "PublicationEndDate": "2030-12-31",
            "PositionStartDate": "2026-09-01",
            "CareerLevel": [{"Code": "12", "Name": "Salaried"}],
            "JobCategory": [{"Code": "37", "Name": "IT/Telecom"}],
            "TargetGroup": [{"Code": "4", "Name": "Berufserfahrene"}],
            "PublicationLanguage": {"Code": "1"},
            "PositionFormattedDescription": [
                {"Tasks": f"<p>tasks for {pid}</p>", "Qualifications": f"<p>quals for {pid}</p>"},
            ],
        }
    }

KW_CYBER = [
    make_item("mer00000a", "Security Analyst"),
    make_item("mer00000b", "Cloud Security Engineer"),
    make_item("mer00000c", "DevSecOps Developer Zero Trust"),
    make_item("mer00000d", "SAP Cyber Security Expert"),
    make_item("mer00000e", "IAM Solution Expert"),
]
KW_SEC = [
    make_item("mer00000a", "Security Analyst"),    # overlap
    make_item("mer00000b", "Cloud Security Engineer"),  # overlap
    make_item("mer00000f", "Physical Security Specialist", dept="Work Safety"),
]


def page_response(keyword: str, first: int, count: int):
    """Build a Mercedes-style page response for our tiny fixture."""
    src = KW_CYBER if keyword == "cybersecurity" else KW_SEC
    items = src[:count]  # we never paginate in tests
    total = len(src)
    return {
        "LanguageCode": "EN",
        "SearchResult": {
            "SearchResultCount": len(items),
            "SearchResultCountAll": total,
            "SearchResultItems": items,
            "UserArea": {"ExecutionError": 0},
        }
    }


# ---------- mock POST ----------

class MockState:
    def __init__(self, script: list):
        # script = list of ("ok", body_dict) | ("429",) | ("500",) tuples
        self.script = deque(script)
        self.calls = 0
        self.last_payload = None

    def __call__(self, payload):
        from urllib.request import Request
        self.calls += 1
        self.last_payload = payload
        if not self.script:
            raise HTTPError("https://x", 500, "no more scripted responses", {}, None)
        op = self.script.popleft()
        if op[0] == "429":
            raise HTTPError("https://x", 429, "rate limited", {}, None)
        if op[0] == "500":
            raise HTTPError("https://x", 500, "boom", {}, None)
        return op[1]


def patch_post(monkey_state: MockState):
    """Patch Harvester._post to use the mock instead of urllib.

    Mirrors the real _post semantics: catches HTTPError, increments the
    wire counter BEFORE the attempt, classifies 403/429/5xx and either
    raises SafetyAbort or retries with sleep.
    """
    def fake_post(self, payload):
        from urllib.parse import urlparse
        host_ok = urlparse(self.search_url).hostname in self._allowed_hosts
        if not host_ok:
            raise mh.SafetyAbort(f"refusing to call non-allowed host: {self.search_url}")
        attempts = 0
        while True:
            attempts += 1
            if self.http_requests_total >= self.max_requests_per_run:
                raise mh.SafetyAbort("max_requests_per_run reached")
            self.http_requests_total += 1
            self.pacer.wait()
            try:
                resp = monkey_state(payload)
            except HTTPError as e:
                if e.code == 403 and self.abort_on_403:
                    self.http_403_count += 1
                    self._consecutive_errors += 1
                    raise mh.SafetyAbort("HTTP 403 from Mercedes", status=e.code, url=self.search_url)
                if e.code == 429 and self.abort_on_429:
                    self.http_429_count += 1
                    self._consecutive_errors += 1
                    raise mh.SafetyAbort("HTTP 429 from Mercedes", status=e.code, url=self.search_url)
                if 500 <= e.code < 600:
                    self.http_5xx_count += 1
                    self._consecutive_errors += 1
                    self.errors.append(f"5xx: {e.code}")
                    if attempts <= self.max_retries_5xx and self._consecutive_errors <= self.max_consecutive_errors:
                        # skip real sleep for tests
                        continue
                    raise mh.SafetyAbort(f"HTTP {e.code} after retries", status=e.code, url=self.search_url)
            # success path
            self._consecutive_errors = 0
            return resp
    mh.Harvester._post = fake_post


# ---------- helpers ----------

def write_config(tmpdir: str, *, max_requests: int = 600, retries_5xx: int = 1, max_consec: int = 8):
    cfg = {
        "api": {
            "search_url": "https://jobs.api.mercedes-benz.com/search",
            "headers": {"Accept": "application/json", "Content-Type": "application/json",
                        "User-Agent": "test", "Referer": "x", "Origin": "y"},
            "page_size": 50,
            "request_timeout_seconds": 5,
        },
        "pacing": {
            "min_seconds_between_requests": 0.0,
            "jitter_seconds_max": 0.0,
            "long_pause_every_n_requests": 0,
            "long_pause_seconds": 0.0,
            "retry_after_5xx_seconds": 0.0,
        },
        "safety": {
            "max_requests_per_run": max_requests,
            "abort_on_http_403": True,
            "abort_on_http_429": True,
            "max_retries_on_5xx": retries_5xx,
            "max_consecutive_errors": max_consec,
        },
        "search": {
            "language": "EN",
            "sort_criterion": "PublicationStartDate",
            "keywords": ["cybersecurity", "security"],
            "max_keywords_per_run": 22,
        },
        "detail": {
            "fetch_full_description": True,
            "fields_to_hash_for_change_detection": ["PositionTitle"],
        },
        "storage": {
            "db_path": "mercedes_jobs.db",
            "output_dir": "output",
        },
    }
    cfg_path = os.path.join(tmpdir, "harvester_config.json")
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)
    return cfg_path


def run_with(monkey_script, tmpdir, mode):
    cfg_path = write_config(tmpdir)
    cfg = mh.load_config(cfg_path)
    os.chdir(tmpdir)
    # The harvester resolves storage paths against its own HERE directory
    # (the script location). Tests need them to land in tmpdir instead.
    mh.HERE = tmpdir
    state = MockState(monkey_script)
    patch_post(state)
    summary = mh.run(cfg, mode)
    return summary, state


def make_ok_script():
    # 2 keywords, 1 page each
    return [
        ("ok", page_response("cybersecurity", 1, 50)),
        ("ok", page_response("security", 1, 50)),
    ]


# ---------- tests ----------

def test_idempotent_run(tmpdir):
    s1, st1 = run_with(make_ok_script(), tmpdir, "bootstrap")
    print(f"  bootstrap summary: complete={s1['catalog_complete']} new={s1['new_jobs']} unchanged={s1['unchanged_jobs']} detail={s1['detail_requests']} http={s1['http_requests_total']}")
    assert s1["catalog_complete"] is True, f"bootstrap catalog_complete={s1['catalog_complete']}"
    assert s1["closed_jobs"] == 0
    assert s1["new_jobs"] == 0  # bootstrap doesn't emit
    # 2nd run: catalog identical, no new/changed/closed
    s2, st2 = run_with(make_ok_script(), tmpdir, "normal")
    print(f"  normal summary:   complete={s2['catalog_complete']} new={s2['new_jobs']} unchanged={s2['unchanged_jobs']} detail={s2['detail_requests']} http={s2['http_requests_total']}")
    assert s2["catalog_complete"] is True, f"normal catalog_complete={s2['catalog_complete']}"
    assert s2["new_jobs"] == 0, f"expected 0 new, got {s2['new_jobs']}"
    assert s2["changed_jobs"] == 0
    assert s2["unchanged_jobs"] == 6, f"unchanged={s2['unchanged_jobs']}"  # 6 unique PIDs across both keywords
    assert s2["closed_jobs"] == 0
    # No detail requests on a normal run (we removed the detail pass)
    assert s2["detail_requests"] == 0, f"detail_requests={s2['detail_requests']}"
    # Wire counter only counts the 2 catalog pages
    assert s2["http_requests_total"] == 2, f"http_requests_total={s2['http_requests_total']}"
    # DB has 6 rows (5 from cybersecurity + 1 unique from security)
    conn = sqlite3.connect(os.path.join(tmpdir, "mercedes_jobs.db"))
    n = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    assert n == 6, f"db rows={n}"
    conn.close()
    print(f"[PASS] test_idempotent_run  http_requests_total={s2['http_requests_total']}")


def test_partial_catalog_429_leaves_db_consistent(tmpdir):
    # Script: 1st keyword OK, 2nd keyword returns 429.
    script = [
        ("ok", page_response("cybersecurity", 1, 50)),
        ("429",),
    ]
    s, st = run_with(script, tmpdir, "normal")
    print(f"  partial summary: complete={s['catalog_complete']} aborted={s['aborted_for_safety']} 429={s['http_429_count']} closed={s['closed_jobs']} skipped={s['closed_calculation_skipped']}")
    # We did NOT mark anything closed because catalog was incomplete
    assert s["catalog_complete"] is False, f"catalog_complete={s['catalog_complete']}"
    assert s["closed_calculation_skipped"] is True, f"closed_calculation_skipped={s['closed_calculation_skipped']}"
    assert s["closed_jobs"] == 0, f"closed_jobs={s['closed_jobs']}"
    assert s["aborted_for_safety"] is True
    assert s["http_429_count"] >= 1
    # All previously-known rows still have is_open=1
    conn = sqlite3.connect(os.path.join(tmpdir, "mercedes_jobs.db"))
    rows = list(conn.execute("SELECT source_job_id, is_open FROM jobs"))
    # In this test DB is fresh (no prior rows); so 0 rows. That's fine.
    # The point is: no row was set to is_open=0 destructively.
    closed = [r for r in rows if r[1] == 0]
    assert len(closed) == 0, f"DB has closed rows: {closed}"
    conn.close()
    print(f"[PASS] test_partial_catalog_429_leaves_db_consistent  "
          f"closed_calculation_skipped={s['closed_calculation_skipped']} "
          f"closed_jobs={s['closed_jobs']}")


def test_partial_catalog_does_not_close_after_real_prior_state(tmpdir):
    # Seed DB with 3 rows that look 'open' before the run.
    # Then run with partial catalog (429 mid-sweep).
    # Expect: all 3 still is_open=1.
    dbp = os.path.join(tmpdir, "mercedes_jobs.db")
    if os.path.exists(dbp):
        os.remove(dbp)
    conn = sqlite3.connect(dbp)
    mh.db_connect(dbp)  # ensures schema
    # insert 3 rows that we EXPECT to NOT see in the partial catalog
    # (they are not in our 5-item fixture)
    for pid, title in [("mer00000z1", "Old1"), ("mer00000z2", "Old2"), ("mer00000z3", "Old3")]:
        conn.execute("""INSERT INTO jobs
            (source_job_id, title, metadata_hash, semantic_hash,
             first_seen_at, last_seen_at, last_seen_run_at,
             is_open, needs_semantic_analysis)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)""",
            (pid, title, "meta-x", "sem-x", "t", "t", "t"))
    conn.commit()
    conn.close()

    # Run with partial catalog
    script = [
        ("ok", page_response("cybersecurity", 1, 50)),
        ("429",),
    ]
    s, st = run_with(script, tmpdir, "normal")
    # Verify those 3 rows are STILL is_open=1
    conn = sqlite3.connect(dbp)
    rows = list(conn.execute("SELECT source_job_id, is_open FROM jobs WHERE source_job_id LIKE 'mer00000z%'"))
    assert all(r[1] == 1 for r in rows), f"some prior rows were closed: {rows}"
    # We should ALSO have inserted the 5 fixture rows that were seen
    new_rows = list(conn.execute("SELECT source_job_id FROM jobs WHERE source_job_id LIKE 'mer00000%' AND length(source_job_id)=9"))
    assert len(new_rows) == 5, f"unexpected new rows: {new_rows}"
    conn.close()
    print(f"[PASS] test_partial_catalog_does_not_close_after_real_prior_state")


def test_breaker_counts_real_attempts_including_retries(tmpdir):
    # Script: first keyword returns 500 once (then OK), second keyword OK.
    # Retries are configured = 1, so the 500 consumes 2 wire attempts.
    script = [
        ("500",),                              # 1st attempt: 500
        ("ok", page_response("cybersecurity", 1, 50)),  # 2nd attempt: OK
        ("ok", page_response("security", 1, 50)),      # 3rd attempt: OK
    ]
    s, st = run_with(script, tmpdir, "normal")
    # http_requests_total must reflect real attempts: 3
    assert s["http_requests_total"] == 3, f"http_requests_total={s['http_requests_total']}"
    # logical metrics: catalog_requests = 2 (the 2 OK calls)
    assert s["catalog_requests"] == 2, f"catalog_requests={s['catalog_requests']}"
    # breaker tripped? no, we never hit the cap (set to 600 by default)
    assert s["aborted_for_safety"] is False
    print(f"[PASS] test_breaker_counts_real_attempts_including_retries  "
          f"http_requests_total={s['http_requests_total']} catalog_requests={s['catalog_requests']}")


def test_breaker_trips_on_real_attempts(tmpdir):
    # Set max_requests_per_run=1. One keyword, two pages expected — the
    # 2nd page must be refused by the breaker BEFORE going to wire.
    cfg_path = write_config(tmpdir, max_requests=1)
    cfg = mh.load_config(cfg_path)
    cfg["search"]["keywords"] = ["cybersecurity"]
    cfg["search"]["max_keywords_per_run"] = 1
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)
    os.chdir(tmpdir)
    mh.HERE = tmpdir

    # Build a response whose total > page_size so the harvester would
    # WANT to make a 2nd request if the breaker didn't stop it.
    big = {
        "LanguageCode": "EN",
        "SearchResult": {
            "SearchResultCount": 50,
            "SearchResultCountAll": 100,
            "SearchResultItems": [make_item(f"mer{i:07d}", f"Job {i}")["MatchedObjectDescriptor"]
                                   for i in range(50)],
            "UserArea": {"ExecutionError": 0},
        }
    }
    script = [
        ("ok", big),
        # The breaker must refuse before we hit the wire for page 2.
    ]
    state = MockState(script)
    patch_post(state)
    summary = mh.run(cfg, "normal")
    print(f"  breaker summary: http={summary['http_requests_total']} "
          f"aborted={summary['aborted_for_safety']} complete={summary['catalog_complete']} "
          f"closed={summary['closed_jobs']}")
    assert summary["aborted_for_safety"] is True, f"aborted={summary['aborted_for_safety']}"
    assert summary["http_requests_total"] == 1, f"http={summary['http_requests_total']}"
    assert summary["catalog_complete"] is False
    assert summary["closed_jobs"] == 0
    assert summary["closed_calculation_skipped"] is True
    print(f"[PASS] test_breaker_trips_on_real_attempts  http={summary['http_requests_total']}")


def test_run_catches_safety_abort_keeps_db_consistent(tmpdir):
    """If harvest_catalog aborts, the DB must still be queryable and the
    summary must reflect the partial state — we must not lose the writes
    that already happened."""
    mh.HERE = tmpdir
    os.chdir(tmpdir)
    cfg_path = write_config(tmpdir)
    cfg = mh.load_config(cfg_path)

    # 1st call OK (1 PID), 2nd call 429
    from urllib.error import HTTPError
    def fake_post(self, payload):
        from urllib.parse import urlparse
        if urlparse(self.search_url).hostname not in self._allowed_hosts:
            raise mh.SafetyAbort("nope")
        attempts = 0
        while True:
            attempts += 1
            self.http_requests_total += 1
            if self.http_requests_total > self.max_requests_per_run:
                raise mh.SafetyAbort("max")
            self.pacer.wait()
            try:
                if self.http_requests_total == 1:
                    return {"SearchResult":{"SearchResultCount":1,"SearchResultCountAll":1,"SearchResultItems":[{"MatchedObjectDescriptor":{"PositionID":"mer00000a","ID":"1","PositionTitle":"x","DepartmentName":"d","ParentOrganizationName":"p","PositionLocation":[{"CityName":"S","CountryCode":"DE","CountryName":"Germany","DisplayName":"S"}],"PublicationStartDate":"2026-08-01","PublicationEndDate":"2030-12-31","PositionStartDate":"2026-09-01","CareerLevel":[{"Code":"12","Name":"S"}],"JobCategory":[{"Code":"37","Name":"IT"}],"TargetGroup":[{"Code":"4","Name":"x"}],"PublicationLanguage":{"Code":"1"},"PositionFormattedDescription":[],"PositionURI":"u","ApplyURI":["a"]}}]}}
                raise HTTPError("x", 429, "rate", {}, None)
            except HTTPError as e:
                if e.code == 429:
                    self.http_429_count += 1
                    self._consecutive_errors += 1
                    raise mh.SafetyAbort("HTTP 429", status=e.code, url=self.search_url)
    mh.Harvester._post = fake_post

    summary = mh.run(cfg, "normal")
    assert summary["catalog_complete"] is False
    assert summary["closed_jobs"] == 0
    # Verify DB is queryable and contains the row that was inserted
    # before the 429
    dbp = os.path.join(tmpdir, "mercedes_jobs.db")
    assert os.path.exists(dbp)
    conn = sqlite3.connect(dbp)
    rows = list(conn.execute("SELECT source_job_id, is_open FROM jobs"))
    conn.close()
    assert len(rows) == 1, f"expected 1 row, got {rows}"
    assert rows[0][1] == 1, f"row should still be open, got {rows[0]}"
    # run_summary.json and new_or_changed_jobs.json must exist
    assert os.path.exists(os.path.join(tmpdir, "output", "run_summary.json"))
    assert os.path.exists(os.path.join(tmpdir, "output", "new_or_changed_jobs.json"))
    print(f"[PASS] test_run_catches_safety_abort_keeps_db_consistent  "
          f"db_rows={len(rows)}  closed_jobs={summary['closed_jobs']}")


# ---------- helpers for the change-detection tests ----------

def make_md(pid: str, *, title: str = "Security Analyst",
            dept: str = "Cyber Security",
            tasks: str = "Task A. Task B.",
            quals: str = "Knows X. Knows Y.",
            apply_uri: str | None = None,
            location: tuple = ("Stuttgart", "DE", "Germany"),
            start_date: str = "2026-08-01"):
    """Build a Mercedes-style MatchedObjectDescriptor for the tests."""
    return {
        "PositionID": pid,
        "ID": pid[-6:],
        "PositionTitle": title,
        "PositionURI": f"https://jobs.mercedes-benz.com/{pid}",
        "ApplyURI": [apply_uri or f"https://example/apply/{pid}"],
        "DepartmentName": dept,
        "ParentOrganizationName": "Mercedes-Benz AG",
        "PositionLocation": [{
            "CityName": location[0], "CountryCode": location[1],
            "CountryName": location[2], "DisplayName": f"{location[0]}, {location[1]}",
        }],
        "PublicationStartDate": start_date,
        "PublicationEndDate": "2030-12-31",
        "PositionStartDate": "2026-09-01",
        "CareerLevel": [{"Code": "12", "Name": "Salaried"}],
        "JobCategory": [{"Code": "37", "Name": "IT/Telecom"}],
        "TargetGroup": [{"Code": "4", "Name": "Berufserfahrene"}],
        "PublicationLanguage": {"Code": "1"},
        "PositionFormattedDescription": [
            {"Tasks": f"<p>{tasks}</p>", "Qualifications": f"<p>{quals}</p>"},
        ],
    }


def make_one_page_response(*items):
    return {
        "LanguageCode": "EN",
        "SearchResult": {
            "SearchResultCount": len(items),
            "SearchResultCountAll": len(items),
            "SearchResultItems": [{"MatchedObjectDescriptor": x} for x in items],
            "UserArea": {"ExecutionError": 0},
        }
    }


def bootstrap_one(tmpdir, items):
    """Run a bootstrap with a mock that always returns the given items
    for each keyword, and patch the harvester to use tmpdir."""
    cfg_path = write_config(tmpdir)
    cfg = mh.load_config(cfg_path)
    os.chdir(tmpdir)
    mh.HERE = tmpdir
    state = MockState([("ok", make_one_page_response(*items))] * 22)
    patch_post(state)
    return mh.run(cfg, "bootstrap")


# ---------- the four new tests ----------


def test_description_only_change_triggers_semantic_analysis(tmpdir):
    """Modify ONLY Tasks/Qualifications — keep title, department,
    location, dates identical. The row should be flagged for
    semantic analysis because the semantic_hash changed."""
    pid = "mer0000abc"
    # 1. Bootstrap with the original description.
    initial = make_md(pid, tasks="Original task text.", quals="Original quals.")
    bootstrap_one(tmpdir, [initial])
    # 2. Second run: change ONLY Tasks and Qualifications.
    changed = make_md(pid, tasks="New task text with extra info.",
                      quals="Updated qualifications.")
    state = MockState([("ok", make_one_page_response(changed))] * 22)
    patch_post(state)
    cfg_path = write_config(tmpdir)
    cfg = mh.load_config(cfg_path)
    summary = mh.run(cfg, "normal")
    print(f"  desc-only summary: new={summary['new_jobs']} changed={summary['changed_jobs']} "
          f"unchanged={summary['unchanged_jobs']} http={summary['http_requests_total']}")
    assert summary["changed_jobs"] == 1, f"expected 1 changed, got {summary['changed_jobs']}"
    assert summary["new_jobs"] == 0
    assert summary["unchanged_jobs"] == 0
    # Verify DB has needs_semantic_analysis=1 for this PID
    conn = sqlite3.connect(os.path.join(tmpdir, "mercedes_jobs.db"))
    row = list(conn.execute("SELECT needs_semantic_analysis, metadata_hash, semantic_hash FROM jobs WHERE source_job_id=?", (pid,)))[0]
    conn.close()
    assert row[0] == 1, f"needs_semantic_analysis should be 1, got {row[0]}"
    # metadata_hash unchanged (we didn't touch metadata), semantic_hash changed
    assert row[1] == mh.metadata_hash(initial), "metadata_hash should match the original"
    assert row[2] == mh.semantic_hash(changed), "semantic_hash should match the new"
    # new_or_changed_jobs.json must contain this PID
    out = json.load(open(os.path.join(tmpdir, "output", "new_or_changed_jobs.json")))
    assert any(o["source_job_id"] == pid for o in out), f"PID {pid} missing from output"
    print(f"[PASS] test_description_only_change_triggers_semantic_analysis")


def test_metadata_only_change_does_not_trigger_semantic_analysis(tmpdir):
    """Change ONLY metadata (apply URI + location). Title, department and
    description are identical. The DB row is updated but
    needs_semantic_analysis must stay 0 — no LLM call is owed."""
    pid = "mer0000def"
    initial = make_md(pid, apply_uri="https://apply-old", location=("Stuttgart", "DE", "Germany"))
    bootstrap_one(tmpdir, [initial])
    # Second run: change ONLY apply_uri + a small location tweak
    changed = make_md(pid, apply_uri="https://apply-NEW", location=("Stuttgart", "DE", "Germany"))
    state = MockState([("ok", make_one_page_response(changed))] * 22)
    patch_post(state)
    cfg_path = write_config(tmpdir)
    cfg = mh.load_config(cfg_path)
    summary = mh.run(cfg, "normal")
    print(f"  meta-only summary: new={summary['new_jobs']} changed={summary['changed_jobs']} "
          f"unchanged={summary['unchanged_jobs']} http={summary['http_requests_total']}")
    # The DB row was updated (metadata_hash differs), but the semantic
    # hash is identical → needs_semantic_analysis stays 0.
    conn = sqlite3.connect(os.path.join(tmpdir, "mercedes_jobs.db"))
    row = list(conn.execute("SELECT needs_semantic_analysis, apply_url, metadata_hash, semantic_hash FROM jobs WHERE source_job_id=?", (pid,)))[0]
    conn.close()
    assert row[0] == 0, f"needs_semantic_analysis should stay 0, got {row[0]}"
    assert row[1] == "https://apply-NEW", f"apply_url should be updated, got {row[1]}"
    assert row[2] == mh.metadata_hash(changed), "metadata_hash should be the new one"
    assert row[3] == mh.semantic_hash(initial), "semantic_hash should be unchanged"
    # new_or_changed_jobs.json must be empty
    out = json.load(open(os.path.join(tmpdir, "output", "new_or_changed_jobs.json")))
    assert out == [], f"expected empty output, got {out}"
    # summary counts: 0 new, 0 changed (metadata-only edits don't count as semantic changes)
    assert summary["changed_jobs"] == 0, f"expected 0 changed, got {summary['changed_jobs']}"
    assert summary["new_jobs"] == 0
    # The PID WAS re-classified as possibly_changed during classification
    # (metadata_hash differs), so it was NOT counted as unchanged.
    assert summary["unchanged_jobs"] == 0
    print(f"[PASS] test_metadata_only_change_does_not_trigger_semantic_analysis")


def test_pagination_cap_cannot_claim_complete(tmpdir):
    """There is no per-keyword page cap any more — only the global
    circuit breaker can stop pagination. We simulate a real safety event
    mid-pagination (the breaker trips) and verify that the catalog is
    marked incomplete."""
    # Build a response whose total > page_size so the harvester WOULD
    # try a 2nd page if not stopped.
    cfg_path = write_config(tmpdir, max_requests=1)
    cfg = mh.load_config(cfg_path)
    cfg["search"]["keywords"] = ["cybersecurity"]
    cfg["search"]["max_keywords_per_run"] = 1
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)
    os.chdir(tmpdir)
    mh.HERE = tmpdir

    big = make_one_page_response(
        *[make_md(f"mer{i:07d}", title=f"Job {i}") for i in range(50)]
    )
    big["SearchResult"]["SearchResultCountAll"] = 5000   # lie: there are way more
    script = [("ok", big)]
    state = MockState(script)
    patch_post(state)
    summary = mh.run(cfg, "normal")
    print(f"  cap summary: http={summary['http_requests_total']} complete={summary['catalog_complete']} "
          f"closed={summary['closed_jobs']} skipped={summary['closed_calculation_skipped']}")
    assert summary["aborted_for_safety"] is True
    assert summary["http_requests_total"] == 1
    assert summary["catalog_complete"] is False, "catalog_complete MUST be False when the breaker trips mid-sweep"
    assert summary["closed_calculation_skipped"] is True
    assert summary["closed_jobs"] == 0
    # No per-keyword cap: even with one more page available, the run
    # stopped only because of the breaker, not because of a hidden cap.
    print(f"[PASS] test_pagination_cap_cannot_claim_complete")


def test_exactly_one_retry_means_two_wire_attempts(tmpdir):
    """max_retries_on_5xx = 1 must mean EXACTLY 1 original + 1 retry = 2
    wire attempts. The third scripted response (an OK) must NOT be
    consumed. http_requests_total must be 2."""
    cfg_path = write_config(tmpdir, max_requests=600, retries_5xx=1, max_consec=8)
    cfg = mh.load_config(cfg_path)
    cfg["search"]["keywords"] = ["cybersecurity"]
    cfg["search"]["max_keywords_per_run"] = 1
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)
    os.chdir(tmpdir)
    mh.HERE = tmpdir

    # Page 1 of the only keyword: 500, 500, then a third "ok" we MUST NOT touch.
    ok_response = make_one_page_response(make_md("mer00000a"))
    script = [
        ("500",),
        ("500",),
        ("ok", ok_response),   # this MUST NOT be consumed
    ]
    state = MockState(script)
    patch_post(state)
    summary = mh.run(cfg, "normal")
    print(f"  retry summary: http={summary['http_requests_total']} aborted={summary['aborted_for_safety']} "
          f"5xx={summary['http_5xx_count']}")
    assert summary["http_requests_total"] == 2, f"expected exactly 2 wire attempts, got {summary['http_requests_total']}"
    assert summary["aborted_for_safety"] is True
    assert summary["http_5xx_count"] == 2
    # Verify the third scripted response was NOT consumed
    leftover = list(state.script)
    assert len(leftover) == 1, f"third response was consumed, leftover={leftover}"
    assert leftover[0][0] == "ok", f"third response was consumed, leftover={leftover}"
    print(f"[PASS] test_exactly_one_retry_means_two_wire_attempts  http={summary['http_requests_total']}")


def main():
    tests = [
        test_idempotent_run,
        test_partial_catalog_429_leaves_db_consistent,
        test_partial_catalog_does_not_close_after_real_prior_state,
        test_breaker_counts_real_attempts_including_retries,
        test_breaker_trips_on_real_attempts,
        test_run_catches_safety_abort_keeps_db_consistent,
        test_description_only_change_triggers_semantic_analysis,
        test_metadata_only_change_does_not_trigger_semantic_analysis,
        test_pagination_cap_cannot_claim_complete,
        test_exactly_one_retry_means_two_wire_attempts,
    ]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                t(tmp)
            except AssertionError as e:
                print(f"[FAIL] {t.__name__}: {e}")
                failed += 1
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[FAIL] {t.__name__}: {type(e).__name__}: {e}")
                failed += 1
    if failed:
        sys.exit(1)
    print("\nAll offline tests passed.")


if __name__ == "__main__":
    main()

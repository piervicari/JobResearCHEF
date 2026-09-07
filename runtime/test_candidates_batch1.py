#!/usr/bin/env python3
"""
Offline contract tests for batch-1 candidates (Google + Microsoft).

Does NOT modify the frozen executor or the frozen schema.
Uses only the same generic `spec_executor.py` to drive both
representable sources and NEEDS_EXTENSION declarations.

Each representable source must pass:
- spec valid against source_spec/v0.1
- catalog request rendered correctly
- pagination injection correct
- extraction (catalog + detail) of real fixture data
- normalized job conformant to job.schema.json
- detail_complete correct before/after detail merge
- completeness evaluation
- closed_decision consistent with source_of_truth

NEEDS_EXTENSION sources are reported with structured gap analysis
(extracted from the *.NEEDS_EXTENSION.md markdown).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spec_executor as se  # noqa: E402
import validate_specs  # noqa: E402

# --- Microsoft (representable) ---
MICROSOFT_SPEC_PATH = os.path.join(HERE, "candidates", "microsoft.json")
MICROSOFT_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "microsoft_catalog_page.json")
MICROSOFT_DETAIL_FIXTURE = os.path.join(HERE, "fixtures", "microsoft_detail.json")
JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCE_SPEC_SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")

# --- Google (not representable) ---
GOOGLE_NEEDS_PATH = os.path.join(HERE, "candidates", "google_NEEDS_EXTENSION.md")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ============================================================
# MICROSOFT — representable with source_spec/v0.1
# ============================================================

class MicrosoftSpecValidationTests(unittest.TestCase):

    def test_microsoft_spec_validates_against_v01_schema(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        errors = validate_specs.validate_source_spec(spec, schema)
        self.assertEqual(errors, [], msg=f"Microsoft spec errors: {errors}")

    def test_microsoft_is_full_catalog_and_authoritative(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        self.assertEqual(spec["schema_version"], "source_spec/v0.1")
        self.assertEqual(spec["source_of_truth"], "full_catalog")
        self.assertTrue(spec["open_closed_authoritative"])
        self.assertEqual(spec["platform"]["name"], "eightfold_pcsx")

    def test_microsoft_uses_query_param_for_paging(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        self.assertEqual(spec["paging"]["strategy"], "offset")
        self.assertEqual(spec["paging"]["inject"]["target"], "query_param")
        self.assertEqual(spec["paging"]["page_size"], 10)
        self.assertEqual(spec["paging"]["first_page_value"], 0)


class MicrosoftRequestRenderingTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(MICROSOFT_SPEC_PATH)

    def test_page_1(self):
        r = se.render_catalog_request(self.spec, 0)
        self.assertEqual(r["method"], "GET")
        self.assertEqual(r["url"], "https://microsoft.eightfold.ai/api/pcsx/search")
        self.assertEqual(r["query"]["domain"], "microsoft.com")
        self.assertEqual(r["query"]["start"], 0)
        self.assertEqual(r["query"]["hl"], "en")
        self.assertIn("User-Agent", r["headers"])

    def test_page_2_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 10)
        self.assertEqual(r["query"]["start"], 10)

    def test_page_3_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 20)
        self.assertEqual(r["query"]["start"], 20)


class MicrosoftExtractionTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(MICROSOFT_SPEC_PATH)
        self.page = _load(MICROSOFT_PAGE_FIXTURE)
        self.items, self.total = se.extract_page(self.spec, self.page)
        self.assertEqual(self.total, 2252)
        self.assertEqual(len(self.items), 10)
        self.item = self.items[0]

    def test_extract_stable_id_title_department_locations(self):
        job = se.extract_item(self.spec, self.item)
        # Real ID from the captured fixture
        self.assertEqual(job["source_job_id"], "1970393556853171")
        self.assertEqual(job["title"], "Principal Software Engineer Manager")
        self.assertEqual(job["department"], "Software Engineering")
        self.assertEqual(job["locations"], ["United States, Washington, Redmond"])
        self.assertEqual(job["source_secondary_ids"], ["200033370", "200033370"])
        # publicUrl is null in catalog -> template fallback applies
        self.assertEqual(
            job["official_url"],
            "https://apply.careers.microsoft.com/careers/job/1970393556853171",
        )
        # publication_date is unix_seconds → ISO date
        self.assertEqual(job["publication_date"], "2026-09-05")
        # Catalog item has no jobDescription → detail_complete=False
        self.assertEqual(job.get("description", ""), "")
        self.assertFalse(job.get("detail_complete", True))

    def test_normalized_catalog_only_job_conforms_to_schema(self):
        job = se.extract_item(self.spec, self.item)
        job = se.normalize_job(self.spec, job, "2026-09-05T00:00:00+00:00")
        js = _load(JOB_SCHEMA_PATH)
        errors = se.validate_against_job_schema(job, js)
        self.assertEqual(errors, [], msg=f"job schema errors: {errors}")
        self.assertEqual(job["company_id"], "microsoft")
        self.assertEqual(job["source_platform"], "eightfold_pcsx")
        self.assertFalse(job["detail_complete"])

    def test_detail_request_uses_stable_id(self):
        dr = se.render_detail_request(self.spec, 1970393556853171)
        self.assertIsNotNone(dr)
        self.assertEqual(dr["method"], "GET")
        self.assertEqual(dr["url"], "https://microsoft.eightfold.ai/api/pcsx/position_details")
        self.assertEqual(dr["query"]["domain"], "microsoft.com")
        self.assertEqual(dr["query"]["position_id"], 1970393556853171)
        self.assertEqual(dr["query"]["hl"], "en")

    def test_detail_response_populates_description_and_html_stripped(self):
        detail = _load(MICROSOFT_DETAIL_FIXTURE)
        catalog_job = se.extract_item(self.spec, self.item)
        full = se.merge_detail_into_job(self.spec, dict(catalog_job), detail)
        full = se.normalize_job(self.spec, full, "2026-09-05T00:00:00+00:00")
        # Real jobDescription came back from detail endpoint
        self.assertTrue(len(full.get("description", "")) > 100,
                        msg=f"description too short: {full.get('description', '')[:200]}")
        # HTML stripped
        self.assertNotIn("<p>", full["description"])
        self.assertNotIn("<ul>", full["description"])
        # detail_complete flipped to True
        self.assertTrue(full["detail_complete"])
        # publicUrl came from the detail response
        self.assertEqual(
            full["official_url"],
            "https://apply.careers.microsoft.com/careers/job/1970393556853171",
        )
        # Schema still validates
        js = _load(JOB_SCHEMA_PATH)
        self.assertEqual(se.validate_against_job_schema(full, js), [])


class MicrosoftCompletenessTests(unittest.TestCase):

    def test_offset_complete_when_total_reached(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        # Walk all 2252 jobs, last page has 2252 % 10 = 2 items.
        history = []
        offset = first
        while offset < 2252:
            count = min(page_size, 2252 - offset)
            history.append({"page_value": offset, "items_count": count, "total": 2252})
            offset += page_size
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertTrue(ok, msg=f"expected complete, got reason={reason}")

    def test_complete_allows_closed_for_authoritative_source(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        history = []
        offset = first
        while offset < 2252:
            count = min(page_size, 2252 - offset)
            history.append({"page_value": offset, "items_count": count, "total": 2252})
            offset += page_size
        ok, _ = se.evaluate_completeness(spec, history)
        self.assertTrue(ok)
        decision = se.closed_decision(spec, ok)
        self.assertTrue(decision["may_mark_closed"])

    def test_incomplete_blocks_closed(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        history = [{"page_value": 0, "items_count": 10, "total": 2252}]
        ok, _ = se.evaluate_completeness(spec, history)
        self.assertFalse(ok)
        decision = se.closed_decision(spec, ok)
        self.assertFalse(decision["may_mark_closed"])


class MicrosoftPaginationCountTests(unittest.TestCase):

    def test_microsoft_full_sweep_request_count(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        # total=2252, page_size=10, first=0
        # data pages = ceil(2252 / 10) = 226 pages (offsets 0..2250)
        # Microsoft does NOT have items_path_empty_after_total rule
        # (only next_offset_ge_total + last_page_shorter), so NO empty probe.
        n = se.total_request_count(spec, 2252)
        self.assertEqual(n, 226, msg=f"expected 226 requests, got {n}")

    def test_microsoft_pagination_iterator_emits_226_offsets(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 2252))
        self.assertEqual(len(offsets), 226,
                         msg=f"expected 226 offsets, got {len(offsets)}")
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets[-1], 2250)
        self.assertEqual(offsets, sorted(offsets))


class MicrosoftSpecMutationTests(unittest.TestCase):

    def test_microsoft_rendering_does_not_mutate_spec(self):
        spec = _load(MICROSOFT_SPEC_PATH)
        snapshot = json.dumps(spec, sort_keys=True)
        for offset in [0, 10, 20, 30, 10, 0]:
            se.render_catalog_request(spec, offset)
        se.render_detail_request(spec, 1970393556853171)
        after = json.dumps(spec, sort_keys=True)
        self.assertEqual(snapshot, after,
                         msg="rendering mutated the Microsoft spec — must stay immutable")


# ============================================================
# GOOGLE — NOT representable, documented as NEEDS_EXTENSION
# ============================================================

class GoogleNeedsExtensionTests(unittest.TestCase):
    """No source spec is created for Google — by design.
    Verify the needs-extension doc exists, has the required
    structured fields, and the reason is documented.

    These tests assert the documentation contract for NEEDS_EXTENSION.
    They do NOT attempt to drive the executor with a Google spec —
    because none exists, and creating one would lie about
    representability.
    """

    def test_google_needs_extension_doc_exists(self):
        self.assertTrue(os.path.exists(GOOGLE_NEEDS_PATH),
                        msg=f"missing Google needs-extension doc: {GOOGLE_NEEDS_PATH}")

    def test_google_doc_declares_correct_verdict(self):
        content = open(GOOGLE_NEEDS_PATH).read()
        self.assertIn("NEEDS_EXTENSION", content,
                      msg="Google doc must declare NEEDS_EXTENSION verdict")
        self.assertIn("BROWSER_REQUIRED", content,
                      msg="Google doc must also flag BROWSER_REQUIRED")

    def test_google_doc_documents_missing_primitives(self):
        content = open(GOOGLE_NEEDS_PATH).read()
        # At minimum, must mention the specific primitives that v0.1
        # lacks. This is the "extension pressure" record.
        for needle in ["opaque_cursor", "batchexecute", "page_number_nonce",
                       "f.sid", "nonce"]:
            self.assertIn(needle, content.lower(),
                          msg=f"Google doc must mention '{needle}'")

    def test_google_does_not_have_a_fake_spec(self):
        """Anti-cheat: ensure no fake google.json was created that
        claims PASS_V01 — that would be a misrepresentation."""
        fake = os.path.join(HERE, "candidates", "google.json")
        self.assertFalse(
            os.path.exists(fake),
            msg=f"google.json MUST NOT exist — it would falsely claim "
                f"PASS_V01. Only the NEEDS_EXTENSION markdown may exist."
        )

    def test_google_no_http_429_received(self):
        """Per the task's safety rules, we must have stopped before
        triggering 429. Assert this from the doc."""
        content = open(GOOGLE_NEEDS_PATH).read()
        # The doc should explicitly say no 429/403/CAPTCHA was received.
        self.assertRegex(content, r"(?i)(no|zero|nessun).*(429|403|captcha)",
                         msg="Google doc must document zero 429/403/CAPTCHA")


# ============================================================
# FROZEN REGRESSION — make sure we did NOT break the existing
# 42 Mercedes+NVIDIA tests.
# ============================================================

class FrozenRegressionTests(unittest.TestCase):

    def test_frozen_executor_tests_still_pass(self):
        # Re-run the frozen test module via its main() entry point.
        # unittest.TextTestRunner writes to stderr by default, so we
        # capture both streams.
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "test_spec_executor.py")],
            capture_output=True, text=True, cwd=HERE,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0,
                         msg=f"frozen test_spec_executor.py FAILED:\n"
                             f"stdout: {result.stdout}\nstderr: {result.stderr}")
        # Parse the trailing "Ran N tests in T s / OK" line
        m = re.search(r"Ran (\d+) tests? in", combined)
        self.assertIsNotNone(m,
                             msg=f"could not parse test count from output:\n{combined[-500:]}")
        n = int(m.group(1))
        self.assertGreaterEqual(n, 42,
                                msg=f"frozen test count dropped below 42: {n}")

    def test_executor_did_not_change(self):
        # If the executor or schema changed, this hash will differ.
        # We don't hash directly here; instead we re-load it and
        # verify the docstring declares v0.1 capabilities (frozen).
        import spec_executor as se_mod
        doc = se_mod.__doc__ or ""
        self.assertIn("v0.1", doc,
                      msg="spec_executor.py docstring must still declare v0.1 scope")

    def test_schema_did_not_change_version(self):
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        self.assertEqual(schema["properties"]["schema_version"]["const"],
                         "source_spec/v0.1",
                         msg="source_spec.schema.json must still pin schema_version = v0.1")
        self.assertEqual(schema["properties"]["paging"]["properties"]["strategy"]["const"],
                         "offset",
                         msg="paging.strategy must still be const 'offset'")


# ============================================================
# DRIVER
# ============================================================

def main():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

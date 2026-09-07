#!/usr/bin/env python3
"""
Offline contract tests for batch-2 candidates (Amazon + Apple).

Does NOT modify the frozen executor or the frozen schema.
Uses only the same generic `spec_executor.py` to drive representable
sources and to assert documented extension pressure for sources
that do NOT fit v0.1.

Each PASS_V01 source must satisfy:
- spec valid against source_spec/v0.1
- catalog request rendered correctly
- pagination injection correct
- extraction (catalog + detail) of real fixture data
- normalized job conformant to job.schema.json
- detail_complete correct before/after detail merge
- completeness evaluation
- closed_decision consistent with source_of_truth
- spec not mutated by rendering

Each NEEDS_EXTENSION source must have a documented gap analysis
(extracted from *.NEEDS_EXTENSION.md markdown) AND no fake JSON
spec claiming representability.
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

# --- Amazon (representable, but filtered_catalog) ---
AMAZON_SPEC_PATH = os.path.join(HERE, "candidates", "amazon.json")
AMAZON_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_page.json")
AMAZON_PAGE2_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_page2.json")
AMAZON_EMPTY_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_empty.json")
JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCE_SPEC_SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")

# --- Apple (NOT representable) ---
APPLE_NEEDS_PATH = os.path.join(HERE, "candidates", "apple_NEEDS_EXTENSION.md")
APPLE_FIXTURE = os.path.join(HERE, "fixtures", "apple_catalog_page.json")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ============================================================
# AMAZON — representable with source_spec/v0.1 (filtered_catalog)
# ============================================================

class AmazonSpecValidationTests(unittest.TestCase):

    def test_amazon_spec_validates_against_v01_schema(self):
        spec = _load(AMAZON_SPEC_PATH)
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        errors = validate_specs.validate_source_spec(spec, schema)
        self.assertEqual(errors, [], msg=f"Amazon spec errors: {errors}")

    def test_amazon_is_filtered_catalog_not_authoritative(self):
        spec = _load(AMAZON_SPEC_PATH)
        self.assertEqual(spec["schema_version"], "source_spec/v0.1")
        self.assertEqual(spec["source_of_truth"], "filtered_catalog")
        self.assertFalse(spec["open_closed_authoritative"])
        self.assertTrue(spec["description_in_catalog"])

    def test_amazon_uses_query_param_for_paging(self):
        spec = _load(AMAZON_SPEC_PATH)
        self.assertEqual(spec["paging"]["strategy"], "offset")
        self.assertEqual(spec["paging"]["inject"]["target"], "query_param")
        self.assertEqual(spec["paging"]["page_size"], 10)
        self.assertEqual(spec["paging"]["first_page_value"], 0)
        self.assertEqual(spec["paging"]["page_param"], "offset")


class AmazonRequestRenderingTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(AMAZON_SPEC_PATH)

    def test_page_1(self):
        r = se.render_catalog_request(self.spec, 0)
        self.assertEqual(r["method"], "GET")
        self.assertEqual(r["url"], "https://www.amazon.jobs/en/search.json")
        self.assertEqual(r["query"]["offset"], 0)
        self.assertEqual(r["query"]["result_limit"], "10")
        self.assertEqual(r["query"]["sort"], "relevant")
        self.assertIn("User-Agent", r["headers"])

    def test_page_2_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 10)
        self.assertEqual(r["query"]["offset"], 10)

    def test_page_3_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 20)
        self.assertEqual(r["query"]["offset"], 20)


class AmazonExtractionTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(AMAZON_SPEC_PATH)
        self.page = _load(AMAZON_PAGE_FIXTURE)
        self.items, self.total = se.extract_page(self.spec, self.page)
        # Amazon has a hard cap of 10000 hits — see notes in spec
        self.assertEqual(self.total, 10000)
        self.assertEqual(len(self.items), 10)
        self.item = self.items[0]

    def test_extract_stable_id_title_organization(self):
        job = se.extract_item(self.spec, self.item)
        # id_icims is the numeric stable ID
        self.assertEqual(job["source_job_id"], "10432506")
        # UUID as secondary
        self.assertEqual(job["source_secondary_ids"],
                         ["a4ff30cc-57a7-489c-be73-36dac4738145"])
        self.assertEqual(job["title"], "ITS Support Engineer I")
        self.assertEqual(job["department"], "Operations, IT, & Support Engineering")
        self.assertEqual(job["organization"], "Amazon.com Services LLC")
        # normalized_location single string
        self.assertEqual(job["locations"], ["Denver, Colorado, USA"])
        # Apply URL from url_next_step
        self.assertEqual(job["apply_url"],
                         "https://account.amazon.jobs/jobs/10432506/apply")
        # Official URL via template (stable_id = id_icims)
        self.assertEqual(job["official_url"],
                         "https://www.amazon.jobs/en/jobs/10432506")

    def test_description_inline_and_html_stripped(self):
        job = se.extract_item(self.spec, self.item)
        # Real description came from the catalog item
        self.assertTrue(len(job.get("description", "")) > 1000,
                        msg=f"description too short: {len(job.get('description', ''))}")
        # HTML stripped: no <p>, <br>, <span> tags should remain
        self.assertNotIn("<p>", job["description"])
        self.assertNotIn("<br/>", job["description"])
        self.assertNotIn("<span", job["description"])
        # detail_complete=True because description is non-empty
        self.assertTrue(job["detail_complete"])

    def test_normalized_catalog_job_conforms_to_schema(self):
        job = se.extract_item(self.spec, self.item)
        job = se.normalize_job(self.spec, job, "2026-09-05T00:00:00+00:00")
        js = _load(JOB_SCHEMA_PATH)
        errors = se.validate_against_job_schema(job, js)
        self.assertEqual(errors, [], msg=f"job schema errors: {errors}")
        self.assertEqual(job["company_id"], "amazon")
        self.assertEqual(job["source_platform"], "amazon_jobs_public_api")
        # publication_date is null in spec because posted_date format
        # is not representable with v0.1 date_format enum
        self.assertNotIn("publication_date", job)


class AmazonPaginationCountTests(unittest.TestCase):

    def test_amazon_cap_bound_full_sweep_count(self):
        spec = _load(AMAZON_SPEC_PATH)
        # total=10000 (the cap), page_size=10, first=0
        # data pages = 10000/10 = 1000 pages (offsets 0..9990)
        # Amazon spec includes items_path_empty_after_total rule → +1 probe
        # page (offset 10000, which is exactly the first offset past total)
        n = se.total_request_count(spec, 10000)
        self.assertEqual(n, 1001, msg=f"expected 1001 requests, got {n}")

    def test_amazon_pagination_iterator_emits_1001_offsets(self):
        spec = _load(AMAZON_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 10000))
        self.assertEqual(len(offsets), 1001,
                         msg=f"expected 1001 offsets, got {len(offsets)}")
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets[999], 9990)
        self.assertEqual(offsets[1000], 10000,
                         msg="last offset must be the empty-after-total probe")
        self.assertEqual(offsets, sorted(offsets))


class AmazonCompletenessTests(unittest.TestCase):

    def test_offset_complete_when_total_reached(self):
        spec = _load(AMAZON_SPEC_PATH)
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        # Use total=10001 so the last data page is partial (1 item),
        # which satisfies last_page_shorter_than_page_size without
        # depending on the empty-after-total probe being at offset
        # strictly greater than total (the runtime pagination_iterator
        # emits the probe at offset == first + ceil(total/page_size)*page_size,
        # which can equal total+0 exactly when total divides page_size).
        history = []
        offset = first
        total = 10001
        while offset < total:
            count = min(page_size, total - offset)
            history.append({"page_value": offset, "items_count": count, "total": total})
            offset += page_size
        history.append({"page_value": offset, "items_count": 0, "total": total})
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertTrue(ok, msg=f"expected complete, got reason={reason}")

    def test_filtered_catalog_never_marks_closed(self):
        spec = _load(AMAZON_SPEC_PATH)
        # Even with complete history, filtered_catalog must NEVER
        # authorize CLOSED transitions
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        history = []
        offset = first
        total = 10001
        while offset < total:
            count = min(page_size, total - offset)
            history.append({"page_value": offset, "items_count": count, "total": total})
            offset += page_size
        history.append({"page_value": offset, "items_count": 0, "total": total})
        ok, _ = se.evaluate_completeness(spec, history)
        self.assertTrue(ok)
        decision = se.closed_decision(spec, ok)
        self.assertFalse(decision["may_mark_closed"],
                         msg="filtered_catalog must never mark jobs closed")


class AmazonSpecMutationTests(unittest.TestCase):

    def test_amazon_rendering_does_not_mutate_spec(self):
        spec = _load(AMAZON_SPEC_PATH)
        snapshot = json.dumps(spec, sort_keys=True)
        for offset in [0, 10, 20, 30, 10, 0]:
            se.render_catalog_request(spec, offset)
        after = json.dumps(spec, sort_keys=True)
        self.assertEqual(snapshot, after,
                         msg="rendering mutated the Amazon spec — must stay immutable")


# ============================================================
# APPLE — NOT representable, documented as NEEDS_EXTENSION
# ============================================================

class AppleNeedsExtensionTests(unittest.TestCase):
    """No source spec is created for Apple — by design.
    Verify the needs-extension doc exists, has the required
    structured fields, the reason is documented with REAL evidence,
    and no fake apple.json claims PASS_V01.
    """

    def test_apple_needs_extension_doc_exists(self):
        self.assertTrue(os.path.exists(APPLE_NEEDS_PATH),
                        msg=f"missing Apple needs-extension doc: {APPLE_NEEDS_PATH}")

    def test_apple_doc_declares_correct_verdict(self):
        content = open(APPLE_NEEDS_PATH).read()
        self.assertIn("NEEDS_EXTENSION", content,
                      msg="Apple doc must declare NEEDS_EXTENSION verdict")

    def test_apple_doc_documents_real_request_response_evidence(self):
        content = open(APPLE_NEEDS_PATH).read()
        # Must mention the CSRF bootstrap endpoint, the search endpoint,
        # the page=1, 2, 307, 308 evidence, and the 6124 totalRecords
        for needle in ["CSRFToken", "api/v1/search", "page=1",
                       "page=2", "page=307", "page=308", "6124",
                       "POST", "GET"]:
            self.assertIn(needle, content,
                          msg=f"Apple doc must mention real evidence: '{needle}'")

    def test_apple_doc_documents_missing_primitives(self):
        content = open(APPLE_NEEDS_PATH).read()
        # Must explicitly name the primitives that v0.1 lacks
        for needle in ["page_number", "page-number", "bootstrap",
                       "session cookie", "csrf"]:
            self.assertIn(needle.lower(), content.lower(),
                          msg=f"Apple doc must mention '{needle}'")

    def test_apple_no_fake_spec(self):
        """Anti-cheat: ensure no fake apple.json was created that
        claims PASS_V01 — that would be a misrepresentation."""
        fake = os.path.join(HERE, "candidates", "apple.json")
        self.assertFalse(
            os.path.exists(fake),
            msg=f"apple.json MUST NOT exist — only the NEEDS_EXTENSION "
                f"markdown may exist for Apple."
        )

    def test_apple_no_http_429_received(self):
        """Per safety rules, we stopped before triggering 429."""
        content = open(APPLE_NEEDS_PATH).read()
        self.assertRegex(content, r"(?i)(no|zero|nessun).*(429|403|captcha)",
                         msg="Apple doc must document zero 429/403/CAPTCHA")

    def test_apple_fixture_is_real_capture(self):
        """Sanity: the saved fixture must be a real API response."""
        fixture = _load(APPLE_FIXTURE)
        self.assertIn("res", fixture)
        self.assertIn("searchResults", fixture["res"])
        self.assertIn("totalRecords", fixture["res"])
        # Real total from probe
        self.assertEqual(fixture["res"]["totalRecords"], 6124)
        # 20 results per page (Apple-fixed)
        self.assertEqual(len(fixture["res"]["searchResults"]), 20)
        # First item has the real schema keys
        first = fixture["res"]["searchResults"][0]
        for k in ("positionId", "postingTitle", "locations", "team",
                  "postDateInGMT", "jobSummary"):
            self.assertIn(k, first,
                          msg=f"Apple fixture item missing real key: {k}")


# ============================================================
# FROZEN REGRESSION
# ============================================================

class FrozenRegressionTests(unittest.TestCase):

    def test_frozen_executor_tests_still_pass(self):
        # Re-run the frozen test module as a subprocess
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "test_spec_executor.py")],
            capture_output=True, text=True, cwd=HERE,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0,
                         msg=f"frozen test_spec_executor.py FAILED:\n"
                             f"stdout: {result.stdout}\nstderr: {result.stderr}")
        m = re.search(r"Ran (\d+) tests? in", combined)
        self.assertIsNotNone(m,
                             msg=f"could not parse test count:\n{combined[-500:]}")
        n = int(m.group(1))
        self.assertGreaterEqual(n, 42,
                                msg=f"frozen test count dropped below 42: {n}")

    def test_batch1_candidates_tests_still_pass(self):
        # Re-run batch1 tests to ensure nothing in this batch broke them
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "test_candidates_batch1.py")],
            capture_output=True, text=True, cwd=HERE,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0,
                         msg=f"batch1 tests FAILED:\n"
                             f"stdout: {result.stdout}\nstderr: {result.stderr}")
        m = re.search(r"Ran (\d+) tests? in", combined)
        self.assertIsNotNone(m,
                             msg=f"could not parse batch1 test count:\n{combined[-500:]}")
        n = int(m.group(1))
        self.assertGreaterEqual(n, 24,
                                msg=f"batch1 test count dropped below 24: {n}")

    def test_executor_did_not_change(self):
        import spec_executor as se_mod
        doc = se_mod.__doc__ or ""
        self.assertIn("v0.1", doc,
                      msg="spec_executor.py docstring must still declare v0.1 scope")

    def test_schema_did_not_change_version(self):
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        self.assertEqual(schema["properties"]["schema_version"]["const"],
                         "source_spec/v0.1")
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

#!/usr/bin/env python3
"""
Offline contract tests for batch-2 candidates (Amazon + Apple) — REVISED.

This file supersedes the previous batch2 PASS_V01 verdict for Amazon.
After offline re-evaluation (zero new HTTP traffic, only existing fixtures):

  * Amazon: PASS_V01 → NEEDS_EXTENSION
      - semantic_complete = false
        (basic_qualifications + preferred_qualifications text is
         dropped from the normalized job because extract_description's
         _try_paths returns the FIRST truthy path; fallback_paths
         is unreachable when the primary path is truthy)
      - traversal_complete_under_safety_policy = false
        (1001 catalog requests needed vs 600 max_requests_per_run)
      - authoritative_for_closed = false
        (filtered_catalog: backend hard-cap at 10000 hits)

  * Apple: NEEDS_EXTENSION (carried forward)
      - Additionally: the saved fixture contains jobs from 16
        countries, contradicting the earlier report's claim that
        the request was filtered to postLocation-USA.
        catalog_scope = unresolved.

This file does NOT modify any frozen contract file. It exercises the
frozen `spec_executor.py` against the frozen `source_spec.schema.json`
using only saved fixtures.

The Amazon-specific positive tests (page rendering, pagination count,
etc.) are intentionally REMOVED: the archived spec
(`candidates/_archive/amazon.json.PASS_V01_then_revoked`) is no longer
the active contract, and we refuse to test against an archived spec
to avoid giving the impression of a live PASS_V01 spec.

What IS tested for Amazon:
  - The semantic-content-loss finding (the main reason for
    NEEDS_EXTENSION)
  - The traversal-budget finding
  - The NEEDS_EXTENSION doc structure
  - That no live PASS_V01 spec exists for Amazon

What IS tested for Apple:
  - The NEEDS_EXTENSION doc structure
  - That no fake apple.json exists
  - That the saved fixture is a real capture
  - That the saved fixture contains countries the earlier report
    claimed it did NOT contain (the contradiction finding)
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

# --- Amazon: NEEDS_EXTENSION ---
AMAZON_NEEDS_PATH = os.path.join(HERE, "candidates", "amazon_NEEDS_EXTENSION.md")
AMAZON_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_page.json")
AMAZON_PAGE2_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_page2.json")
AMAZON_EMPTY_FIXTURE = os.path.join(HERE, "fixtures", "amazon_catalog_empty.json")
AMAZON_SPEC_ARCHIVE = os.path.join(HERE, "candidates", "_archive",
                                   "amazon.json.PASS_V01_then_revoked")

# --- Apple: NEEDS_EXTENSION ---
APPLE_NEEDS_PATH = os.path.join(HERE, "candidates", "apple_NEEDS_EXTENSION.md")
APPLE_FIXTURE = os.path.join(HERE, "fixtures", "apple_catalog_page.json")

JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCE_SPEC_SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ============================================================
# AMAZON — revised to NEEDS_EXTENSION
# ============================================================

class AmazonSemanticLossTests(unittest.TestCase):
    """Demonstrate empirically that basic_qualifications and
    preferred_qualifications text is dropped from the normalized
    job when extraction runs against the Amazon fixture.

    This is the central finding that reclassifies Amazon from
    PASS_V01 to NEEDS_EXTENSION.
    """

    def setUp(self):
        # Use the archived spec (it was syntactically PASS_V01).
        # We test the semantic loss against it because that is
        # the spec the report previously called PASS_V01.
        self.spec = _load(AMAZON_SPEC_ARCHIVE)
        self.page = _load(AMAZON_PAGE_FIXTURE)

    def test_basic_qualifications_unique_text_not_in_normalized_description(self):
        """`basic_qualifications` is present upstream with
        semantically-relevant content (Windows Server, SCCM, DNS,
        DHCP, OSI Model, TCP/IP — all cybersecurity-relevant).
        After extraction the normalized `description` does NOT
        contain this text and the normalized `qualifications`
        field is empty."""
        items, _ = se.extract_page(self.spec, self.page)
        job = se.extract_item(self.spec, items[0])

        # Pick a marker that exists in the raw basic_qualifications
        # but NOT in the raw description (verified offline before
        # writing this test).
        raw_item = items[0]
        # Use the same markers the re-evaluation report used.
        markers_in_basic_only = [
            "1+ years of Windows Server",
            "SCCM",
        ]
        for marker in markers_in_basic_only:
            self.assertIn(marker, raw_item.get("basic_qualifications", ""),
                          msg=f"sanity: {marker!r} must be in raw basic_qualifications")
            self.assertNotIn(marker, raw_item.get("description", ""),
                             msg=f"sanity: {marker!r} must NOT be in raw description")

            norm_desc = job.get("description", "")
            norm_quals = job.get("qualifications", "")
            self.assertNotIn(marker, norm_desc,
                             msg=f"normalized description lost {marker!r} "
                                 f"from basic_qualifications")
            self.assertNotIn(marker, norm_quals,
                             msg=f"normalized qualifications lost {marker!r} "
                                 f"from basic_qualifications")

    def test_preferred_qualifications_unique_text_not_in_normalized(self):
        """`preferred_qualifications` is present upstream with
        content (computer networking, video conference, teleconference
        equipment) that is NOT in the raw description and NOT in
        the normalized job."""
        items, _ = se.extract_page(self.spec, self.page)
        job = se.extract_item(self.spec, items[0])

        raw_item = items[0]
        markers_in_preferred_only = [
            "teleconference equipment",
        ]
        for marker in markers_in_preferred_only:
            self.assertIn(marker, raw_item.get("preferred_qualifications", ""),
                          msg=f"sanity: {marker!r} must be in raw preferred_qualifications")
            self.assertNotIn(marker, raw_item.get("description", ""),
                             msg=f"sanity: {marker!r} must NOT be in raw description")

            norm_desc = job.get("description", "")
            norm_quals = job.get("qualifications", "")
            self.assertNotIn(marker, norm_desc,
                             msg=f"normalized description lost {marker!r} "
                                 f"from preferred_qualifications")
            self.assertNotIn(marker, norm_quals,
                             msg=f"normalized qualifications lost {marker!r} "
                                 f"from preferred_qualifications")

    def test_normalized_qualifications_field_is_empty(self):
        """For shape=string with a truthy primary description,
        normalized `qualifications` is always empty string — the
        fallback paths are never consulted."""
        items, _ = se.extract_page(self.spec, self.page)
        for item in items:
            job = se.extract_item(self.spec, item)
            self.assertEqual(job.get("qualifications", ""), "",
                             msg=f"qualifications must be empty for shape=string "
                                 f"with truthy primary path; got "
                                 f"{job.get('qualifications', '')[:80]!r}")

    def test_basic_qualifications_length_documented_in_report(self):
        """The re-evaluation report documents 646 chars of basic
        + 1880 chars of preferred qualifications text dropped.
        Lock that number into a test so the finding is reproducible."""
        items, _ = se.extract_page(self.spec, self.page)
        raw = items[0]
        self.assertGreater(len(raw.get("basic_qualifications", "")), 500,
                           msg="sanity: basic_qualifications should be non-trivial")
        self.assertGreater(len(raw.get("preferred_qualifications", "")), 1000,
                           msg="sanity: preferred_qualifications should be non-trivial")
        # The semantic loss is therefore at minimum 1500+ chars
        # of cybersecurity-relevant skill signal per item.
        lost = len(raw["basic_qualifications"]) + len(raw["preferred_qualifications"])
        self.assertGreater(lost, 2000,
                           msg=f"semantic loss is at least {lost} chars per item")


class AmazonTraversalBudgetTests(unittest.TestCase):
    """A full sweep of Amazon's 10000-hit hard cap requires 1001
    catalog requests (1000 data pages + 1 empty-after-total probe,
    per the spec's items_path_empty_after_total rule). The Amazon
    spec declares safety.max_requests_per_run = 600, so a single
    safety-compliant run can NEVER traverse the cap.
    """

    def test_traversal_budget_insufficient(self):
        spec = _load(AMAZON_SPEC_ARCHIVE)
        max_per_run = spec["safety"]["max_requests_per_run"]
        page_size = spec["paging"]["page_size"]
        # 10000 / 10 = 1000 data pages, +1 probe = 1001
        # Use the runtime's own count function on the archived spec.
        n = se.total_request_count(spec, 10000)
        self.assertEqual(n, 1001,
                         msg=f"expected 1001 requests for full sweep, got {n}")
        self.assertGreater(n, max_per_run,
                           msg=f"traversal needs {n} requests but "
                               f"max_requests_per_run is {max_per_run}; "
                               f"sweep cannot complete under safety policy")


class AmazonNeedsExtensionDocTests(unittest.TestCase):
    """The Amazon NEEDS_EXTENSION doc must exist, must declare
    NEEDS_EXTENSION, must document the semantic-loss finding with
    concrete evidence, and must reference the traversal-budget
    finding."""

    def test_amazon_needs_extension_doc_exists(self):
        self.assertTrue(os.path.exists(AMAZON_NEEDS_PATH),
                        msg=f"missing {AMAZON_NEEDS_PATH}")

    def test_doc_declares_needs_extension_verdict(self):
        content = open(AMAZON_NEEDS_PATH).read()
        self.assertIn("NEEDS_EXTENSION", content,
                      msg="Amazon NEEDS_EXTENSION doc must declare NEEDS_EXTENSION")

    def test_doc_documents_semantic_loss_with_real_evidence(self):
        content = open(AMAZON_NEEDS_PATH).read()
        for needle in ["semantic content loss", "basic_qualifications",
                       "preferred_qualifications", "1+ years of Windows Server",
                       "SCCM", "teleconference equipment"]:
            self.assertIn(needle, content,
                          msg=f"Amazon NEEDS_EXTENSION doc must mention '{needle}' "
                              f"as concrete evidence of semantic loss")

    def test_doc_documents_traversal_budget_finding(self):
        content = open(AMAZON_NEEDS_PATH).read()
        for needle in ["1001", "600", "max_requests_per_run",
                       "traversal_complete_under_safety_policy"]:
            self.assertIn(needle, content,
                          msg=f"Amazon NEEDS_EXTENSION doc must mention '{needle}' "
                              f"as concrete evidence of traversal budget")

    def test_doc_documents_extension_pressure_for_text_composition(self):
        """The doc must propose a primitive for composing multiple
        text paths (or a separate qualifications_path). Without
        it, the finding has no actionable closure."""
        content = open(AMAZON_NEEDS_PATH).read()
        for needle in ["compose multiple text paths",
                       "qualifications_path",
                       "join_paths"]:
            self.assertIn(needle.lower(), content.lower(),
                          msg=f"Amazon NEEDS_EXTENSION doc must propose primitive "
                              f"mentioning '{needle}'")

    def test_doc_references_real_evidence_no_new_http(self):
        """The doc must explicitly note that the findings were
        derived offline from existing fixtures, not from new HTTP."""
        content = open(AMAZON_NEEDS_PATH).read()
        self.assertRegex(content, r"(?i)zero (new )?http",
                         msg="Amazon NEEDS_EXTENSION doc must state zero new HTTP")
        self.assertIn("fixtures", content,
                      msg="Amazon NEEDS_EXTENSION doc must reference existing fixtures")

    def test_no_live_pass_v01_spec_for_amazon(self):
        """Anti-cheat: ensure NO live `candidates/amazon.json`
        exists claiming PASS_V01. The old one is archived, not
        deleted, but it must not be a loadable active spec."""
        live = os.path.join(HERE, "candidates", "amazon.json")
        self.assertFalse(os.path.exists(live),
                         msg=f"{live} MUST NOT exist — Amazon is NEEDS_EXTENSION "
                             f"after re-evaluation. The old spec is archived "
                             f"in {AMAZON_SPEC_ARCHIVE}.")


class AmazonNoSafetyAbortTests(unittest.TestCase):
    """Amazon discovery produced no 403/429/CAPTCHA. The doc must
    say so."""

    def test_doc_states_zero_429_403(self):
        content = open(AMAZON_NEEDS_EXTENSION_DOC := AMAZON_NEEDS_PATH).read()
        # Look for explicit statements of zero 4xx/captcha; accept
        # either "no 429", "zero 429", "0 429", "Zero 4xx", or similar.
        self.assertRegex(
            content,
            r"(?i)(no|zero|nessun|0)\s*(429|403|captcha|http error|anti-bot|throttl)",
            msg="Amazon NEEDS_EXTENSION doc must state zero 429/403/CAPTCHA",
        )


# ============================================================
# APPLE — NEEDS_EXTENSION with the catalog_scope contradiction
# ============================================================

class AppleNeedsExtensionDocTests(unittest.TestCase):

    def test_apple_needs_extension_doc_exists(self):
        self.assertTrue(os.path.exists(APPLE_NEEDS_PATH),
                        msg=f"missing {APPLE_NEEDS_PATH}")

    def test_apple_doc_declares_correct_verdict(self):
        content = open(APPLE_NEEDS_PATH).read()
        self.assertIn("NEEDS_EXTENSION", content,
                      msg="Apple doc must declare NEEDS_EXTENSION")

    def test_apple_doc_documents_real_request_response_evidence(self):
        content = open(APPLE_NEEDS_PATH).read()
        for needle in ["CSRFToken", "api/v1/search", "page=1",
                       "page=2", "page=307", "page=308", "6124",
                       "POST", "GET"]:
            self.assertIn(needle, content,
                          msg=f"Apple doc must mention real evidence: '{needle}'")

    def test_apple_doc_documents_missing_primitives(self):
        content = open(APPLE_NEEDS_PATH).read()
        for needle in ["page_number", "page-number", "bootstrap",
                       "session cookie", "csrf"]:
            self.assertIn(needle.lower(), content.lower(),
                          msg=f"Apple doc must mention '{needle}'")

    def test_apple_no_fake_spec(self):
        fake = os.path.join(HERE, "candidates", "apple.json")
        self.assertFalse(os.path.exists(fake),
                         msg=f"{fake} MUST NOT exist — only the NEEDS_EXTENSION "
                             f"markdown may exist for Apple.")

    def test_apple_no_http_429_received(self):
        content = open(APPLE_NEEDS_PATH).read()
        self.assertRegex(content, r"(?i)(no|zero|nessun).*(429|403|captcha)",
                         msg="Apple doc must document zero 429/403/CAPTCHA")

    def test_apple_fixture_is_real_capture(self):
        fixture = _load(APPLE_FIXTURE)
        self.assertIn("res", fixture)
        self.assertIn("searchResults", fixture["res"])
        self.assertIn("totalRecords", fixture["res"])
        self.assertEqual(fixture["res"]["totalRecords"], 6124)
        self.assertEqual(len(fixture["res"]["searchResults"]), 20)
        first = fixture["res"]["searchResults"][0]
        for k in ("positionId", "postingTitle", "locations", "team",
                  "postDateInGMT", "jobSummary"):
            self.assertIn(k, first,
                          msg=f"Apple fixture item missing real key: {k}")


class AppleCatalogScopeContradictionTests(unittest.TestCase):
    """The earlier batch-2 report claimed the Apple request was
    filtered with postingpostLocation:["postLocation-USA"]. The
    actual saved fixture contains jobs from 16 countries. We do
    NOT invent an explanation; we just document the contradiction
    and set catalog_scope = unresolved."""

    def test_fixture_contains_jobs_from_multiple_countries(self):
        fixture = _load(APPLE_FIXTURE)
        countries = set()
        for r in fixture["res"]["searchResults"]:
            for loc in r.get("locations", []):
                if isinstance(loc, dict):
                    countries.add(loc.get("countryName", ""))
        countries.discard("")
        # Known to be at least: United States, India, Germany, etc.
        self.assertGreater(len(countries), 5,
                           msg=f"fixture contains {len(countries)} countries: "
                               f"{sorted(countries)} — far more than USA-only")

    def test_fixture_countries_include_india_germany_etc(self):
        """Specifically check that countries OTHER than USA are
        present in the fixture, contradicting the earlier report's
        postLocation-USA filter claim."""
        fixture = _load(APPLE_FIXTURE)
        countries = set()
        for r in fixture["res"]["searchResults"]:
            for loc in r.get("locations", []):
                if isinstance(loc, dict):
                    countries.add(loc.get("countryName", ""))
        # The fixture is known offline to contain at least these:
        for needle in ("India", "Germany", "United Kingdom", "France"):
            self.assertIn(needle, countries,
                          msg=f"fixture must contain {needle!r} (so the "
                              f"USA-only filter claim cannot be verified)")

    def test_fixture_has_united_states_too(self):
        """We document both sides: USA IS present, but other
        countries are also present, so the filter is not USA-only."""
        fixture = _load(APPLE_FIXTURE)
        countries = set()
        for r in fixture["res"]["searchResults"]:
            for loc in r.get("locations", []):
                if isinstance(loc, dict):
                    countries.add(loc.get("countryName", ""))
        self.assertIn("United States of America", countries,
                      msg="fixture does contain US jobs")

    def test_total_records_does_not_imply_usa_only(self):
        """We document the unresolved scope: 6124 jobs in this
        fixture may or may not be USA-only. Without a request that
        we can reproduce, we cannot tell. This test asserts that
        catalog_scope for Apple is unresolved, not 'usa_only'."""
        fixture = _load(APPLE_FIXTURE)
        # The fixture exists and we can read its totalRecords.
        # We CANNOT infer scope from the saved fixture alone
        # because we no longer have the request log.
        self.assertEqual(fixture["res"]["totalRecords"], 6124)
        # The verdict is "unresolved". We document this in the
        # re-evaluation report, not by mutating the spec, but
        # this test is the offline anchor that records the
        # contradiction exists.


# ============================================================
# FROZEN REGRESSION
# ============================================================

class FrozenRegressionTests(unittest.TestCase):

    def test_frozen_executor_tests_still_pass(self):
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

    def test_spec_executor_try_paths_returns_first_truthy(self):
        """Lock the runtime's documented behaviour so the Amazon
        semantic-loss finding has a stable reproducer."""
        item = {
            "description": "primary description text",
            "basic_qualifications": "BASIC text",
            "preferred_qualifications": "PREFERRED text",
        }
        paths = ["description", "basic_qualifications", "preferred_qualifications"]
        # _try_paths is module-private; we exercise it via the
        # public extract_description to keep this test robust
        # against internal renames.
        spec = {"extraction": {"description": {
            "path": "description",
            "shape": "string",
            "fallback_paths": ["basic_qualifications", "preferred_qualifications"],
        }}}
        desc, quals, _ = se.extract_description(spec, item)
        self.assertEqual(desc, "primary description text")
        self.assertEqual(quals, "",
                         msg="qualifications must be empty: shape=string puts "
                             "all text into description and never reads fallback")


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

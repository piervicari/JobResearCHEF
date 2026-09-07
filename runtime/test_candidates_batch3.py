#!/usr/bin/env python3
"""
Offline contract tests for batch-3 candidates (Meta + Cloudflare).

Does NOT modify the frozen executor or the frozen schema.
Uses only the same generic `spec_executor.py` to drive
representable sources and to assert documented extension pressure
for sources that do NOT fit v0.1.

Multi-dimensional evaluation per source:
  - contract_fit (PASS_V01 / NEEDS_EXTENSION / CUSTOM_REQUIRED / UNRESOLVED)
  - semantic_complete (true/false/unknown)
  - traversal_complete_under_safety_policy (true/false/unknown)
  - authoritative_for_closed (true/false/unknown)
  - browser_required (true/false/unknown)
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

# --- Cloudflare (REVOKED Phase-1 pre-flight: fake offset pagination; ---
# --- see candidates/cloudflare_NEEDS_EXTENSION.md; tests run against the archived spec) ---
CLOUDFLARE_SPEC_PATH = os.path.join(HERE, "candidates", "_archive",
                                    "cloudflare.json.PASS_V01_then_revoked")
CLOUDFLARE_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "cloudflare_catalog_page.json")
CLOUDFLARE_DETAIL_FIXTURE = os.path.join(HERE, "fixtures", "cloudflare_detail.json")

# --- Meta (NOT representable: UNRESOLVED) ---
META_UNRESOLVED_PATH = os.path.join(HERE, "candidates", "meta_UNRESOLVED.md")
META_FIXTURE_REACHABLE = os.path.join(HERE, "fixtures",
                                    "meta_GRAPHQL_endpoint_reachable_but_doc_id_unknown.json")

JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCE_SPEC_SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ============================================================
# CLOUDFLARE — representable with source_spec/v0.1
# ============================================================

class CloudflareSpecValidationTests(unittest.TestCase):

    def test_cloudflare_spec_validates_against_v01_schema(self):
        spec = _load(CLOUDFLARE_SPEC_PATH)
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        errors = validate_specs.validate_source_spec(spec, schema)
        self.assertEqual(errors, [], msg=f"Cloudflare spec errors: {errors}")

    def test_cloudflare_is_full_catalog_and_authoritative(self):
        spec = _load(CLOUDFLARE_SPEC_PATH)
        self.assertEqual(spec["schema_version"], "source_spec/v0.1")
        self.assertEqual(spec["source_of_truth"], "full_catalog")
        self.assertTrue(spec["open_closed_authoritative"])
        self.assertEqual(spec["platform"]["name"], "greenhouse_job_board_api")

    def test_cloudflare_uses_query_param_for_paging(self):
        spec = _load(CLOUDFLARE_SPEC_PATH)
        self.assertEqual(spec["paging"]["strategy"], "offset")
        self.assertEqual(spec["paging"]["inject"]["target"], "query_param")
        self.assertEqual(spec["paging"]["page_size"], 331)
        self.assertEqual(spec["paging"]["first_page_value"], 0)


class CloudflareRequestRenderingTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(CLOUDFLARE_SPEC_PATH)

    def test_page_1(self):
        r = se.render_catalog_request(self.spec, 0)
        self.assertEqual(r["method"], "GET")
        self.assertEqual(r["url"], "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs")
        self.assertIn("content", r["query"])
        self.assertIn("User-Agent", r["headers"])


class CloudflareExtractionTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(CLOUDFLARE_SPEC_PATH)
        self.page = _load(CLOUDFLARE_PAGE_FIXTURE)
        self.items, self.total = se.extract_page(self.spec, self.page)
        self.assertEqual(self.total, 331)
        self.assertEqual(len(self.items), 331)
        self.item = self.items[0]

    def test_extract_stable_id_title_department_locations(self):
        job = se.extract_item(self.spec, self.item)
        self.assertEqual(job["source_job_id"], "7695702")
        # secondary IDs include internal_job_id and requisition_id
        self.assertIn("3383201", job["source_secondary_ids"])
        self.assertEqual(job["title"], "Account Executive, FedCiv")
        self.assertEqual(job["department"], "Field Sales")
        self.assertEqual(job["organization"], "Cloudflare")
        # locations: list_of_objects with item_template "{name}"
        self.assertEqual(job["locations"], ["Washington, DC"])
        self.assertIn("boards.greenhouse.io", job["official_url"])

    def test_description_extracted_and_html_stripped(self):
        job = se.extract_item(self.spec, self.item)
        # content is HTML; strip removes <...> but leaves entity refs
        # (documented limitation). The text content is present.
        self.assertTrue(len(job.get("description", "")) > 100,
                        msg=f"description too short: {len(job.get('description', ''))}")
        # <p> tags removed (none present after strip because the content
        # was entity-encoded)
        self.assertNotIn("<p>", job["description"])
        self.assertNotIn("<h3>", job["description"])
        # detail_complete=True: description is non-empty (single source)
        self.assertTrue(job["detail_complete"])

    def test_publication_date_iso_datetime(self):
        job = se.extract_item(self.spec, self.item)
        # first_published is "2026-03-09T16:05:19-04:00" — full ISO datetime
        # v0.1's iso_datetime branch returns the raw string unchanged
        self.assertEqual(job["publication_date"], "2026-03-09T16:05:19-04:00")

    def test_normalized_job_conforms_to_schema(self):
        job = se.extract_item(self.spec, self.item)
        job = se.normalize_job(self.spec, job, "2026-09-05T00:00:00+00:00")
        js = _load(JOB_SCHEMA_PATH)
        errors = se.validate_against_job_schema(job, js)
        self.assertEqual(errors, [], msg=f"job schema errors: {errors}")
        self.assertEqual(job["company_id"], "cloudflare")
        self.assertEqual(job["source_platform"], "greenhouse_job_board_api")

    def test_no_detail_endpoint_needed(self):
        # Cloudflare's content=true means description is inline; no
        # detail endpoint needed. The spec has no `detail` block.
        spec = _load(CLOUDFLARE_SPEC_PATH)
        self.assertNotIn("detail", spec)
        # And render_detail_request returns None when no detail block
        self.assertIsNone(se.render_detail_request(spec, "7695702"))


class CloudflarePaginationCountTests(unittest.TestCase):

    def test_cloudflare_single_chunk_total_request_count(self):
        spec = _load(CLOUDFLARE_SPEC_PATH)
        # total=331, page_size=331, first=0
        # pagination_iterator yields exactly 1 offset (0)
        offsets = list(se.pagination_iterator(spec, 331))
        self.assertEqual(len(offsets), 1,
                         msg=f"expected 1 offset, got {len(offsets)}")
        self.assertEqual(offsets[0], 0)
        n = se.total_request_count(spec, 331)
        self.assertEqual(n, 1, msg=f"expected 1 request, got {n}")


class CloudflareCompletenessTests(unittest.TestCase):

    def test_full_catalog_complete_with_probe(self):
        """Cloudflare returns the entire catalog in one chunk
        (331 items). The v0.1 `next_offset_ge_total` rule requires
        the harness to have fetched every offset from `first` to
        `final_total` INCLUSIVE. For total=331, page_size=331, first=0,
        that means offsets [0, 331] — but the pagination_iterator
        yields only [0]. Without a probe page, the rule fails with
        'missing pages: [331]'. Additionally, `last_page_shorter_than_page_size`
        fails because the last page is full (=page_size).

        We document that v0.1 cannot represent Cloudflare-style
        single-chunk catalogs as a clean PASS_V01 sweep without
        either:
        (a) a downstream probe request to satisfy completeness, or
        (b) a new v0.2 primitive for unpaginated full-chunk responses.
        """
        spec = _load(CLOUDFLARE_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 331))
        # Just 1 offset. The runtime will issue 1 request, get 331 items.
        # Multiple v0.1 rules will fail because the iterator never
        # emits an offset >= total. We document which rule fires
        # first (next_offset_ge_total).
        history = [{"page_value": offsets[0], "items_count": 331, "total": 331}]
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertFalse(
            ok,
            msg=("v0.1 completeness cannot succeed with a single "
                 "full-chunk page; documenting."),
        )
        # Document the failure reason — either rule may fire first
        # depending on the iteration order.
        self.assertTrue(
            ("missing pages" in reason) or ("last non-empty page was full" in reason),
            msg=f"expected missing-pages or last-page-full failure, "
                f"got {reason!r}",
        )

    def test_full_catalog_complete_with_explicit_probe(self):
        """If the harness appends an explicit probe request (an
        additional offset=331 returning 0 items), completeness
        succeeds. The runtime can be tricked into this by adding
        the probe manually in the history.

        SUPERSEDED FINDING (Phase-2 hardening §3, generic boundary
        fix): this test previously asserted False, documenting that
        `observed_empty_after` required `page_value > total` while the
        boundary probe sits exactly AT total (331 == 331). The hardened
        evaluator uses `>=`, so a probe at exactly total IS the
        empty-after-total evidence — the same semantics §3 requires for
        NVIDIA/Microsoft (total=10 → probe start=10 → complete=true).
        The assertion is flipped to True WITH the explanation kept, so
        the documented reasoning survives the behavior change.
        """
        spec = _load(CLOUDFLARE_SPEC_PATH)
        # Real pagination_iterator yields 1 offset; harness adds
        # an extra probe (page_value=331, items_count=0).
        history = [
            {"page_value": 0, "items_count": 331, "total": 331},
            {"page_value": 331, "items_count": 0, "total": 331},
        ]
        ok, reason = se.evaluate_completeness(spec, history)
        # Boundary probe (page_value == total) now counts as the
        # empty-after-total observation.
        self.assertTrue(
            ok,
            msg=(f"boundary probe at total must satisfy completeness, got {reason!r}"),
        )

    def test_authoritative_for_closed_with_explicit_2nd_request(self):
        """Demonstrates: if a downstream harness issues multiple
        probe requests (page_value=331 AND page_value=332, both
        returning 0 items), then v0.1's `next_offset_ge_total` rule
        succeeds AND the `last_page_shorter` rule is satisfied via
        the empty-after-total observation, AND the harness is
        authorized to mark CLOSED.

        This documents that Cloudflare's single-chunk catalog
        requires at LEAST 2 probe requests beyond the catalog
        request itself to satisfy v0.1 completeness. The runtime
        pagination_iterator does NOT emit these probes (it only
        emits offset 0), so the harness is responsible for adding
        them.

        Real-world interpretation: the spec produces 1 catalog
        request (1 wire call). The downstream harvester must add
        2 empty-page probes to mark the run authoritative for
        CLOSED. This is operational, not contractual — the spec
        itself is fine, the harness needs to know to do probes.
        """
        spec = _load(CLOUDFLARE_SPEC_PATH)
        history = [
            {"page_value": 0, "items_count": 331, "total": 331},
            {"page_value": 331, "items_count": 0, "total": 331},
            {"page_value": 332, "items_count": 0, "total": 331},
        ]
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertTrue(ok, msg=f"expected complete with 2 probes, got {reason!r}")
        decision = se.closed_decision(spec, ok)
        self.assertTrue(decision["may_mark_closed"],
                        msg="full_catalog authoritative must mark closed with probes")


class CloudflareSpecMutationTests(unittest.TestCase):

    def test_cloudflare_rendering_does_not_mutate_spec(self):
        spec = _load(CLOUDFLARE_SPEC_PATH)
        snapshot = json.dumps(spec, sort_keys=True)
        for offset in [0, 0, 0]:
            se.render_catalog_request(spec, offset)
        after = json.dumps(spec, sort_keys=True)
        self.assertEqual(snapshot, after,
                         msg="rendering mutated the Cloudflare spec")


# ============================================================
# META — UNRESOLVED (no fake PASS_V01 spec)
# ============================================================

class MetaUnresolvedTests(unittest.TestCase):

    def test_meta_unresolved_doc_exists(self):
        self.assertTrue(os.path.exists(META_UNRESOLVED_PATH),
                        msg=f"missing {META_UNRESOLVED_PATH}")

    def test_meta_doc_declares_correct_verdict(self):
        content = open(META_UNRESOLVED_PATH).read()
        self.assertIn("UNRESOLVED", content,
                      msg="Meta doc must declare UNRESOLVED verdict")

    def test_meta_doc_documents_discovery_attempts(self):
        content = open(META_UNRESOLVED_PATH).read()
        # Must document the Comet/GraphQL protocol (Meta's backend)
        for needle in ["GraphQL", "Comet", "persisted quer", "doc_id"]:
            # "persisted quer" matches both "persisted queries" and
            # "persisted query"; we accept either form
            self.assertIn(needle.lower(), content.lower(),
                          msg=f"Meta doc must mention '{needle}'")

    def test_meta_no_fake_spec(self):
        fake = os.path.join(HERE, "candidates", "meta.json")
        self.assertFalse(os.path.exists(fake),
                         msg=f"{fake} MUST NOT exist — only the UNRESOLVED "
                             f"markdown may exist for Meta.")

    def test_meta_fixture_documents_protocol_but_not_payload(self):
        """The saved fixture is not a usable catalog response; it's
        only evidence that the GraphQL endpoint is reachable.
        Document that explicitly."""
        f = _load(META_FIXTURE_REACHABLE)
        self.assertIn("errors", f,
                      msg="Meta fixture must contain GraphQL errors (proves "
                          "endpoint reachable but doc_id unknown)")
        # The error message must be the doc_id-not-found kind
        errors = f.get("errors", [])
        self.assertGreater(len(errors), 0)
        first_msg = errors[0].get("message", "")
        self.assertIn("not found", first_msg.lower(),
                      msg=f"Meta fixture error must mention 'not found', "
                          f"got {first_msg!r}")

    def test_meta_no_429_received(self):
        content = open(META_UNRESOLVED_PATH).read()
        self.assertRegex(content, r"(?i)(no|zero|nessun).*(429|403|captcha)",
                         msg="Meta doc must document zero 429/403/CAPTCHA")


# ============================================================
# FROZEN REGRESSION — run all previously-frozen test modules
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
        self.assertIsNotNone(m)
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
        self.assertIsNotNone(m)
        n = int(m.group(1))
        self.assertGreaterEqual(n, 24,
                                msg=f"batch1 test count dropped below 24: {n}")

    def test_batch2_revised_tests_still_pass(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "test_candidates_batch2_revised.py")],
            capture_output=True, text=True, cwd=HERE,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0,
                         msg=f"batch2 revised tests FAILED:\n"
                             f"stdout: {result.stdout}\nstderr: {result.stderr}")
        m = re.search(r"Ran (\d+) tests? in", combined)
        self.assertIsNotNone(m)
        n = int(m.group(1))
        self.assertGreaterEqual(n, 25,
                                msg=f"batch2 revised test count dropped below 25: {n}")

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

    def test_extension_pressure_registry_exists(self):
        """Lock that the cumulative registry file exists and contains
        at least the entries from prior batches."""
        registry = os.path.join(HERE, "EXTENSION_PRESSURE_REGISTRY.md")
        self.assertTrue(os.path.exists(registry),
                        msg=f"missing {registry}")
        content = open(registry).read()
        # At least the entries that were documented before batch 3
        for needle in ["Amazon", "Apple", "page_number",
                       "basic_qualifications", "csrf", "session cookie"]:
            self.assertIn(needle, content,
                          msg=f"Extension registry must mention '{needle}'")


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

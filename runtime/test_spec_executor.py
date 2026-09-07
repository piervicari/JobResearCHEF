#!/usr/bin/env python3
"""
Offline contract tests for spec_executor.py.

Validates that the SAME source-agnostic executor handles both Mercedes
and NVIDIA source specs correctly. Includes:
  - spec validation
  - request rendering (catalog + detail)
  - extraction (catalog + detail)
  - normalized job schema compliance
  - completeness + CLOSED policy
  - GENERICITY: spec_executor must contain zero source-specific branches
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spec_executor as se  # noqa: E402

MERCEDES_SPEC_PATH = os.path.join(HERE, "sources", "mercedes.json")
NVIDIA_SPEC_PATH = os.path.join(HERE, "sources", "nvidia.json")
JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCE_SPEC_SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")
MERCEDES_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "mercedes_catalog_page.json")
NVIDIA_PAGE_FIXTURE = os.path.join(HERE, "fixtures", "nvidia_catalog_page.json")
NVIDIA_DETAIL_FIXTURE = os.path.join(HERE, "fixtures", "nvidia_detail.json")
SPEC_EXECUTOR_PATH = os.path.join(HERE, "spec_executor.py")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ============================================================
# GENERICITY
# ============================================================

class GenericityTests(unittest.TestCase):
    """Static AST scan of spec_executor.py: NO source-specific branching."""

    FORBIDDEN_TOKENS = [
        "mercedes", "nvidia",
        "beesite", "eightfold",
        "eightfold_pcsx", "pcsx",
    ]

    def test_no_source_specific_tokens(self):
        src = open(SPEC_EXECUTOR_PATH).read()
        hits = []
        for tok in self.FORBIDDEN_TOKENS:
            # Case-insensitive but skip docstring / comments? We treat the
            # whole file uniformly — the spec executor should not even
            # MENTION these names. Comments included.
            pattern = re.compile(r"\b" + re.escape(tok) + r"\b", re.IGNORECASE)
            for m in pattern.finditer(src):
                # report the line number
                line_no = src[:m.start()].count("\n") + 1
                hits.append((tok, line_no))
        self.assertEqual(
            hits, [], msg=f"spec_executor.py must not mention source-specific "
                            f"names (Mercedes, NVIDIA, Beesite, Eightfold). "
                            f"Found: {hits}"
        )

    def test_no_company_or_platform_keyword_in_code(self):
        src = open(SPEC_EXECUTOR_PATH).read()
        for kw in ["company_id ==", "platform ==", "platform==", "company =="]:
            self.assertNotIn(kw, src, f"spec_executor must not branch on {kw!r}")


# ============================================================
# SPEC VALIDATION
# ============================================================

class SpecValidationTests(unittest.TestCase):

    def setUp(self):
        # Use the existing offline validator to make sure both specs are valid.
        import validate_specs  # noqa
        # We re-use the validator's _check_required_keys, _check_no_arbitrary_code,
        # etc. but the cleanest path is just to run it on each spec.
        self.validate = validate_specs

    def test_mercedes_spec_is_valid(self):
        spec = _load(MERCEDES_SPEC_PATH)
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        errors = self.validate.validate_source_spec(spec, schema)
        self.assertEqual(errors, [], msg=f"Mercedes spec errors: {errors}")

    def test_nvidia_spec_is_valid(self):
        spec = _load(NVIDIA_SPEC_PATH)
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        errors = self.validate.validate_source_spec(spec, schema)
        self.assertEqual(errors, [], msg=f"NVIDIA spec errors: {errors}")

    def test_mercedes_is_full_catalog_and_authoritative(self):
        spec = _load(MERCEDES_SPEC_PATH)
        self.assertEqual(spec["source_of_truth"], "full_catalog")
        self.assertTrue(spec["open_closed_authoritative"])

    def test_nvidia_is_full_catalog_and_authoritative(self):
        spec = _load(NVIDIA_SPEC_PATH)
        self.assertEqual(spec["source_of_truth"], "full_catalog")
        self.assertTrue(spec["open_closed_authoritative"])

    def test_mercedes_body_searchcriteria_empty(self):
        spec = _load(MERCEDES_SPEC_PATH)
        # The canonical body must have SearchCriteria = []. We do NOT
        # require a cybersecurity keyword anywhere in the spec.
        self.assertEqual(spec["request"]["body"]["SearchCriteria"], [])
        self.assertNotIn("keyword", spec["request"]["variables"])
        self.assertNotIn("cybersecurity", json.dumps(spec).lower())

    def test_paging_inject_is_explicit(self):
        for path in (MERCEDES_SPEC_PATH, NVIDIA_SPEC_PATH):
            spec = _load(path)
            self.assertIn("inject", spec["paging"])
            self.assertIn("target", spec["paging"]["inject"])
            target = spec["paging"]["inject"]["target"]
            self.assertIn(target, ("query_param", "body_path", "url_path"))

    def test_mercedes_uses_body_path_for_paging(self):
        spec = _load(MERCEDES_SPEC_PATH)
        self.assertEqual(spec["paging"]["inject"]["target"], "body_path")
        self.assertEqual(spec["paging"]["inject"]["path"], "SearchParameters.FirstItem")

    def test_nvidia_uses_query_param_for_paging(self):
        spec = _load(NVIDIA_SPEC_PATH)
        self.assertEqual(spec["paging"]["inject"]["target"], "query_param")


# ============================================================
# MERCEDES
# ============================================================

class MercedesRequestRenderingTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(MERCEDES_SPEC_PATH)

    def test_page_1(self):
        r = se.render_catalog_request(self.spec, 1)
        self.assertEqual(r["method"], "POST")
        self.assertEqual(r["url"], "https://jobs.api.mercedes-benz.com/search")
        self.assertEqual(r["headers"]["Accept"], "application/json")
        self.assertEqual(r["headers"]["Content-Type"], "application/json")
        self.assertEqual(r["body"]["SearchParameters"]["FirstItem"], 1)
        self.assertEqual(r["body"]["SearchCriteria"], [])
        self.assertIn("User-Agent", r["headers"])
        self.assertEqual(r["body"]["LanguageCode"], "EN")

    def test_page_2_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 51)
        self.assertEqual(r["body"]["SearchParameters"]["FirstItem"], 51)

    def test_page_3_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 101)
        self.assertEqual(r["body"]["SearchParameters"]["FirstItem"], 101)


class MercedesExtractionTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(MERCEDES_SPEC_PATH)
        self.page = _load(MERCEDES_PAGE_FIXTURE)
        self.items, self.total = se.extract_page(self.spec, self.page)
        self.assertEqual(self.total, 2798)
        self.assertEqual(len(self.items), 1)
        self.item = self.items[0]

    def test_extract_stable_id_title_location_date_url_description(self):
        job = se.extract_item(self.spec, self.item)
        self.assertEqual(job["source_job_id"], "mer000484n")
        self.assertEqual(job["title"], "Executive, Digital Apps & Online Platforms")
        self.assertEqual(job["department"], "Brand & Communications Strategy")
        self.assertEqual(job["organization"], "Mercedes-Benz Taiwan Ltd.")
        self.assertEqual(job["locations"], ["Mercedes-Benz Taiwan Ltd., Taipei"])
        self.assertEqual(job["publication_date"], "2026-09-04")
        self.assertEqual(job["expiration_date"], "2026-10-04")
        self.assertEqual(
            job["official_url"],
            "https://jobs.mercedes-benz.com/executive-digital-apps-online-platforms--237103-MER000484N",
        )
        # description_in_catalog=true so the executor exposes description
        # from the catalog item, not via detail request.
        # We do NOT have a description_path that yields it; the job schema
        # treats description/qualifications as optional strings filled by
        # either catalog or detail. Mercedes stores description in
        # PositionFormattedDescription; the spec does not point to it
        # (the harvester stores it in its own DB). For source-spec v0 the
        # description is optional and may stay empty.
        # The presence of a detail block would be required if the spec
        # wanted the executor to fetch descriptions; we deliberately did
        # NOT add a detail block because Mercedes already provides the
        # description in the catalog. So we test the absence of detail:
        self.assertIsNone(se.render_detail_request(self.spec, "mer000484n"))

    def test_normalized_job_conforms_to_job_schema(self):
        job = se.extract_item(self.spec, self.item)
        job = se.normalize_job(self.spec, job, "2026-09-05T00:00:00+00:00")
        js = _load(JOB_SCHEMA_PATH)
        errors = se.validate_against_job_schema(job, js)
        self.assertEqual(errors, [], msg=f"job schema errors: {errors}")
        self.assertEqual(job["company_id"], "mercedes-benz")
        self.assertEqual(job["source_platform"], "beesite")
        self.assertTrue(job["official_url"].startswith("https://jobs.mercedes-benz.com/"))

    def test_apply_url_is_resolved_from_applyuri_array(self):
        job = se.extract_item(self.spec, self.item)
        self.assertTrue(job["apply_url"].startswith("https://tas-DAIMLER.taleo.net/"))


# ============================================================
# NVIDIA
# ============================================================

class NvidiaRequestRenderingTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(NVIDIA_SPEC_PATH)

    def test_page_1(self):
        r = se.render_catalog_request(self.spec, 0)
        self.assertEqual(r["method"], "GET")
        self.assertEqual(r["url"], "https://jobs.nvidia.com/api/pcsx/search")
        self.assertEqual(r["query"]["domain"], "nvidia.com")
        self.assertEqual(r["query"]["start"], 0)
        self.assertEqual(r["query"]["hl"], "en")
        self.assertIn("User-Agent", r["headers"])

    def test_page_2_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 10)
        self.assertEqual(r["query"]["start"], 10)

    def test_page_3_offsets_correctly(self):
        r = se.render_catalog_request(self.spec, 20)
        self.assertEqual(r["query"]["start"], 20)


class NvidiaExtractionTests(unittest.TestCase):

    def setUp(self):
        self.spec = _load(NVIDIA_SPEC_PATH)
        self.page = _load(NVIDIA_PAGE_FIXTURE)
        self.items, self.total = se.extract_page(self.spec, self.page)
        self.assertEqual(self.total, 2674)
        self.assertEqual(len(self.items), 10)
        self.item = self.items[0]

    def test_extract_catalog_stable_id_title_location_date_url(self):
        job = se.extract_item(self.spec, self.item)
        self.assertEqual(job["source_job_id"], "893397562188")
        self.assertEqual(job["title"], "ASIC Verification Engineer - Clocks")
        self.assertEqual(job["department"], "Engineer, Verification")
        self.assertEqual(job["locations"], ["India, Bengaluru"])
        self.assertEqual(job["publication_date"], "2026-09-04")
        # official_url_template is used because publicUrl may not be in
        # the catalog item.
        self.assertEqual(
            job["official_url"], "https://jobs.nvidia.com/careers/job/893397562188",
        )
        # The catalog item has no description (description_in_catalog=false)
        self.assertNotIn("description", job)

    def test_normalized_catalog_only_job(self):
        job = se.extract_item(self.spec, self.item)
        job = se.normalize_job(self.spec, job, "2026-09-05T00:00:00+00:00")
        js = _load(JOB_SCHEMA_PATH)
        errors = se.validate_against_job_schema(job, js)
        self.assertEqual(errors, [], msg=f"job schema errors: {errors}")

    def test_detail_request_uses_stable_id(self):
        dr = se.render_detail_request(self.spec, self.item["id"])
        self.assertIsNotNone(dr)
        self.assertEqual(dr["method"], "GET")
        self.assertEqual(dr["url"], "https://jobs.nvidia.com/api/pcsx/position_details")
        self.assertEqual(dr["query"]["domain"], "nvidia.com")
        self.assertEqual(dr["query"]["position_id"], self.item["id"])
        self.assertEqual(dr["query"]["hl"], "en")
        self.assertIn("User-Agent", dr["headers"])

    def test_detail_response_populates_description(self):
        detail = _load(NVIDIA_DETAIL_FIXTURE)
        catalog_job = se.extract_item(self.spec, self.item)
        full = se.merge_detail_into_job(self.spec, dict(catalog_job), detail)
        full = se.normalize_job(self.spec, full, "2026-09-05T00:00:00+00:00")
        self.assertTrue(len(full.get("description", "")) > 100)
        # HTML was stripped: no <p> or <ul> tags should remain.
        self.assertNotIn("<p>", full["description"])
        self.assertNotIn("<ul>", full["description"])
        # And the schema still validates.
        js = _load(JOB_SCHEMA_PATH)
        self.assertEqual(se.validate_against_job_schema(full, js), [])


# ============================================================
# COMPLETENESS + CLOSED POLICY
# ============================================================

class CompletenessTests(unittest.TestCase):

    def test_offset_complete_when_total_reached(self):
        spec = _load(MERCEDES_SPEC_PATH)
        page_size = spec["paging"]["page_size"]  # 50
        first = spec["paging"]["first_page_value"]  # 1
        # Construct a history that walks 2798 jobs starting at 1, with the
        # last full page (2751) returning 48 items (partial) and the next
        # page (2801) returning 0 items. The items_path_empty_after_total
        # rule requires observing that empty page.
        history = []
        offset = first
        while offset <= 2798:
            count = min(page_size, 2798 - offset + 1)
            history.append({"page_value": offset, "items_count": count, "total": 2798})
            offset += page_size
        # Add the empty-after-total page.
        history.append({"page_value": 2801, "items_count": 0, "total": 2798})
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertTrue(ok, msg=f"expected complete, got reason={reason}")

    def test_offset_empty_page_before_total_is_incomplete(self):
        spec = _load(MERCEDES_SPEC_PATH)
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        # An anomalous scenario: page 1 returned 50 items, total=2798, but
        # the next page returned 0 items. The executor must NOT claim
        # completeness.
        history = [
            {"page_value": first, "items_count": page_size, "total": 2798},
            {"page_value": first + page_size, "items_count": 0, "total": 2798},
        ]
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertFalse(ok)
        # The reason should mention the missing pages or the empty-after-total rule.
        self.assertTrue(len(reason) > 0)

    def test_incomplete_blocks_closed_for_authoritative_source(self):
        spec = _load(MERCEDES_SPEC_PATH)
        # Incomplete history
        history = [
            {"page_value": 1, "items_count": 50, "total": 2798},
        ]
        ok, _ = se.evaluate_completeness(spec, history)
        self.assertFalse(ok)
        decision = se.closed_decision(spec, ok)
        self.assertFalse(decision["may_mark_closed"])
        self.assertIn("incomplete", decision["reason"])

    def test_complete_allows_closed_for_authoritative_source(self):
        spec = _load(MERCEDES_SPEC_PATH)
        page_size = spec["paging"]["page_size"]
        first = spec["paging"]["first_page_value"]
        history = []
        offset = first
        while offset <= 2798:
            count = min(page_size, 2798 - offset + 1)
            history.append({"page_value": offset, "items_count": count, "total": 2798})
            offset += page_size
        # Add the empty-after-total page so items_path_empty_after_total passes.
        history.append({"page_value": 2801, "items_count": 0, "total": 2798})
        ok, reason = se.evaluate_completeness(spec, history)
        self.assertTrue(ok, msg=f"expected complete, got reason={reason}")
        decision = se.closed_decision(spec, ok)
        self.assertTrue(decision["may_mark_closed"])

    def test_filtered_catalog_never_marks_closed(self):
        # Hypothetical filtered spec: same shape as Mercedes but
        # source_of_truth=filtered_catalog, open_closed_authoritative=false.
        spec = _load(MERCEDES_SPEC_PATH)
        spec["source_of_truth"] = "filtered_catalog"
        spec["open_closed_authoritative"] = False
        decision = se.closed_decision(spec, complete=True)
        self.assertFalse(decision["may_mark_closed"])


# ============================================================
# ADDITIONAL HARDENING TESTS (v0.1)
# ============================================================

class DescriptionExtractionTests(unittest.TestCase):
    """Real content extraction: description + qualifications must come
    out of the catalog item, not be silently empty."""

    def test_mercedes_description_and_qualifications_real_content(self):
        spec = _load(MERCEDES_SPEC_PATH)
        page = _load(MERCEDES_PAGE_FIXTURE)
        items, _ = se.extract_page(spec, page)
        item = items[0]
        job = se.extract_item(spec, item)
        # Real content must be present, NOT just an empty string.
        self.assertTrue(len(job.get("description", "")) > 0,
                        msg=f"Mercedes description is empty: {job!r}")
        self.assertTrue(len(job.get("qualifications", "")) > 0,
                        msg=f"Mercedes qualifications is empty: {job!r}")
        # And HTML must be stripped.
        self.assertNotIn("<p>", job["description"])
        self.assertNotIn("<p>", job["qualifications"])
        # And the text must match what the fixture actually said.
        self.assertIn("Lead the regional digital apps", job["description"])
        self.assertIn("digital product leadership", job["qualifications"])

    def test_mercedes_detail_complete_true_from_catalog(self):
        spec = _load(MERCEDES_SPEC_PATH)
        page = _load(MERCEDES_PAGE_FIXTURE)
        items, _ = se.extract_page(spec, page)
        job = se.extract_item(spec, items[0])
        job = se.normalize_job(spec, job, "2026-09-05T00:00:00+00:00")
        self.assertTrue(job["detail_complete"],
                        msg=f"Mercedes must be detail_complete=True after catalog extraction")

    def test_nvidia_catalog_only_has_detail_complete_false(self):
        spec = _load(NVIDIA_SPEC_PATH)
        page = _load(NVIDIA_PAGE_FIXTURE)
        items, _ = se.extract_page(spec, page)
        # Catalog item has no jobDescription. extract_item should leave
        # description empty and detail_complete=False.
        job = se.extract_item(spec, items[0])
        self.assertEqual(job.get("description", ""), "")
        self.assertFalse(job.get("detail_complete", True))
        job = se.normalize_job(spec, job, "2026-09-05T00:00:00+00:00")
        self.assertFalse(job["detail_complete"])

    def test_nvidia_detail_response_flips_detail_complete_true(self):
        spec = _load(NVIDIA_SPEC_PATH)
        page = _load(NVIDIA_PAGE_FIXTURE)
        items, _ = se.extract_page(spec, page)
        detail = _load(NVIDIA_DETAIL_FIXTURE)
        job = se.extract_item(spec, items[0])
        # Before detail
        self.assertFalse(job.get("detail_complete", True))
        full = se.merge_detail_into_job(spec, dict(job), detail)
        full = se.normalize_job(spec, full, "2026-09-05T00:00:00+00:00")
        # After detail — detail response has jobDescription, so complete
        self.assertTrue(full["detail_complete"])
        # And the description came from the detail.
        self.assertTrue(len(full["description"]) > 50)
        # HTML stripped
        self.assertNotIn("<p>", full["description"])


class SpecMutationTests(unittest.TestCase):
    """Render must not mutate the spec passed in."""

    def test_mercedes_rendering_does_not_mutate_spec(self):
        spec = _load(MERCEDES_SPEC_PATH)
        snapshot = json.dumps(spec, sort_keys=True)
        for offset in [1, 51, 101, 51, 1, 9999]:
            se.render_catalog_request(spec, offset)
        # Re-render with detail
        se.render_detail_request(spec, "mer000484n")
        after = json.dumps(spec, sort_keys=True)
        self.assertEqual(snapshot, after,
                         msg="rendering mutated the spec — spec must stay immutable")

    def test_nvidia_rendering_does_not_mutate_spec(self):
        spec = _load(NVIDIA_SPEC_PATH)
        snapshot = json.dumps(spec, sort_keys=True)
        for offset in [0, 10, 20, 30, 10, 0]:
            se.render_catalog_request(spec, offset)
        se.render_detail_request(spec, 893397562188)
        after = json.dumps(spec, sort_keys=True)
        self.assertEqual(snapshot, after,
                         msg="rendering mutated the spec — spec must stay immutable")


class PaginationCountTests(unittest.TestCase):
    """Mathematical verification of how many requests a full
    authoritative Mercedes reconciliation issues."""

    def test_mercedes_full_sweep_request_count(self):
        spec = _load(MERCEDES_SPEC_PATH)
        # total=2798, page_size=50, first=1
        # data pages = ceil((2798 - 1 + 1)/50) = 56 pages (offsets 1..2751)
        # + 1 empty-after-total probe page (offset 2801)
        # = 57 total requests
        n = se.total_request_count(spec, 2798)
        self.assertEqual(n, 57, msg=f"expected 57 requests, got {n}")

    def test_mercedes_pagination_iterator_emits_57_offsets(self):
        spec = _load(MERCEDES_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 2798))
        self.assertEqual(len(offsets), 57,
                         msg=f"expected 57 offsets, got {len(offsets)}: {offsets[:5]}...{offsets[-5:]}")
        # First 56 are data pages (1, 51, 101, ..., 2751)
        self.assertEqual(offsets[0], 1)
        self.assertEqual(offsets[55], 2751)
        # Last is the empty-after-total probe
        self.assertEqual(offsets[56], 2801)
        self.assertEqual(offsets, sorted(offsets))

    def test_mercedes_data_offsets_count_matches_total(self):
        spec = _load(MERCEDES_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 2798))
        # 56 data offsets cover items 1..2751; with page_size=50, the last
        # data page returns items 2751..2798 → 48 items. We can verify by
        # counting: offsets that map to data pages = those <= last_data_offset.
        last_data_offset = 2751
        data_offsets = [o for o in offsets if o <= last_data_offset]
        self.assertEqual(len(data_offsets), 56)

    def test_nvidia_synthetic_total(self):
        # NVIDIA's completeness rules are next_offset_ge_total +
        # last_page_shorter_than_page_size. There is NO
        # items_path_empty_after_total, so NO trailing empty probe.
        # total=24, page_size=10, first=0 → ceil(24/10) = 3 data pages.
        spec = _load(NVIDIA_SPEC_PATH)
        offsets = list(se.pagination_iterator(spec, 24))
        self.assertEqual(offsets, [0, 10, 20])
        self.assertEqual(se.total_request_count(spec, 24), 3)


class ExecutorHardeningTests(unittest.TestCase):
    """Static + behavioral checks that the runtime contains NO knowledge
    of payload field names from the two real sources."""

    # Real source-payload field names. We deliberately do NOT include
    # schema-generic keys like 'company', 'platform', 'language',
    # 'headers', 'query', 'body', 'jobs', 'data' — those are part of
    # the source_spec schema, not the payload. The schema-generic
    # 'id' key in spec.company.id is also NOT a payload field. We
    # only list the names that appear in real catalog responses.
    PAYLOAD_FIELDS = [
        # Mercedes-Benz
        "DisplayName", "CityName", "CountryCode", "CountryName",
        "ContinentName", "CountrySubDivisionName", "StreetName",
        "PositionLocation", "PositionFormattedDescription",
        "PositionTitle", "DepartmentName", "ParentOrganizationName",
        "PublicationStartDate", "PublicationEndDate",
        "PositionURI", "ApplyURI", "PositionID",
        "MatchedObjectDescriptor", "SearchResultCountAll",
        "SearchResultItems", "FirstItem", "SearchParameters",
        "LanguageCode", "SearchCriteria", "PublicationLanguage",
        # NVIDIA
        "displayJobId", "atsJobId", "postedTs", "publicUrl",
        "jobDescription", "positionUserActions", "applyAction",
        "applyUrl", "positions", "filterDef", "resultsMetaData",
        "appliedFilters", "sortBy",
        # Platform / vendor names
        "eightfold", "beesite", "pcsx",
    ]

    def _strip_python_noise(self, src: str) -> str:
        """Remove comments and docstrings so the static scan cannot
        be silenced by smuggling a payload field name into a comment."""
        src = re.sub(r"#[^\n]*", "", src)
        src = re.sub(r'"""[\s\S]*?"""', "", src)
        src = re.sub(r"'''[\s\S]*?'''", "", src)
        return src

    def test_no_payload_field_names_in_executor(self):
        src = open(SPEC_EXECUTOR_PATH).read()
        code_only = self._strip_python_noise(src)
        hits = []
        for fld in self.PAYLOAD_FIELDS:
            if re.search(r"\b" + re.escape(fld) + r"\b", code_only):
                hits.append(fld)
        self.assertEqual(hits, [],
                         msg=f"executor code must not contain payload field "
                             f"names: {hits}")

    def test_no_payload_field_names_anywhere_in_executor(self):
        """Even in comments/docstrings — the runtime must not MENTION
        any payload field name. This is stricter than
        test_no_payload_field_names_in_executor and exists so that
        someone who adds a 'see PositionFormattedDescription' comment
        is forced to drop it instead of letting it become a fixture
        for future copy-paste."""
        src = open(SPEC_EXECUTOR_PATH).read()
        hits = []
        for fld in self.PAYLOAD_FIELDS:
            if re.search(r"\b" + re.escape(fld) + r"\b", src):
                # find the line for the message
                m = re.search(r"\b" + re.escape(fld) + r"\b", src)
                line_no = src[:m.start()].count("\n") + 1
                hits.append((fld, line_no))
        self.assertEqual(hits, [],
                         msg=f"executor must not contain payload field names "
                             f"anywhere (incl. comments): {hits}")

    def test_no_company_or_platform_keyword_in_code(self):
        src = open(SPEC_EXECUTOR_PATH).read()
        code_only = self._strip_python_noise(src)
        for kw in ["company_id ==", "platform ==", "platform==", "company =="]:
            self.assertNotIn(kw, code_only, f"executor must not branch on {kw!r}")

    def test_only_offset_strategy_advertised(self):
        # v0.1 must only accept 'offset'.
        schema = _load(SOURCE_SPEC_SCHEMA_PATH)
        st = schema["properties"]["paging"]["properties"]["strategy"]
        self.assertEqual(st.get("const"), "offset")
        self.assertNotIn("enum", st)  # enum would imply >1 option


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

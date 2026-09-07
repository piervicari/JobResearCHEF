#!/usr/bin/env python3
"""Offline Phase-1 tests: source_spec/v0.1 -> bridge -> JobResearCHEF request.

Chain under test (zero live HTTP, zero browser)::

    spec JSON -> spec_executor.render_*_request (A: plain dict)
      -> jobresearchchef_bridge.to_fetch_request (B: FetchRequest)
        -> HttpFetcher.fetch with httpx.MockTransport (C: observed wire request)

Run with the JobResearCHEF venv so the REAL FetchRequest/HttpFetcher
classes are exercised::

    PYTHONPATH=src ../.venv/bin/python -m pytest tests/          # JobResearCHEF side
    PYTHONPATH=<jobresearchchef>/research_agent_v24/src \
        <jobresearchchef>/research_agent_v24/.venv/bin/python \
        test_jobresearchchef_bridge.py                            # this file (runtime side)

When JobResearCHEF is not importable, the FetchRequest-level tests
skip (with a loud message); the pure-validation tests always run.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spec_executor as se  # noqa: E402
import jobresearchchef_bridge as bridge  # noqa: E402

# Best-effort: make the real JobResearCHEF package importable when the
# historical repo layout is present (sibling directory). Explicitly
# allowed as temporary local linking for this Phase-1 proof.
_JR_SRC = os.path.join(
    os.path.dirname(HERE), "JobResearCHEF", "research_agent_v24", "src"
)
if os.path.isdir(_JR_SRC) and _JR_SRC not in sys.path:
    sys.path.insert(0, _JR_SRC)

try:
    from research_agent.pipeline.http import FetchRequest, HttpFetcher  # noqa: E402
    import httpx  # noqa: E402
    HAVE_JOBRESEARCHCHEF = True
except Exception as exc:  # noqa: BLE001 - report reason loudly on skip
    HAVE_JOBRESEARCHCHEF = False
    _IMPORT_ERROR = str(exc)

MERCEDES_SPEC = os.path.join(HERE, "sources", "mercedes.json")
NVIDIA_SPEC = os.path.join(HERE, "sources", "nvidia.json")
MICROSOFT_SPEC = os.path.join(HERE, "candidates", "microsoft.json")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _rendered_catalog(spec_path: str, page_value: object) -> dict:
    return se.render_catalog_request(_load(spec_path), page_value)


def _rendered_detail(spec_path: str, stable_id: str) -> dict:
    rendered = se.render_detail_request(_load(spec_path), stable_id)
    assert rendered is not None
    return rendered


# ============================================================
# Mercedes / NVIDIA / Microsoft through the SAME bridge
# ============================================================

class MercedesBridgeTests(unittest.TestCase):

    def test_mercedes_catalog_bridges_to_post_fetch_request(self):
        rendered = _rendered_catalog(MERCEDES_SPEC, 1)
        req = bridge.to_fetch_request(rendered, fetch_request_cls=FetchRequest) \
            if HAVE_JOBRESEARCHCHEF else bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.url, "https://jobs.api.mercedes-benz.com/search")
        # headers preserved exactly
        self.assertEqual(req.headers, rendered["headers"])
        self.assertIn("Referer", req.headers)
        self.assertIn("Origin", req.headers)
        # JSON body preserved, SearchCriteria untouched, paging value rendered
        self.assertIsNotNone(req.json_body)
        assert req.json_body is not None
        self.assertEqual(req.json_body["SearchCriteria"], [])
        self.assertEqual(req.json_body["SearchParameters"]["FirstItem"], 1)
        self.assertEqual(req.json_body["LanguageCode"], rendered["body"]["LanguageCode"])
        self.assertIsNone(req.form_body)
        self.assertFalse(req.allow_cache)


class NvidiaBridgeTests(unittest.TestCase):

    def test_nvidia_catalog_bridges_to_get_with_query_folded(self):
        rendered = _rendered_catalog(NVIDIA_SPEC, 0)
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        self.assertEqual(req.method, "GET")
        self.assertEqual(
            req.url,
            "https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&start=0&hl=en",
        )
        self.assertEqual(req.headers, rendered["headers"])
        self.assertIsNone(req.json_body)
        self.assertIsNone(req.form_body)
        self.assertTrue(req.allow_cache)

    def test_nvidia_detail_bridges_with_interpolated_position_id(self):
        rendered = _rendered_detail(NVIDIA_SPEC, "JR12345")
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        self.assertEqual(req.method, "GET")
        self.assertIn("position_id=JR12345", req.url)
        self.assertTrue(req.url.startswith(
            "https://jobs.nvidia.com/api/pcsx/position_details?"))
        self.assertEqual(req.headers, rendered["headers"])
        self.assertIsNone(req.json_body)


class MicrosoftBridgeTests(unittest.TestCase):
    """Same bridge function, no company branching: Eightfold-family proof."""

    def test_microsoft_catalog_uses_identical_path_as_nvidia(self):
        rendered = _rendered_catalog(MICROSOFT_SPEC, 10)
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        self.assertEqual(req.method, "GET")
        self.assertEqual(
            req.url,
            "https://microsoft.eightfold.ai/api/pcsx/search"
            "?domain=microsoft.com&start=10&hl=en",
        )
        self.assertIsNone(req.json_body)

    def test_microsoft_detail_bridges(self):
        rendered = _rendered_detail(MICROSOFT_SPEC, "ms-999")
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        self.assertEqual(req.method, "GET")
        self.assertIn("position_id=ms-999", req.url)
        self.assertTrue(req.url.startswith(
            "https://microsoft.eightfold.ai/api/pcsx/position_details?"))


class _FakeFetchRequest:
    """Minimal stand-in with the real FetchRequest constructor shape."""

    def __init__(self, url, headers=None, allow_cache=True, method="GET",
                 json_body=None, form_body=None):
        self.url = url
        self.headers = headers
        self.allow_cache = allow_cache
        self.method = method
        self.json_body = json_body
        self.form_body = form_body


# ============================================================
# Fidelity A -> B -> C through the REAL HttpFetcher (MockTransport)
# ============================================================

@unittest.skipUnless(HAVE_JOBRESEARCHCHEF, "JobResearCHEF not importable")
class WireFidelityTests(unittest.TestCase):
    """The observable wire request (C) must equal the rendered dict (A)."""

    def _fetch_via_mock(self, fetch_request: FetchRequest,
                        canned: bytes) -> httpx.Request:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                content=canned,
                headers={"Content-Type": "application/json"},
                request=request,
            )

        async def run() -> None:
            fetcher = HttpFetcher(
                per_domain_min_interval_seconds=0,
                jitter_seconds=0,
                max_retries=0,
                resolve_dns=False,
                transport=httpx.MockTransport(handler),
            )
            async with fetcher:
                await fetcher.fetch(fetch_request)

        asyncio.run(run())
        self.assertEqual(len(seen), 1)
        return seen[0]

    def test_nvidia_catalog_wire_matches_rendered(self):
        rendered = _rendered_catalog(NVIDIA_SPEC, 0)
        req = bridge.to_fetch_request(rendered)
        self.assertIsInstance(req, FetchRequest)
        wire = self._fetch_via_mock(req, b'{"positions": [], "count": 0}')
        self.assertEqual(wire.method, rendered["method"])
        self.assertEqual(str(wire.url),
                         "https://jobs.nvidia.com/api/pcsx/search"
                         "?domain=nvidia.com&start=0&hl=en")
        for key, value in rendered["headers"].items():
            self.assertEqual(wire.headers.get(key), value)

    def test_mercedes_catalog_wire_matches_rendered(self):
        rendered = _rendered_catalog(MERCEDES_SPEC, 1)
        req = bridge.to_fetch_request(rendered)
        wire = self._fetch_via_mock(req, b'{"Meta": {}, "MatchedObjectDescriptor": []}')
        self.assertEqual(wire.method, "POST")
        self.assertEqual(str(wire.url), rendered["url"])
        sent_body = json.loads(wire.content.decode("utf-8"))
        self.assertEqual(sent_body, rendered["body"])
        self.assertEqual(sent_body["SearchParameters"]["FirstItem"], 1)
        for key, value in rendered["headers"].items():
            self.assertEqual(wire.headers.get(key), value)

    def test_microsoft_detail_wire_matches_rendered(self):
        rendered = _rendered_detail(MICROSOFT_SPEC, "ms-999")
        req = bridge.to_fetch_request(rendered)
        wire = self._fetch_via_mock(req, b'{}')
        self.assertEqual(wire.method, "GET")
        self.assertIn("position_id=ms-999", str(wire.url))


# ============================================================
# Source-agnostic static test (§9)
# ============================================================

class BridgeSourceAgnosticTests(unittest.TestCase):

    def test_bridge_has_no_source_specific_tokens(self):
        path = os.path.join(HERE, "jobresearchchef_bridge.py")
        with open(path) as f:
            source = f.read()
        lowered = source.lower()
        forbidden = [
            "mercedes", "nvidia", "microsoft", "cloudflare", "apple",
            "amazon", "google", "beesite", "eightfold", "greenhouse",
            "company_id", "searchcriteria", "position_id", "firstitem",
            "pcsx", "languagecode",
        ]
        for token in forbidden:
            self.assertNotIn(token, lowered,
                             msg=f"bridge must not mention source token {token!r}")
        # 'meta' only as a whole word (must not match 'method'/'metadata')
        for match in re.finditer(r"[A-Za-z_]+", lowered):
            self.assertNotEqual(match.group(0), "meta",
                                msg="bridge must not mention source token 'meta'")

    def test_bridge_has_no_source_specific_branches(self):
        path = os.path.join(HERE, "jobresearchchef_bridge.py")
        with open(path) as f:
            source = f.read()
        # No conditional dispatches on anything company/platform shaped.
        self.assertNotRegex(source, r"if\s+.*company|platform.*==|in\s+\{[^}]*nvidia",
                            msg="no company/platform branching allowed")


# ============================================================
# Immutability (§11)
# ============================================================

class BridgeImmutabilityTests(unittest.TestCase):

    def test_bridge_does_not_mutate_spec_or_rendered(self):
        spec = _load(NVIDIA_SPEC)
        spec_snapshot = copy.deepcopy(spec)
        rendered = se.render_catalog_request(spec, 0)
        rendered_snapshot = copy.deepcopy(rendered)
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        # mutate the OUTPUT; inputs must be unaffected
        req.headers["X-Injected"] = "1"
        if req.json_body is not None:
            req.json_body["X"] = 1
        self.assertEqual(spec, spec_snapshot)
        self.assertEqual(rendered, rendered_snapshot)

    def test_post_body_is_a_copy(self):
        rendered = _rendered_catalog(MERCEDES_SPEC, 1)
        cls = FetchRequest if HAVE_JOBRESEARCHCHEF else _FakeFetchRequest
        req = bridge.to_fetch_request(rendered, fetch_request_cls=cls)
        assert req.json_body is not None
        self.assertIsNot(req.json_body, rendered["body"])
        self.assertEqual(req.json_body, rendered["body"])


# ============================================================
# Error handling (§12): loud deterministic failures
# ============================================================

class BridgeErrorHandlingTests(unittest.TestCase):

    def test_unknown_method_fails(self):
        rendered = {"method": "DELETE", "url": "https://x.example.test/a",
                    "headers": {}, "query": {}, "body": {}}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_non_dict_body_fails_without_guessing(self):
        rendered = {"method": "POST", "url": "https://x.example.test/a",
                    "headers": {}, "query": {},
                    "body": "f.req=[[\"x\"]]"}  # form-style string: must NOT convert
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_list_body_fails(self):
        rendered = {"method": "POST", "url": "https://x.example.test/a",
                    "headers": {}, "query": {}, "body": [1, 2]}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_get_with_body_fails(self):
        rendered = {"method": "GET", "url": "https://x.example.test/a",
                    "headers": {}, "query": {}, "body": {"a": 1}}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_missing_field_fails(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request({"method": "GET", "url": "https://x.example.test/a"},
                                    fetch_request_cls=_FakeFetchRequest)

    def test_non_string_header_fails_without_coercion(self):
        rendered = {"method": "GET", "url": "https://x.example.test/a",
                    "headers": {"X-N": 5}, "query": {}, "body": {}}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_non_http_url_fails(self):
        rendered = {"method": "GET", "url": "ftp://x.example.test/a",
                    "headers": {}, "query": {}, "body": {}}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_none_query_value_fails(self):
        rendered = {"method": "GET", "url": "https://x.example.test/a",
                    "headers": {}, "query": {"start": None}, "body": {}}
        with self.assertRaises(bridge.BridgeError):
            bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)

    def test_query_encoding_is_rfc3986(self):
        rendered = {"method": "GET", "url": "https://x.example.test/a",
                    "headers": {}, "query": {"q": "a b&c=d", "n": 5, "f": True},
                    "body": {}}
        req = bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)
        self.assertEqual(req.url,
                         "https://x.example.test/a?q=a%20b%26c%3Dd&n=5&f=true")

    def test_existing_query_string_in_base_url_is_preserved(self):
        rendered = {"method": "GET", "url": "https://x.example.test/a?content=true",
                    "headers": {}, "query": {"start": 0}, "body": {}}
        req = bridge.to_fetch_request(rendered, fetch_request_cls=_FakeFetchRequest)
        self.assertEqual(req.url,
                         "https://x.example.test/a?content=true&start=0")


if __name__ == "__main__":
    if not HAVE_JOBRESEARCHCHEF:
        print(f"NOTE: JobResearCHEF not importable ({_IMPORT_ERROR}); "
              f"Fetcher-level tests will SKIP. "
              f"Re-run with the JobResearCHEF venv + PYTHONPATH=src for full coverage.")
    unittest.main(verbosity=2)

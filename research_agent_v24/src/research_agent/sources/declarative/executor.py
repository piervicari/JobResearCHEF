#!/usr/bin/env python3
"""
Source-agnostic offline executor for source_spec v0.1.

Given a source spec and a fixture (catalog page JSON, detail JSON),
it produces the HTTP request structure, extracts items, normalizes
them into the job schema, and decides catalog completeness.

NO HTTP is performed. The "requests" are returned as plain data
dictionaries (method, url, headers, query, body) for the caller to
send via their preferred HTTP client.

This module contains ZERO source-specific logic. It must work
identically for any two specs without ever mentioning any specific
company, platform, vendor, or payload field name.

v0.1 supports:
  - HTTP method GET or POST
  - offset pagination only (no page_number, no cursor)
  - dotted JSON paths for extraction
  - location templates (list_of_strings OR list_of_objects + template)
  - description templates (string OR list_of_blocks with relative keys)
  - static + template-driven headers/query/body
  - sequential-only safety policy
  - completeness rules: next_offset_ge_total, items_path_empty_after_total,
    last_page_shorter_than_page_size

v0.1 does NOT support:
  - cursor pagination (will land in v0.2 with a real source)
  - page_number pagination
  - dynamic auth / token rotation / captcha
  - GraphQL
  - browser-required sources
"""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone
from typing import Any


HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- generic utilities ----------

def _get(obj: Any, path: str) -> Any:
    """Resolve a dotted path against a nested dict/list structure.
    Returns None if any segment is missing.
    """
    if obj is None:
        return None
    cur = obj
    for seg in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list):
            try:
                idx = int(seg)
            except ValueError:
                return None
            cur = cur[idx] if -len(cur) <= idx < len(cur) else None
        else:
            return None
    return cur


def _set(obj: Any, path: str, value: Any) -> None:
    """In-place set at dotted path. Creates intermediate dicts.
    List segments require the slot already to be a list.
    """
    parts = path.split(".")
    cur = obj
    for seg in parts[:-1]:
        nxt = cur.get(seg) if isinstance(cur, dict) else None
        if not isinstance(nxt, dict) and not isinstance(nxt, list):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    last = parts[-1]
    if isinstance(cur, dict):
        cur[last] = value
    elif isinstance(cur, list):
        cur[int(last)] = value
    else:
        raise ValueError(f"cannot set into non-container at {path}")


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")
# Single-brace template grammar for location item_template:
# {RelKey} or {RelKey.NestedKey}. Single braces are unambiguous
# alongside the double-brace {{var}} used for request rendering.
_ITEM_VAR_RE = re.compile(r"\{\s*([a-zA-Z_][\w.]*)\s*\}")


def _interpolate(value: Any, variables: dict) -> Any:
    """Recursively interpolate {{var}} placeholders inside string values.
    Non-string leaves are passed through unchanged.
    """
    if isinstance(value, str):
        def repl(m):
            key = m.group(1)
            v = variables.get(key)
            if v is None:
                raise KeyError(f"undefined variable: {key}")
            return str(v)
        return _VAR_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, variables) for v in value]
    return value


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _HTML_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s)
    return s.strip()


# ---------- error ----------

class SourceSpecError(Exception):
    pass


# ---------- template rendering ----------

def _apply_templates(rendered: dict, spec_section: dict, variables: dict) -> None:
    """Apply spec_section['templates'] overrides IN PLACE on `rendered`.

    rendered is {headers, query, body, url}. Each template has 'at'
    (dotted path into headers/query/body/url) and 'value' (the replacement).
    The value is interpolated, then written.
    """
    templates = spec_section.get("templates") or {}
    merged_vars = dict(spec_section.get("variables") or {})
    merged_vars.update(variables or {})

    for _name, tpl in templates.items():
        at = tpl["at"]
        value = _interpolate(tpl["value"], merged_vars)
        if at.startswith("headers."):
            sub = at[len("headers."):]
            if not sub:
                raise SourceSpecError("at='headers.' requires a sub-path")
            _set(rendered["headers"], sub, value)
        elif at.startswith("query."):
            sub = at[len("query."):]
            if not sub:
                raise SourceSpecError("at='query.' requires a sub-path")
            _set(rendered["query"], sub, value)
        elif at.startswith("body."):
            sub = at[len("body."):]
            if not sub:
                raise SourceSpecError("at='body.' requires a sub-path")
            _set(rendered["body"], sub, value)
        elif at == "url":
            rendered["url"] = value
        else:
            raise SourceSpecError(f"unknown template target: {at}")


def _deep_copy_request_dict(d: dict) -> dict:
    """Copy headers/query/body/url so we never mutate the spec."""
    return {
        "headers": dict(d.get("headers") or {}),
        "query":   dict(d.get("query") or {}),
        "body":    copy.deepcopy(d.get("body") or {}),
        "url":     d.get("url"),
    }


def _render_section(spec_section: dict, variables: dict) -> dict:
    """Render one request section (catalog or detail). Returns a fresh
    dict that does NOT share any nested container with the spec."""
    rendered = _deep_copy_request_dict(spec_section)
    _apply_templates(rendered, spec_section, variables)
    # Also interpolate any {{var}} placeholders already present in static
    # headers/query/body/url values (not in templates).
    merged_vars = dict(spec_section.get("variables") or {})
    merged_vars.update(variables or {})
    rendered["headers"] = _interpolate(rendered["headers"], merged_vars)
    rendered["query"]   = _interpolate(rendered["query"],   merged_vars)
    rendered["body"]    = _interpolate(rendered["body"],    merged_vars)
    return rendered


# ---------- request rendering ----------

def render_catalog_request(spec: dict, page_value: Any, variables: dict | None = None) -> dict:
    """Render the catalog request for one page.

    The caller passes `page_value` which will be written into the slot
    pointed to by `paging.inject` — either a body path for POST sources
    or a query parameter for GET sources.
    """
    variables = dict(variables or {})
    rendered = _render_section(spec["request"], variables)
    inject = spec["paging"]["inject"]
    target = inject["target"]

    if target == "query_param":
        param_name = spec["paging"].get("page_param", "start")
        rendered["query"][param_name] = page_value
    elif target == "body_path":
        path = inject["path"]
        _set(rendered["body"], path, page_value)
    else:
        raise SourceSpecError(f"unknown paging.inject.target: {target}")

    return {
        "method": spec["request"]["method"],
        "url": rendered["url"],
        "headers": rendered["headers"],
        "query": rendered["query"],
        "body": rendered["body"],
    }


def render_detail_request(spec: dict, stable_id: Any, variables: dict | None = None) -> dict | None:
    """Render a detail request for one vacancy. Returns None if the spec
    has no detail block. stable_id is injected as a variable before
    template rendering so templates whose value is '{{stable_id}}' resolve.
    """
    detail = spec.get("detail")
    if detail is None:
        return None
    variables = dict(variables or {})
    variables["stable_id"] = stable_id
    if "language" not in variables:
        variables["language"] = spec.get("language", {}).get("default", "en")
    rendered = _render_section(detail, variables)
    inter = detail["interpolation"]
    target = inter["target"]

    if target == "query_param":
        rendered["query"][inter["name"]] = stable_id
    elif target == "body_path":
        _set(rendered["body"], inter["name"], stable_id)
    else:
        raise SourceSpecError(f"unknown detail.interpolation.target: {target}")

    return {
        "method": detail["method"],
        "url": rendered["url"],
        "headers": rendered["headers"],
        "query": rendered["query"],
        "body": rendered["body"],
    }


# ---------- pagination driver (offset only) ----------

def pagination_iterator(spec: dict, total_count: int):
    """Yield successive offset values for an offset-paginated source.

    Yields only the offsets the runtime must actually request. Whether
    a final empty-after-total probe is yielded depends on whether the
    spec's completeness rules include 'items_path_empty_after_total' —
    if they don't, no probe is needed and we stop at the last data
    page.
    """
    if spec["paging"]["strategy"] != "offset":
        raise SourceSpecError(
            f"v0.1 only supports strategy=offset, got {spec['paging']['strategy']}"
        )
    page_size = spec["paging"]["page_size"]
    first = spec["paging"]["first_page_value"]
    rule_kinds = {r["kind"] for r in spec["completeness"]["rules"]}

    cur = first
    last_data_offset = first + ((max(0, total_count - first - 1) // page_size) * page_size)
    while cur <= last_data_offset:
        yield cur
        cur += page_size

    # Plus the empty-after-total probe page ONLY when the completeness
    # rules require positive evidence of termination via an empty page.
    if "items_path_empty_after_total" in rule_kinds:
        yield cur


def total_request_count(spec: dict, total_count: int) -> int:
    """How many catalog requests a fully authoritative full-catalog sweep
    will issue, assuming the runtime honours items_path_empty_after_total.
    """
    if spec["paging"]["strategy"] != "offset":
        raise SourceSpecError("not offset")
    page_size = spec["paging"]["page_size"]
    first = spec["paging"]["first_page_value"]
    n_data_pages = ((max(0, total_count - first - 1) // page_size) + 1
                    if total_count >= first else 0)
    rule_kinds = {r["kind"] for r in spec["completeness"]["rules"]}
    extra = 1 if "items_path_empty_after_total" in rule_kinds else 0
    return n_data_pages + extra


# ---------- extraction ----------

def extract_page(spec: dict, response: dict) -> tuple[list[dict], int]:
    """Extract (items, total) from a page response using the spec.

    Items returned to the caller are UNWRAPPED: each item is the inner
    descriptor. This keeps the spec's extraction paths simple and
    source-agnostic — no vendor wrapper field name ever needs to appear
    in any extraction path.

    If the page wrapper's 'items' path points directly to the descriptor
    list, items pass through. If each item is a single-key wrapper
    around the descriptor, we unwrap to that single key.
    """
    extraction = spec["extraction"]
    if "page_wrapper" in extraction:
        items = _get(response, extraction["page_wrapper"]["items"]) or []
        total = _get(response, extraction["page_wrapper"]["total"]) or 0
    else:
        items = _get(response, extraction["item_path"]) or []
        total = _get(response, extraction["total_path"]) or 0
    if not isinstance(items, list):
        items = []
    if not isinstance(total, int):
        try:
            total = int(total)
        except Exception:
            total = 0
    # Unwrap common single-key wrappers so extraction paths are
    # source-agnostic. Only the FIRST level is unwrapped; deeper
    # wrapping is described declaratively via extraction paths.
    unwrapped = []
    for raw in items:
        if isinstance(raw, dict) and len(raw) == 1:
            only_key = next(iter(raw.keys()))
            unwrapped.append(raw[only_key])
        else:
            unwrapped.append(raw)
    return unwrapped, total


# ---- location extraction (declarative) ----

def _interpolate_item_template(template: str, item: dict) -> str:
    """Substitute {RelKey} or {RelKey.NestedKey} with the value from item.

    Single-brace placeholders. Used by extraction.locations.shape=
    list_of_objects to render each location object into a string. The
    keys are resolved against the location OBJECT itself, not the parent
    item.
    """
    return _ITEM_VAR_RE.sub(lambda m: str(_get(item, m.group(1)) or ""), template)


def extract_locations(spec: dict, item: dict) -> list[str]:
    """Extract a list of human-readable location strings using the
    spec's `extraction.locations` declaration. Pure-data; the runtime
    knows no payload field names."""
    loc = spec["extraction"].get("locations")
    if not loc:
        return []
    raw = None
    for p in [loc["path"]] + list(loc.get("fallback_paths") or []):
        raw = _get(item, p)
        if raw:
            break
    if not raw:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    shape = loc.get("shape", "list_of_strings")
    if shape == "list_of_strings":
        return [str(x) for x in raw if x]
    if shape == "list_of_objects":
        tmpl = loc.get("item_template")
        if not tmpl:
            return []
        out = []
        for obj in raw:
            if not isinstance(obj, dict):
                continue
            # The template is rendered against the location object ITSELF,
            # not the parent item.
            rendered = _interpolate_item_template(tmpl, obj)
            rendered = rendered.strip()
            if rendered:
                out.append(rendered)
        return out
    raise SourceSpecError(f"unknown locations.shape: {shape}")


# ---- description extraction (declarative) ----

def _try_paths(item: dict, paths: list[str]) -> Any:
    for p in paths:
        v = _get(item, p)
        if v:
            return v
    return None


def extract_description(spec: dict, item: dict, override_path: str | None = None) -> tuple[str, str, bool]:
    """Return (description, qualifications, complete) extracted from `item`.

    The spec declares extraction.description (path + shape + strip_html).
    override_path, when given, REPLACES the primary path (used when
    extracting from a detail response whose key differs).

    complete=True iff BOTH description and qualifications were non-empty.
    """
    decl = spec["extraction"].get("description")
    if not decl:
        return "", "", False
    primary_path = override_path or decl["path"]
    paths = [primary_path] + list(decl.get("fallback_paths") or [])
    raw = _try_paths(item, paths)
    strip = bool(decl.get("strip_html", True))
    shape = decl.get("shape", "string")

    if shape == "string":
        if raw is None:
            return "", "", False
        text = str(raw)
        if strip:
            text = _strip_html(text)
        # When shape=string we cannot split tasks vs qualifications;
        # put everything in description and leave qualifications empty.
        return text, "", bool(text.strip())

    if shape == "list_of_blocks":
        if not isinstance(raw, list) or not raw:
            return "", "", False
        # The relative keys MUST be declared in the spec; we do NOT
        # default them here to keep the executor source-agnostic.
        if "tasks_relative_key" not in decl or "qualifications_relative_key" not in decl:
            raise SourceSpecError(
                "extraction.description.shape=list_of_blocks requires "
                "tasks_relative_key AND qualifications_relative_key in the spec"
            )
        tasks_key = decl["tasks_relative_key"]
        quals_key = decl["qualifications_relative_key"]
        joiner = decl.get("join_separator", "\n\n")
        tasks_parts: list[str] = []
        quals_parts: list[str] = []
        for block in raw:
            if not isinstance(block, dict):
                continue
            t = block.get(tasks_key) or ""
            q = block.get(quals_key) or ""
            if strip:
                if t: t = _strip_html(str(t))
                if q: q = _strip_html(str(q))
            else:
                t = str(t); q = str(q)
            if t.strip(): tasks_parts.append(t)
            if q.strip(): quals_parts.append(q)
        desc = joiner.join(tasks_parts) if tasks_parts else ""
        quals = joiner.join(quals_parts) if quals_parts else ""
        return desc, quals, bool(desc.strip() and quals.strip())

    raise SourceSpecError(f"unknown description.shape: {shape}")


# ---- generic field extractors ----

def _convert_date(value: Any, date_format: str) -> str | None:
    """Convert to ISO 8601 (date) string. None if missing/invalid."""
    if value is None or value == "":
        return None
    try:
        if date_format == "unix_seconds":
            return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
        if date_format == "iso_date":
            s = str(value)
            if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
                return s
            return s[:10]
        if date_format == "iso_datetime":
            return str(value)
    except Exception:
        return None
    return None


def extract_item(spec: dict, item: dict) -> dict:
    """Extract all spec-declared fields from a single catalog item.
    Returns a partial normalized job dict (without detail_complete /
    source_last_seen_at — those are set by merge / caller).
    """
    ex = spec["extraction"]
    out: dict[str, Any] = {}

    # stable_id with fallback chain through secondary_id_paths
    sid = _get(item, ex["stable_id_path"])
    if sid is None:
        for alt in ex.get("secondary_id_paths") or []:
            sid = _get(item, alt)
            if sid is not None:
                break

    out["source_job_id"] = str(sid) if sid is not None else None
    out["source_secondary_ids"] = [
        str(_get(item, p)) for p in ex.get("secondary_id_paths") or []
        if _get(item, p) is not None
    ]

    out["title"] = _get(item, ex["title_path"])

    if ex.get("department_path"):
        out["department"] = _get(item, ex["department_path"])
    if ex.get("organization_path"):
        out["organization"] = _get(item, ex["organization_path"])

    out["locations"] = extract_locations(spec, item)

    if ex.get("publication_date_path") and ex.get("date_format"):
        out["publication_date"] = _convert_date(
            _get(item, ex["publication_date_path"]), ex["date_format"]
        )
    if ex.get("expiration_date_path") and ex.get("date_format"):
        out["expiration_date"] = _convert_date(
            _get(item, ex["expiration_date_path"]), ex["date_format"]
        )

    ou = None
    if ex.get("official_url_path"):
        ou = _get(item, ex["official_url_path"])
    if not ou and ex.get("official_url_template"):
        ou = ex["official_url_template"].replace("{{stable_id}}", str(sid) if sid is not None else "")
    out["official_url"] = ou

    if ex.get("apply_url_path"):
        au = _get(item, ex["apply_url_path"])
        if isinstance(au, list) and au:
            au = au[0]
        out["apply_url"] = au

    if ex.get("language_path"):
        lang_val = _get(item, ex["language_path"])
        if isinstance(lang_val, dict):
            lang_val = lang_val.get("Code")
        if lang_val is not None:
            out["language"] = str(lang_val)

    # description from the catalog item (when description_in_catalog=true)
    desc, quals, complete = extract_description(spec, item)
    if desc:
        out["description"] = desc
    if quals:
        out["qualifications"] = quals
    out["detail_complete"] = complete

    return out


def merge_detail_into_job(spec: dict, job: dict, detail_response: dict) -> dict:
    """Take a normalized job dict and a detail response, and overlay
    description / qualifications. detail.description_path (if present)
    overrides the primary path declared in extraction.description."""
    detail = spec.get("detail") or {}
    out = dict(job)
    override_path = detail.get("description_path")
    desc, quals, complete = extract_description(spec, detail_response, override_path=override_path)
    if desc:
        out["description"] = desc
    if quals:
        out["qualifications"] = quals
    out["detail_complete"] = complete
    return out


def normalize_job(spec: dict, partial: dict, source_last_seen_at: str) -> dict:
    """Add company_id, source_platform, source_last_seen_at. Defaults for
    optional fields. Coerce types."""
    out = dict(partial)
    out["company_id"] = spec["company"]["id"]
    out["source_platform"] = spec["platform"]["name"]
    out["source_last_seen_at"] = source_last_seen_at
    out.setdefault("description", "")
    out.setdefault("qualifications", "")
    out.setdefault("locations", [])
    out.setdefault("source_secondary_ids", [])
    out.setdefault("detail_complete", False)
    if out.get("source_job_id") is not None:
        out["source_job_id"] = str(out["source_job_id"])
    return out


# ---------- completeness ----------

def evaluate_completeness(spec: dict, history: list[dict]) -> tuple[bool, str]:
    """Decide whether the catalog was fully traversed.

    history entries: {page_value, items_count, total}.

    Rules (v0.1):
      - next_offset_ge_total: pages up to (and including) the one that
        contains the last item were all fetched.
      - last_page_shorter_than_page_size: the last non-empty page was
        shorter than page_size OR an empty-after-total page was observed.
      - items_path_empty_after_total: the runtime fetched the page
        immediately after total and received zero items.

    ALL rules listed in completeness.rules must pass.
    """
    if not history:
        return False, "no pages were fetched"

    rule_kinds = {r["kind"] for r in spec["completeness"]["rules"]}
    final_total = max(h["total"] for h in history)
    page_size = spec["paging"]["page_size"]
    first = spec["paging"]["first_page_value"]

    if "next_offset_ge_total" in rule_kinds:
        # BUGFIX (Phase 2, generic — not a v0.2 feature): the data pages
        # that cover `total` items are exactly the offsets emitted by
        # pagination_iterator(), i.e. first + k*page_size for k in
        # range(n_data_pages) with n_data_pages = 0 when total < first
        # else (total - first - 1)//page_size + 1. The previous
        # `while o <= final_total` demanded one extra data page whenever
        # total fell exactly on a page boundary (zero-based:
        # total == page_size needs only page 0, not pages 0 AND
        # page_size). This matches the iterator bit-for-bit so the two
        # can never disagree again. Note the max(0, ...) guard, mirrored
        # from pagination_iterator: when total == first there is exactly
        # one item and one data page; without the guard, Python floor
        # division turns (total-first-1) == -1 into -1 and the single
        # real data page would be skipped.
        if final_total >= first:
            n_data_pages = (max(0, final_total - first - 1) // page_size) + 1
            needed = [first + k * page_size for k in range(n_data_pages)]
        else:
            needed = []
        seen = {h["page_value"] for h in history}
        missing = [p for p in needed if p not in seen]
        if missing:
            return False, f"missing pages: {missing[:5]}"

    if "last_page_shorter_than_page_size" in rule_kinds:
        non_empty = [h for h in history if h["items_count"] > 0]
        if not non_empty:
            return False, "no non-empty page observed"
        last = max(non_empty, key=lambda h: h["page_value"])
        last_is_partial = last["items_count"] < page_size
        # BUGFIX (Phase 2 hardening, generic — same family as the
        # next_offset_ge_total fix above): the terminal empty-after-total
        # probe sits exactly AT total on an exact page boundary
        # (zero-based: probe offset == total), so `>` never sees it.
        # `>=` recognizes the probe without changing any non-boundary
        # outcome (there the probe is always strictly greater).
        observed_empty_after = any(
            h["items_count"] == 0 and h["page_value"] >= final_total
            for h in history
        )
        if not last_is_partial and not observed_empty_after:
            return False, "last non-empty page was full and no empty-after-total page observed"

    if "items_path_empty_after_total" in rule_kinds:
        # Same boundary arithmetic as above (and as pagination_iterator):
        # the probe page is the first offset AFTER the last data page.
        # The previous `while o <= final_total` loop placed the probe one
        # full page too far whenever total fell exactly on a boundary.
        if final_total >= first:
            n_data_pages = (max(0, final_total - first - 1) // page_size) + 1
        else:
            n_data_pages = 0
        page_after_total = first + n_data_pages * page_size
        if not any(h["page_value"] == page_after_total and h["items_count"] == 0
                   for h in history):
            return False, f"never fetched the empty-after-total page ({page_after_total})"

    return True, "all rules satisfied"


def closed_decision(spec: dict, complete: bool) -> dict:
    """Return the CLOSED decision policy for this source in this run."""
    auth = bool(spec.get("open_closed_authoritative"))
    sot = spec.get("source_of_truth")
    if auth and sot == "full_catalog" and complete:
        return {"may_mark_closed": True, "reason": "authoritative full catalog, complete"}
    if auth and not complete:
        return {"may_mark_closed": False,
                "reason": "authoritative source but pagination incomplete — skip_closed"}
    if not auth:
        return {"may_mark_closed": False,
                "reason": "source is not authoritative for OPEN/CLOSED"}
    return {"may_mark_closed": False, "reason": "unknown"}


# ---------- validation against job.schema.json ----------

def validate_against_job_schema(job: dict, job_schema: dict) -> list[str]:
    """Tiny JSON-Schema subset validator for the normalized job."""
    errors: list[str] = []
    required = job_schema.get("required", [])
    for r in required:
        if r not in job:
            errors.append(f"missing required field: {r}")
        elif job[r] is None:
            errors.append(f"required field is null: {r}")
    props = job_schema.get("properties", {})
    for k, sub in props.items():
        if k not in job:
            continue
        v = job[k]
        if v is None:
            continue
        t = sub.get("type")
        if t == "string" and not isinstance(v, str):
            errors.append(f"{k}: expected string, got {type(v).__name__}")
        elif t == "array" and not isinstance(v, list):
            errors.append(f"{k}: expected array, got {type(v).__name__}")
    for k in ("official_url", "apply_url"):
        v = job.get(k)
        if v and isinstance(v, str) and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", v):
            errors.append(f"{k}: not a URI: {v!r}")
    return errors

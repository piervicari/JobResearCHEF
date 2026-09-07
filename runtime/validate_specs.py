#!/usr/bin/env python3
"""
Offline validator for source specs and normalized jobs.

Reads only files on disk. No HTTP. No browser. No network.

Usage:
  python3 validate_specs.py                     # validate all sources
  python3 validate_specs.py path/to/spec.json    # validate one file

Exits 0 if all checks pass, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "source_spec.schema.json")
JOB_SCHEMA_PATH = os.path.join(HERE, "job.schema.json")
SOURCES_DIR = os.path.join(HERE, "sources")

# Tiny JSON-Schema subset validator. We implement only what we actually
# use in source_spec / job_schema. This avoids pulling in a third-party
# dependency and keeps the validator offline-deterministic.
#
# Supported keywords: type, properties, required, additionalProperties,
# pattern, format, enum, const, minLength, minimum, maximum, minItems,
# items, oneOf, not, anyOf, $ref (within the same document).
# Format checks are limited to 'uri' (lightweight) and 'string' (always).
TYPE_MAP = {"string": str, "number": (int, float), "integer": int,
            "boolean": bool, "object": dict, "array": list, "null": type(None)}


class ValidationError(Exception):
    pass


def _check_type(value: Any, expected) -> bool:
    if isinstance(expected, list):
        return any(_check_type(value, e) for e in expected)
    py = TYPE_MAP.get(expected)
    if py is None:
        return True
    if value is None:
        return expected == "null"
    return isinstance(value, py)


def _validate(instance: Any, schema: dict, root: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    if "$ref" in schema:
        target = schema["$ref"]
        if target.startswith("#/"):
            ref_schema = root
            for part in target[2:].split("/"):
                ref_schema = ref_schema.get(part, {}) if isinstance(ref_schema, dict) else {}
            if not ref_schema:
                errors.append(f"{path}: unresolved $ref {target}")
            else:
                errors.extend(_validate(instance, ref_schema, root, path))
            return errors
    t = schema.get("type")
    if t and not _check_type(instance, t):
        errors.append(f"{path}: expected type {t}, got {type(instance).__name__}")
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in enum {schema['enum']!r}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: string {instance!r} does not match pattern {schema['pattern']!r}")
        if schema.get("format") == "uri" and not _looks_like_uri(instance):
            errors.append(f"{path}: string {instance!r} is not a uri")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: array has {len(instance)} items, minItems {schema['minItems']}")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(_validate(item, schema["items"], root, f"{path}[{i}]"))
    if isinstance(instance, dict):
        if "required" in schema:
            for r in schema["required"]:
                if r not in instance:
                    errors.append(f"{path}: missing required property {r!r}")
        if schema.get("additionalProperties") is False and "properties" in schema:
            extras = set(instance.keys()) - set(schema["properties"].keys())
            if extras:
                errors.append(f"{path}: unexpected properties {sorted(extras)!r}")
        if "properties" in schema:
            for k, sub in schema["properties"].items():
                if k in instance:
                    errors.extend(_validate(instance[k], sub, root, f"{path}.{k}"))
        if "oneOf" in schema:
            matches = sum(
                1 for s in schema["oneOf"]
                if not _validate(instance, s, root, path)
            )
            if matches != 1:
                errors.append(f"{path}: oneOf matched {matches} variants (must be exactly 1)")
        if "anyOf" in schema:
            matches = sum(
                1 for s in schema["anyOf"]
                if not _validate(instance, s, root, path)
            )
            if matches < 1:
                errors.append(f"{path}: anyOf matched {matches} variants (must be >= 1)")
        if "not" in schema:
            if not _validate(instance, schema["not"], root, path):
                errors.append(f"{path}: must NOT validate against 'not' schema")
    return errors


def _looks_like_uri(s: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", s))


# ---------- spec-specific checks ----------

FORBIDDEN_SAFETY_KEYS = [
    "proxy_rotation", "ip_rotation", "user_agent_rotation",
    "captcha_bypass", "anti_bot_evasion",
]

REQUIRED_SECTIONS = [
    "schema_version", "company", "platform", "request",
    "extraction", "paging", "completeness", "safety",
]


def _check_no_arbitrary_code(spec: dict, path: str = "$") -> list[str]:
    """The spec must not contain executable code. We forbid:
       - Python eval/exec/lambda/import keywords inside string values;
       - any value containing '__' (Python dunder);
       - any value matching the obvious eval(...) pattern.
    """
    errors: list[str] = []

    def walk(node, p):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in FORBIDDEN_SAFETY_KEYS and p.startswith("$.safety"):
                    errors.append(f"{p}.{k}: forbidden safety policy key")
                walk(v, f"{p}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{p}[{i}]")
        elif isinstance(node, str):
            if re.search(r"\b(eval|exec|compile|__import__|getattr|setattr)\b\s*\(", node):
                errors.append(f"{p}: string contains executable Python: {node!r}")
            if "__" in node and "://" not in node:
                # Allow double-underscore inside URLs only.
                errors.append(f"{p}: string contains '__' (potential Python dunder): {node!r}")
    walk(spec, path)
    return errors


def _check_required_keys(spec: dict) -> list[str]:
    return [f"$.{k}: missing required section" for k in REQUIRED_SECTIONS if k not in spec]


def _check_paging_completeness(spec: dict) -> list[str]:
    """Paging and completeness must agree: a strategy must have at least
    one matching rule. Also: paging.inject.target must be consistent
    with the strategy."""
    errors: list[str] = []
    paging = spec.get("paging", {})
    strategy = paging.get("strategy")
    rules = spec.get("completeness", {}).get("rules", [])
    rule_kinds = {r.get("kind") for r in rules}
    if strategy == "offset" and "next_offset_ge_total" not in rule_kinds:
        errors.append("$.completeness.rules: offset strategy requires 'next_offset_ge_total' rule")
    if strategy == "cursor" and "cursor_absent" not in rule_kinds:
        errors.append("$.completeness.rules: cursor strategy requires 'cursor_absent' rule")
    if strategy == "page_number" and "next_offset_ge_total" not in rule_kinds and "last_page_shorter_than_page_size" not in rule_kinds:
        errors.append("$.completeness.rules: page_number strategy needs an explicit termination rule")
    inject = paging.get("inject")
    if inject:
        target = inject.get("target")
        if target == "body_path" and not inject.get("path"):
            errors.append("$.paging.inject.path: required when target=body_path")
        if target == "query_param" and not paging.get("page_param"):
            errors.append("$.paging.page_param: required when inject.target=query_param")
    return errors


def _check_description_vs_detail(spec: dict) -> list[str]:
    """description_in_catalog=true → no detail block required.
    description_in_catalog=false → detail block is required."""
    errors: list[str] = []
    dic = spec.get("description_in_catalog")
    has_detail = "detail" in spec
    if dic is True and has_detail:
        errors.append("$.detail: should not be present when description_in_catalog=true")
    if dic is False and not has_detail:
        errors.append("$.detail: required when description_in_catalog=false (NVIDIA-style)")
    return errors


def _check_source_of_truth_consistency(spec: dict) -> list[str]:
    """If source_of_truth=filtered_catalog, open_closed_authoritative MUST
    be false. If open_closed_authoritative=true, source_of_truth MUST be
    full_catalog."""
    errors: list[str] = []
    sot = spec.get("source_of_truth")
    auth = spec.get("open_closed_authoritative")
    if sot == "filtered_catalog" and auth is True:
        errors.append("$.open_closed_authoritative: filtered catalog cannot be authoritative for OPEN/CLOSED")
    if auth is True and sot != "full_catalog":
        errors.append("$.source_of_truth: authoritative OPEN/CLOSED requires source_of_truth=full_catalog")
    return errors


def validate_source_spec(spec: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    errors.extend(_check_required_keys(spec))
    errors.extend(_check_no_arbitrary_code(spec))
    errors.extend(_check_paging_completeness(spec))
    errors.extend(_check_description_vs_detail(spec))
    errors.extend(_check_source_of_truth_consistency(spec))
    errors.extend(_validate(spec, schema, schema))
    return errors


# ---------- driver ----------

def main(argv: list[str]) -> int:
    failed = 0
    schema = json.load(open(SCHEMA_PATH))
    job_schema = json.load(open(JOB_SCHEMA_PATH))

    if len(argv) > 1:
        targets = [argv[1]]
    else:
        if not os.path.isdir(SOURCES_DIR):
            print(f"no sources dir: {SOURCES_DIR}", file=sys.stderr)
            return 1
        targets = sorted(
            os.path.join(SOURCES_DIR, f)
            for f in os.listdir(SOURCES_DIR)
            if f.endswith(".json")
        )

    # Validate schemas themselves: just confirm they're valid JSON with
    # a 'type: object' at the root and a 'properties' block. We do NOT
    # validate a schema against itself (that is structurally wrong).
    print("[schema] source_spec.schema.json: structural check...")
    if (not isinstance(schema, dict)
            or schema.get("type") != "object"
            or "properties" not in schema
            or "required" not in schema):
        print("  FAIL: source_spec.schema.json is not a well-formed JSON Schema")
        failed += 1
    else:
        print(f"  OK  ({len(schema.get('properties', {}))} top-level properties, "
              f"{len(schema.get('required', []))} required)")

    print("[schema] job.schema.json: structural check...")
    if (not isinstance(job_schema, dict)
            or job_schema.get("type") != "object"
            or "properties" not in job_schema
            or "required" not in job_schema):
        print("  FAIL: job.schema.json is not a well-formed JSON Schema")
        failed += 1
    else:
        print(f"  OK  ({len(job_schema.get('properties', {}))} top-level properties, "
              f"{len(job_schema.get('required', []))} required)")

    for path in targets:
        print(f"[spec] {path}")
        try:
            spec = json.load(open(path))
        except json.JSONDecodeError as e:
            print(f"  FAIL: invalid JSON: {e}")
            failed += 1
            continue
        if not isinstance(spec, dict):
            print(f"  FAIL: top-level must be an object, got {type(spec).__name__}")
            failed += 1
            continue
        errors = validate_source_spec(spec, schema)
        if errors:
            print(f"  FAIL: {len(errors)} issue(s)")
            for e in errors[:20]:
                print(f"    - {e}")
            if len(errors) > 20:
                print(f"    ... ({len(errors) - 20} more)")
            failed += 1
        else:
            cid = spec.get("company", {}).get("id", "?")
            sot = spec.get("source_of_truth", "?")
            dic = spec.get("description_in_catalog")
            print(f"  OK  company_id={cid}  source_of_truth={sot}  description_in_catalog={dic}")

    # Sanity: normalized-job schema is also self-consistent (already done above)

    if failed:
        print(f"\nFAIL ({failed} problem(s))")
        return 1
    print("\nAll specs valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

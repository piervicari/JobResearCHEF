"""DeclarativeSourceAdapter: source_spec/v0.1 as a sibling SourceAdapter.

Single execution path for every bound spec: whatever source is bound,
it traverses this exact code; there is no per-company or per-platform
branch (enforced by a static token scan in the test suite). The rest
of the pipeline only ever sees ``RawJob`` and ``AdapterScanResult``.

Identity rule (stable across SourceSpec schema upgrades by design):
``RawJob.source`` is ``declarative:<company_id>``. The schema version
is deliberately NOT part of the identity, so a v0.1 -> v0.2 upgrade
of the same company's spec does not fork its jobs into new SourceJob
rows. The native stable id stays in ``RawJob.source_job_id``
(unchanged), the first secondary id (when unambiguous) goes to
``RawJob.ats_job_id``, and the full secondary list plus the complete
normalized job plus the native catalog item are preserved in
``RawJob.raw_payload``.

Semantic-compatibility rule (no DB migration in Phase 2): the legacy
``RawJob.description`` carries the composed semantic text
``description`` + ``"\\n\\nQualifications:\\n"`` + ``qualifications``
(heading appended only when qualifications are non-empty), while
``raw_payload`` keeps ``description`` and ``qualifications`` as
separate fields. Because the legacy observation hash covers
``RawJob.description``, a qualifications-only change alters the hash.

Catalog-scan policy: offset pagination only (whatever v0.1 renders);
detail endpoints are NEVER fetched during ``scan()`` — jobs whose
spec has ``description_in_catalog=false`` get an empty description
with ``detail_complete=false`` in the payload, and detail hydration
for new/changed/candidate jobs is a later phase. Use
``render_detail_fetch()`` explicitly for one-off detail rendering;
``scan()`` does not call it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from research_agent.sources.ats.common import (
    AdapterHttpError,
    AdapterSchemaError,
    parse_datetime,
    require_mapping,
    require_success,
    string_value,
)
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)
from research_agent.sources.declarative import bridge, executor

_HERE = Path(__file__).resolve().parent
DEFAULT_BINDINGS_PATH = _HERE / "bindings.json"

QUALIFICATIONS_HEADING = "\n\nQualifications:\n"


def compose_semantic_text(description: str, qualifications: str) -> str:
    """Deterministic description+qualifications composition (source-agnostic).

    Heading appended only when qualifications are non-empty; no
    duplication, no trailing blank lines beyond the single separator.
    """
    text = description or ""
    quals = qualifications or ""
    if not quals.strip():
        return text
    if text.strip():
        return text + QUALIFICATIONS_HEADING + quals
    return "Qualifications:\n" + quals


def declarative_source_name(spec: dict) -> str:
    """Namespace rule: ``declarative:<company_id>`` (no schema version)."""
    try:
        company_id = spec["company"]["id"]
    except (KeyError, TypeError) as exc:
        raise AdapterSchemaError(f"declarative spec is missing company.id: {exc}") from exc
    if not isinstance(company_id, str) or not company_id:
        raise AdapterSchemaError("declarative spec company.id must be a non-empty string")
    return f"declarative:{company_id}"


def normalized_job_to_raw_job(spec: dict, normalized: dict, native_item: Any) -> RawJob:
    """Convert one normalized (job.schema-shaped) job to a legacy RawJob.

    No per-company branching: every field comes from the normalized
    job or the spec's company block. Raises AdapterSchemaError when the
    stable id or title is missing (same strictness as legacy adapters).
    """
    source = declarative_source_name(spec)
    company_name = string_value((spec.get("company") or {}).get("name"))

    source_job_id = normalized.get("source_job_id")
    if source_job_id is None or str(source_job_id) == "":
        raise AdapterSchemaError(f"{source}: catalog item is missing its stable id")
    title = normalized.get("title") or ""
    if not str(title).strip():
        raise AdapterSchemaError(f"{source}: catalog item {source_job_id!r} is missing its title")

    locations = normalized.get("locations") or []
    location = " | ".join(str(part) for part in locations if str(part).strip())

    description = normalized.get("description") or ""
    qualifications = normalized.get("qualifications") or ""
    semantic_text = compose_semantic_text(str(description), str(qualifications))

    official_url = normalized.get("official_url") or ""
    apply_url = normalized.get("apply_url") or official_url

    secondary = normalized.get("source_secondary_ids") or []
    secondary = [str(value) for value in secondary]

    provenance = dict(normalized)
    provenance["_declarative"] = {
        "schema_version": spec.get("schema_version", ""),
        "company_id": spec["company"]["id"],
        "source_platform": normalized.get("source_platform", ""),
        "detail_complete": bool(normalized.get("detail_complete", False)),
    }
    provenance["_source_native"] = native_item

    return RawJob(
        source=source,
        source_job_id=str(source_job_id),
        source_url=str(official_url),
        apply_url=str(apply_url),
        title=str(title),
        company=company_name,
        location=location,
        description=semantic_text,
        posted_at=parse_datetime(normalized.get("publication_date")),
        ats_job_id=(secondary[0] if len(secondary) == 1 else None),
        raw_payload=provenance,
    )


@dataclass(frozen=True)
class DeclarativeSourceBinding:
    """Explicit portal-URL -> spec-file binding. Exact match only."""

    normalized_jobs_url: str
    spec_path: str  # relative to the declarative package dir, e.g. "specs/<company>.json"


def _load_spec(base_dir: Path, spec_path: str) -> dict:
    path = base_dir / spec_path
    try:
        with open(path, encoding="utf-8") as handle:
            spec = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"declarative binding spec unreadable: {path} ({exc})") from exc
    if not isinstance(spec, dict):
        raise ValueError(f"declarative binding spec is not an object: {path}")
    for key in ("company", "request", "paging", "extraction", "completeness"):
        if key not in spec:
            raise ValueError(f"declarative binding spec {path} is missing {key!r}")
    company = spec["company"]
    if not isinstance(company, dict) or not company.get("id"):
        raise ValueError(f"declarative binding spec {path} is missing company.id")
    return spec


class DeclarativeSourceAdapter:
    """One shared adapter for all explicitly bound source specs."""

    name = "declarative"
    max_pages = 2000  # own ceiling; PortalScanContext caps always win

    def __init__(
        self,
        bindings: Iterable[DeclarativeSourceBinding],
        *,
        base_dir: str | Path | None = None,
    ) -> None:
        base = Path(base_dir) if base_dir is not None else _HERE
        self._specs: dict[str, dict] = {}
        for binding in bindings:
            if not binding.normalized_jobs_url or not binding.spec_path:
                raise ValueError(f"declarative binding is incomplete: {binding!r}")
            if binding.normalized_jobs_url in self._specs:
                raise ValueError(
                    "duplicate declarative binding for "
                    f"{binding.normalized_jobs_url!r}: bindings must be unique, "
                    "first match would otherwise shadow the rest"
                )
            self._specs[binding.normalized_jobs_url] = _load_spec(base, binding.spec_path)

    @property
    def bound_portal_urls(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def supports(self, target: PortalTarget) -> bool:
        # EXACT match on the configured portal URL. Deliberately no host
        # similarity, no ATS-family check, no substring/regex: anything
        # fuzzier would reintroduce the universal resolver through the
        # back door. Unbound portals (even same-host/same-family ones)
        # are not selected.
        return target.normalized_jobs_url in self._specs

    def spec_for(self, target: PortalTarget) -> dict:
        try:
            return self._specs[target.normalized_jobs_url]
        except KeyError:
            raise AdapterSchemaError(
                f"no declarative binding for {target.normalized_jobs_url!r}"
            ) from None

    def preflight(self, target: PortalTarget, effective: Any) -> Any:
        """Fail-closed safety verdict for one bound target (no I/O).

        Compares the bound spec's safety requirements against the
        effective scanner safety (see safety.preflight_safety). Future
        live harnesses must call this before scan(); scan() itself
        stays settings-free on purpose.
        """
        from research_agent.sources.declarative import safety as _safety

        return _safety.preflight_safety(self.spec_for(target), effective)

    def render_detail_fetch(self, target: PortalTarget, stable_id: str) -> Any:
        """Render (not send) the detail FetchRequest for one stable id.

        Explicit one-off helper. ``scan()`` never calls it: catalog
        scans do not N+1 hydrate detail endpoints (see module docstring).
        """
        spec = self.spec_for(target)
        try:
            rendered = executor.render_detail_request(spec, stable_id)
        except executor.SourceSpecError as exc:
            raise AdapterSchemaError(f"{self.spec_label(spec)}: {exc}") from exc
        if rendered is None:
            raise AdapterSchemaError(
                f"{self.spec_label(spec)}: spec declares no detail block"
            )
        try:
            return bridge.to_fetch_request(rendered)
        except bridge.BridgeError as exc:
            raise AdapterSchemaError(f"{self.spec_label(spec)}: {exc}") from exc

    @staticmethod
    def spec_label(spec: dict) -> str:
        try:
            return str(spec["company"]["id"])
        except (KeyError, TypeError):
            return "<unknown spec>"

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        spec = self.spec_for(target)
        label = self.spec_label(spec)
        try:
            page_size = spec["paging"]["page_size"]
            first = spec["paging"]["first_page_value"]
            rule_kinds = {rule["kind"] for rule in spec["completeness"]["rules"]}
            authoritative = bool(spec.get("open_closed_authoritative"))
        except (KeyError, TypeError, AttributeError) as exc:
            raise AdapterSchemaError(f"{label}: malformed paging/completeness: {exc}") from exc

        warnings: list[str] = []
        collected: list[RawJob] = []
        history: list[dict] = []
        fetched: set[Any] = set()
        probe_rule = "items_path_empty_after_total" in rule_kinds
        page_limit = context.page_limit(self.max_pages)
        job_cap = context.max_jobs_per_portal
        seen_at = datetime.now(UTC).isoformat()

        first_total: Any = None
        total_changed = False
        truncated_by_cap = False
        pagination_anomaly = False

        try:
            current: Any = first
            pages = 0
            while True:
                if pages >= page_limit:
                    warnings.append(
                        f"{label}: pagination stopped at safety cap of "
                        f"{page_limit} pages"
                    )
                    truncated_by_cap = True
                    break
                rendered = executor.render_catalog_request(spec, current)
                fetch_request = bridge.to_fetch_request(rendered)
                response = await context.fetch(fetch_request)
                # Reuse the standard ATS failure path: non-2xx raises
                # AdapterHttpError, the fetcher/scanner own retry,
                # circuit-breaker and cooldown. No custom handling here.
                require_success(response)
                payload = response.json()
                if not isinstance(payload, dict):
                    raise AdapterSchemaError(
                        f"{label}: catalog response is not an object "
                        f"(got {type(payload).__name__})"
                    )
                items, total = executor.extract_page(spec, payload)
                history.append(
                    {"page_value": current, "items_count": len(items), "total": total}
                )
                fetched.add(current)
                pages += 1

                if not items and total > 0 and current <= total and len(collected) < total:
                    # Empty page before total coverage: upstream shrank or
                    # lies about total. Never declare complete, never let
                    # the lifecycle close jobs on this run.
                    warnings.append(
                        f"{label}: empty page at offset {current} with "
                        f"total={total} after {len(collected)} jobs: "
                        "stopping conservatively, snapshot not complete"
                    )
                    pagination_anomaly = True
                    break

                if items and current > total >= 0:
                    # Items beyond the stated total: upstream under-reports
                    # (or grew mid-run without updating total). Treat like
                    # a total change — snapshot not authoritative.
                    warnings.append(
                        f"{label}: page at offset {current} returned "
                        f"{len(items)} items beyond stated total={total}: "
                        "snapshot not authoritative"
                    )
                    total_changed = True

                for index, raw in enumerate(items):
                    item = require_mapping(
                        raw, context=f"{label} catalog page {current}[{index}]"
                    )
                    partial = executor.extract_item(spec, item)
                    normalized = executor.normalize_job(spec, partial, seen_at)
                    collected.append(
                        normalized_job_to_raw_job(spec, normalized, native_item=item)
                    )

                if first_total is None:
                    first_total = total
                elif total != first_total and not total_changed:
                    warnings.append(
                        f"{label}: total changed during pagination "
                        f"({first_total} -> {total}): snapshot not authoritative"
                    )
                    total_changed = True

                upcoming = self._upcoming_offsets(
                    spec, first, page_size, current, total, probe_rule, fetched,
                    last_page_items=len(items),
                    short_page_rule=("last_page_shorter_than_page_size" in rule_kinds),
                )
                if len(collected) > job_cap or (
                    len(collected) == job_cap and upcoming
                ):
                    collected = collected[:job_cap]
                    warnings.append(
                        f"{label}: catalog stopped at job cap of "
                        f"{job_cap} records"
                    )
                    truncated_by_cap = True
                    break
                if not upcoming:
                    break
                current = upcoming[0]
        except executor.SourceSpecError as exc:
            raise AdapterSchemaError(f"{label}: {exc}") from exc
        except bridge.BridgeError as exc:
            raise AdapterSchemaError(f"{label}: {exc}") from exc

        complete, _reason = executor.evaluate_completeness(spec, history)
        is_complete_snapshot = bool(
            complete
            and authoritative
            and not truncated_by_cap
            and not pagination_anomaly
            and not total_changed
        )
        if not collected and is_complete_snapshot:
            warnings.append(f"{label}: upstream reports zero active jobs")
        return AdapterScanResult(
            jobs=tuple(collected),
            warnings=tuple(warnings),
            is_complete_snapshot=is_complete_snapshot,
        )

    @staticmethod
    def _upcoming_offsets(
        spec: dict,
        first: Any,
        page_size: int,
        current: Any,
        total: int,
        probe_rule: bool,
        fetched: set[Any],
        *,
        last_page_items: int = 0,
        short_page_rule: bool = False,
    ) -> list[Any]:
        """Data offsets after `current` (+ terminal probe), minus fetched.

        Same arithmetic as ``pagination_iterator`` (last data page, then
        the single empty-after-total probe when the spec's rules require
        it), recomputed from the latest observed total so a changing
        total cannot loop forever; the fetched-set guarantees progress.

        The unconditional probe covers specs whose rules REQUIRE the
        empty-after-total page (``items_path_empty_after_total``). Specs
        whose rules merely ACCEPT it as an alternative
        (``last_page_shorter_than_page_size``: partial final page OR
        empty-after-total) get a CONDITIONAL probe: only when the last
        data page came back full — the only case where the rule cannot
        be satisfied without one. A partial final page stops the scan
        with no extra request.
        """
        if not isinstance(total, int) or total < 0:
            return []
        try:
            current_index = (current - first) // page_size
        except TypeError:
            raise AdapterSchemaError(
                "declarative paging values must be numeric for offset strategy"
            ) from None
        if total >= first:
            # max(0, ...) guard mirrors pagination_iterator: total == first
            # still means exactly one data page (see executor BUGFIX note).
            n_data = (max(0, total - first - 1) // page_size) + 1
        else:
            n_data = 0
        upcoming = [
            first + kilopage * page_size
            for kilopage in range(current_index + 1, n_data)
        ]
        last_data = first + (n_data - 1) * page_size if n_data else None
        at_end = last_data is not None and current >= last_data
        probe_needed = probe_rule or (
            short_page_rule and at_end and total > 0 and last_page_items == page_size
        )
        if probe_needed:
            probe = first + n_data * page_size
            upcoming.append(probe)
        return [offset for offset in upcoming if offset not in fetched]


def load_bindings(bindings_path: str | Path | None = None) -> tuple[DeclarativeSourceBinding, ...]:
    """Load explicit bindings from the versioned JSON config."""
    path = Path(bindings_path) if bindings_path is not None else DEFAULT_BINDINGS_PATH
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"declarative bindings unreadable: {path} ({exc})") from exc
    entries = document.get("bindings") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"declarative bindings {path} must contain a 'bindings' list")
    bindings = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"declarative bindings {path} has a non-object entry: {entry!r}")
        bindings.append(
            DeclarativeSourceBinding(
                normalized_jobs_url=entry.get("normalized_jobs_url", ""),
                spec_path=entry.get("spec_path", entry.get("spec", "")),
            )
        )
    return tuple(bindings)


def load_declarative_adapter(
    bindings_path: str | Path | None = None,
    *,
    base_dir: str | Path | None = None,
) -> DeclarativeSourceAdapter:
    """Build the shared adapter from the versioned bindings config."""
    return DeclarativeSourceAdapter(
        load_bindings(bindings_path),
        base_dir=base_dir if base_dir is not None else _HERE,
    )


__all__ = [
    "AdapterHttpError",
    "DeclarativeSourceAdapter",
    "DeclarativeSourceBinding",
    "QUALIFICATIONS_HEADING",
    "compose_semantic_text",
    "declarative_source_name",
    "load_bindings",
    "load_declarative_adapter",
    "normalized_job_to_raw_job",
]

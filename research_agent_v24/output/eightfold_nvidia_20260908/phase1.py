"""Phase 1 NVIDIA binding truth (0 wires, offline)."""
import json
import sys

sys.path.insert(0, "src")

from research_agent.config import get_settings  # noqa: E402
from research_agent.db.session import create_db_engine  # noqa: E402
from research_agent.pipeline.scanner import load_portal_targets  # noqa: E402
from research_agent.sources.ats.registry import structured_adapter_registry  # noqa: E402
from research_agent.sources.base import PortalTarget  # noqa: E402
from research_agent.sources.declarative import load_declarative_adapter  # noqa: E402
from research_agent.sources.declarative import executor  # noqa: E402

prod = create_db_engine(get_settings().database_url)
targets = load_portal_targets(prod, portal_ids={443})
t443 = targets[0]
print("portal 443:", t443.portal_id, t443.host, t443.jobs_search_url, t443.ats_families)

adapter = load_declarative_adapter()
print("bindings:", adapter.bound_portal_urls)
registry = structured_adapter_registry(declarative_adapters=[adapter])
sel443 = registry.select(t443)
print("portal 443 selects:", type(sel443).__name__ if sel443 else None)

bound = PortalTarget(
    portal_id=None,
    jobs_search_url="https://jobs.nvidia.com/careers",
    normalized_jobs_url="https://jobs.nvidia.com/careers",
    host="jobs.nvidia.com",
    ats_families=("Eightfold",),
    ats_confidences=("Verified",),
)
sel = registry.select(bound)
print("bound URL selects:", type(sel).__name__ if sel else None)
spec = sel.spec_for(bound)
print("spec company:", spec["company"], "platform:", spec["platform"]["name"])

rendered = executor.render_catalog_request(spec, 0)
print("catalog render:", json.dumps(rendered, sort_keys=True)[:400])
rendered2 = executor.render_catalog_request(spec, 10)
print("page2 render:", json.dumps(rendered2, sort_keys=True)[:400])
detail = sel.render_detail_fetch(bound, "12345")
print("detail render:", detail.method, detail.url)

settings = get_settings().scanner.model_copy(
    update={
        "global_concurrency": 1,
        "per_domain_concurrency": 1,
        "per_domain_min_interval_seconds": 1.0,
        "max_retries": 0,
        "max_requests_per_host_per_run": 7,
        "max_requests_per_run": 7,
        "max_pages_per_portal": 7,
        "max_jobs_per_portal": 5000,
    }
)
print("preflight:", sel.preflight(bound, settings))
print("PHASE1_OK")

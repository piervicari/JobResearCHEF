"""Declarative vacancy sources: source_spec/v0.1 runtime as a sibling adapter.

Canonical home of the declarative runtime (Phase 2): the executor,
the bridge and the adapter live here. ``runtime/`` (the offline
experiment directory) keeps thin loaders pointing at this package so
there is exactly one implementation of each behaviour.
"""

from research_agent.sources.declarative.adapter import (
    DeclarativeSourceAdapter,
    DeclarativeSourceBinding,
    load_declarative_adapter,
    normalized_job_to_raw_job,
)

__all__ = [
    "DeclarativeSourceAdapter",
    "DeclarativeSourceBinding",
    "load_declarative_adapter",
    "normalized_job_to_raw_job",
]

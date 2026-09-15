"""Codegraph's source-indexing package.

The implementation was migrated from the historical ``doxygen_index``
distribution. Public compatibility imports are lazy so importing the
contract layer does not import optional C++ tooling, network clients, or the
compatibility distribution.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.1.0"

_LAZY_EXPORTS = {
    "IndexMode": ("codegraph_index.contracts", "IndexMode"),
    "IndexRequest": ("codegraph_index.contracts", "IndexRequest"),
    "IndexResult": ("codegraph_index.contracts", "IndexResult"),
    "IndexDelta": ("codegraph_index.contracts", "IndexDelta"),
    "IndexDiagnostic": ("codegraph_index.contracts", "IndexDiagnostic"),
    "IndexFinding": ("codegraph_index.contracts", "IndexFinding"),
    "IndexService": ("codegraph_index.service", "IndexService"),
    "index": ("codegraph_index.service", "index"),
    "ConanDiscoveryError": ("codegraph_index.conan", "ConanDiscoveryError"),
    "discover_packages": ("codegraph_index.conan", "discover_packages"),
    "generate_xml": ("codegraph_index.doxygen", "generate_xml"),
    "generate_doxyfile": ("codegraph_index.doxygen", "generate_doxyfile"),
    "parse_xml_dir": ("codegraph_index.parser", "parse_xml_dir"),
    "ProjectConfig": ("codegraph_index.project", "ProjectConfig"),
    "load_config": ("codegraph_index.project", "load_config"),
    "write_json": ("codegraph_index.json_backend", "write_result"),
    "create_toolset": ("codegraph_index.tools", "create_toolset"),
    "DependencyGraphTools": ("codegraph_index.tools", "DependencyGraphTools"),
    "EnrichmentResult": ("codegraph_index.enrich", "EnrichmentResult"),
    "EnrichmentSummary": ("codegraph_index.enrich", "EnrichmentSummary"),
    "enrich_result": ("codegraph_index.enrich", "enrich_result"),
    "enrich_single_test": ("codegraph_index.enrich", "enrich_single_test"),
    "enrich_test_descriptions": (
        "codegraph_index.enrich",
        "enrich_test_descriptions",
    ),
    "enrich_all_tests": ("codegraph_index.enrich", "enrich_all_tests"),
    "enrichment_available": ("codegraph_index.enrich", "enrichment_available"),
    "check_enrichment_config": ("codegraph_index.enrich", "check_enrichment_config"),
}

__all__ = [*sorted(_LAZY_EXPORTS), "parse_cppreference"]


def __getattr__(name: str) -> Any:
    """Resolve legacy convenience exports without eager optional imports."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def parse_cppreference(archive_root, **kwargs):
    """Parse a cppreference archive; requires the optional extra."""
    from codegraph_index.cppreference import parse

    return parse(archive_root, **kwargs)

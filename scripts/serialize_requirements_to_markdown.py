#!/usr/bin/env python
"""Serialize requirements and components from Neo4j to Markdown.

Queries the Neo4j instance for all Component, HLR, and LLR nodes,
builds a LayerGraph from their COMPOSES hierarchy, exports it to
Markdown, and writes the result to ``codegraph/requirements/``.

Also verifies the round-trip by importing the Markdown back and
checking that the core structure is preserved.

Usage::

    python scripts/serialize_requirements_to_markdown.py

Requires Neo4j running and environment variables set (NEO4J_URI,
NEO4J_USER, NEO4J_PASSWORD).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Load .env *before* importing codegraph.persistence.config, which reads
# NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD from os.environ at import time.
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# Import model packages so the CodeGraphNode registry is populated.
import codegraph.persistence.config  # noqa: F401
import codegraph_requirements.models.requirement  # noqa: F401
import codegraph_project.models.component  # noqa: F401

from neomodel import db
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.export.markdown import export_markdown, import_markdown
from codegraph.models.tags import CodeGraphNode


def build_requirements_graph() -> LayerGraph:
    """Query Neo4j for all Component -> HLR -> LLR nodes and build a LayerGraph.

    Uses raw Cypher to fetch the full COMPOSES hierarchy and assemble
    CompositeEntry instances in memory.  This avoids the neomodel
    relationship-manager overhead and works across the separate
    codegraph_requirements and codegraph_project packages.
    """
    Neo4jConnection().ensure_driver()

    # -- Fetch all Component, HLR, LLR nodes --
    query = """
    MATCH (n)
    WHERE (n:Component OR n:HLR OR n:LLR)
    RETURN n, labels(n) AS labels
    """
    results, _ = db.cypher_query(query)

    nodes: dict[str, CodeGraphNode] = {}
    key_to_type: dict[str, str] = {}

    for row in results:
        node_props = dict(row[0])
        labels = row[1]
        if "Component" in labels:
            from codegraph_project.models.component import Component
            node = Component.inflate(row[0])
            node_type = "Component"
        elif "HLR" in labels:
            from codegraph_requirements.models.requirement import HLR
            node = HLR.inflate(row[0])
            node_type = "HLR"
        elif "LLR" in labels:
            from codegraph_requirements.models.requirement import LLR
            node = LLR.inflate(row[0])
            node_type = "LLR"
        else:
            continue

        key = LayerGraph._node_key(node)
        nodes[key] = node
        key_to_type[key] = node_type

    print(f"  Found {len(nodes)} nodes "
          f"({sum(1 for t in key_to_type.values() if t == 'Component')} Components, "
          f"{sum(1 for t in key_to_type.values() if t == 'HLR')} HLRs, "
          f"{sum(1 for t in key_to_type.values() if t == 'LLR')} LLRs)")

    # -- Fetch all COMPOSES edges between these nodes --
    edge_query = """
    MATCH (source)-[:COMPOSES]->(target)
    WHERE (source:Component OR source:HLR OR source:LLR)
      AND (target:Component OR target:HLR OR target:LLR)
    RETURN source, target, labels(source) AS src_labels, labels(target) AS tgt_labels
    """
    edge_results, _ = db.cypher_query(edge_query)

    # Build a mapping from raw node properties to the LayerGraph key.
    # For HLR/LLR the unique property is refid (UniqueIdProperty).
    # For Component there is no UniqueIdProperty so the key falls back
    # to name (via _node_key -> _uid_value -> None -> fallback to name).
    prop_to_key: dict[str, str] = {}
    for key, node in nodes.items():
        if key_to_type[key] == "Component":
            prop_to_key[node.name] = key
        else:
            uid_val = node._uid_value()  # refid for HLR/LLR
            if uid_val:
                prop_to_key[uid_val] = key

    # -- Build CompositeEntry tree --
    key_to_entry: dict[str, CompositeEntry] = {}
    for key, node in nodes.items():
        key_to_entry[key] = CompositeEntry(node=node)

    child_keys: set[str] = set()

    for row in edge_results:
        src_props = dict(row[0])
        tgt_props = dict(row[1])
        src_labels = row[2]
        tgt_labels = row[3]

        # Resolve source and target keys via the prop_to_key mapping.
        # For Component, use name; for HLR/LLR, use refid.
        if "Component" in src_labels:
            src_lookup = src_props.get("name", "")
        else:
            src_lookup = src_props.get("refid", "")
        if "Component" in tgt_labels:
            tgt_lookup = tgt_props.get("name", "")
        else:
            tgt_lookup = tgt_props.get("refid", "")

        src_key = prop_to_key.get(src_lookup)
        tgt_key = prop_to_key.get(tgt_lookup)

        if src_key is None or tgt_key is None:
            continue

        src_entry = key_to_entry[src_key]
        tgt_entry = key_to_entry[tgt_key]
        tgt_type = key_to_type.get(tgt_key, "")

        if tgt_type not in src_entry.children:
            src_entry.children[tgt_type] = {}
        src_entry.children[tgt_type][tgt_key] = tgt_entry
        child_keys.add(tgt_key)

    # Root entries = nodes not composed by another
    root_entries = {
        key: entry
        for key, entry in key_to_entry.items()
        if key not in child_keys
    }

    return LayerGraph(
        tags=frozenset({"as-built"}),
        entries=root_entries,
    )


def main() -> None:
    output_dir = Path(__file__).resolve().parent.parent / "codegraph" / "requirements"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Building requirements graph from Neo4j...")
    graph = build_requirements_graph()

    print(f"  Root entries: {len(graph.entries)}")

    # -- Export to Markdown --
    print("Exporting to Markdown...")
    md = export_markdown(graph, fields="all")

    output_file = output_dir / "requirements.md"
    output_file.write_text(md, encoding="utf-8")
    print(f"  Written {len(md)} bytes to {output_file}")

    # -- Verify round-trip --
    print("Verifying round-trip (import -> re-export)...")
    restored = import_markdown(md, tags=frozenset({"as-built"}))

    # Count restored nodes
    all_restored = list(restored._all_entries())
    print(f"  Restored {len(all_restored)} nodes from Markdown")

    # Check that all root entries survived.
    # HLR/LLR nodes are keyed by refid (UUID) in Neo4j but by name in
    # Markdown, so we compare by node name instead of by key.
    original_names = set()
    for entry in graph._all_entries():
        original_names.add(entry.node.name)
    restored_names = set()
    for entry in restored._all_entries():
        restored_names.add(entry.node.name)
    missing_names = original_names - restored_names
    if missing_names:
        print(f"  X {len(missing_names)} nodes lost: {list(missing_names)[:5]}")
    else:
        print(f"  All {len(original_names)} node names preserved")

    # Re-export to verify stability
    md2 = export_markdown(restored, fields="all")
    roundtrip_file = output_dir / "requirements_roundtrip.md"
    roundtrip_file.write_text(md2, encoding="utf-8")
    print(f"  Round-trip Markdown written to {roundtrip_file}")

    # Compare key content
    if md == md2:
        print("  Round-trip is stable (identical output)")
    else:
        # Check that headings are preserved
        import re
        headings1 = set(re.findall(r'^#{2,}.*$', md, re.MULTILINE))
        headings2 = set(re.findall(r'^#{2,}.*$', md2, re.MULTILINE))
        if headings1 == headings2:
            print(f"  All {len(headings1)} headings preserved")
        else:
            missing = headings1 - headings2
            extra = headings2 - headings1
            if missing:
                print(f"  X {len(missing)} headings missing: {list(missing)[:5]}")
            if extra:
                print(f"  ! {len(extra)} extra headings: {list(extra)[:5]}")

    print("\nDone!")


if __name__ == "__main__":
    main()
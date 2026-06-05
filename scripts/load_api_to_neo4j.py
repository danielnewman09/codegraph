#!/usr/bin/env python3
"""Extract codegraph API metadata via Sphinx and persist it to Neo4j.

Pipeline:
    1. Run ``sphinx-build -b json_api`` to produce ``api_metadata.json``
    2. Transform the metadata into codegraph node payloads
    3. Load via ``LayerGraph.from_json()``
    4. Persist via ``LayerGraph.to_neo4j()``

Usage:
    python scripts/load_api_to_neo4j.py           # build + load
    python scripts/load_api_to_neo4j.py --skip-build  # load existing JSON only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "source"
BUILD_DIR = ROOT / "docs" / "_build"
METADATA_FILE = BUILD_DIR / "api_metadata.json"

# ---------------------------------------------------------------------------
# Mapping: FQN suffix → codegraph node type
# ---------------------------------------------------------------------------

_CLASS_NAME_TO_NODE_TYPE: dict[str, str] = {
    "ClassNode": "ClassNode",
    "InterfaceNode": "InterfaceNode",
    "EnumNode": "EnumNode",
    "UnionNode": "UnionNode",
    "ModuleNode": "ModuleNode",
    "MethodNode": "MethodNode",
    "AttributeNode": "AttributeNode",
    "EnumValueNode": "EnumValueNode",
    "FunctionNode": "FunctionNode",
    "DefineNode": "DefineNode",
    "NamespaceNode": "NamespaceNode",
    "FileNode": "FileNode",
    "ParameterNode": "ParameterNode",
    "CodeGraphNode": "ClassNode",  # base class → represented as ClassNode
    "LayerGraph": "ClassNode",     # dataclass → represented as ClassNode
    "GraphRepository": "ClassNode",  # regular class → represented as ClassNode
}

# codegraph kind values for node types that are not standard compounds
_KIND_FOR_NODE_TYPE: dict[str, str] = {
    "ClassNode": "class",
    "InterfaceNode": "interface",
    "EnumNode": "enum",
    "UnionNode": "union",
    "ModuleNode": "module",
    "MethodNode": "method",
    "AttributeNode": "attribute",
    "EnumValueNode": "enumvalue",
    "FunctionNode": "function",
    "DefineNode": "define",
    "NamespaceNode": "namespace",
    "FileNode": "file",
    "ParameterNode": "parameter",
}


# ---------------------------------------------------------------------------
# Step 1: Run Sphinx build
# ---------------------------------------------------------------------------

def run_sphinx_build() -> None:
    """Run ``sphinx-build -b json_api`` to produce api_metadata.json."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "sphinx",
        "-b", "json_api",
        str(SOURCE_DIR),
        str(BUILD_DIR),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(f"Sphinx build failed with exit code {result.returncode}")
    if not METADATA_FILE.exists():
        sys.exit(f"Build succeeded but {METADATA_FILE} not found")
    print(f"Metadata written to {METADATA_FILE}")


# ---------------------------------------------------------------------------
# Step 2: Transform metadata → codegraph nodes
# ---------------------------------------------------------------------------

def _node_type_for_class(fqn: str) -> str | None:
    """Map a fully-qualified class name to a codegraph node type string."""
    class_name = fqn.rsplit(".", 1)[-1]
    return _CLASS_NAME_TO_NODE_TYPE.get(class_name)


def _transform(metadata: dict[str, dict]) -> list[dict]:
    """Transform ``api_metadata.json`` entries into codegraph node payloads.

    Returns a list of dicts suitable for ``LayerGraph.from_json()``.
    Each dict has ``type``, node properties, and ``edges``.
    """
    nodes: list[dict] = []
    seen: set[str] = set()  # track qualified_names to avoid duplicates

    for fqn, entry in metadata.items():
        kind = entry.get("kind")

        if kind == "module":
            node = _make_module_node(fqn, entry)
            qname = node["qualified_name"]
            if qname not in seen:
                seen.add(qname)
                nodes.append(node)

        elif kind == "class":
            node_type = _node_type_for_class(fqn)
            if node_type is None:
                print(f"  Skipping unmapped class: {fqn}", file=sys.stderr)
                continue
            node = _make_class_node(fqn, entry, node_type)
            qname = node["qualified_name"]
            if qname not in seen:
                seen.add(qname)
                nodes.append(node)

            # Emit methods as separate MethodNode entries
            # Skip neomodel inherited methods — only codegraph-defined ones
            for method_name, method_data in entry.get("methods", {}).items():
                if method_name in _NEMOMODEL_METHODS:
                    continue
                method_node = _make_method_node(fqn, method_name, method_data)
                method_qname = method_node["qualified_name"]
                if method_qname not in seen:
                    seen.add(method_qname)
                    nodes.append(method_node)

        elif kind == "function":
            node = _make_function_node(fqn, entry)
            qname = node["qualified_name"]
            if qname not in seen:
                seen.add(qname)
                nodes.append(node)

    # Second pass: add edges from relationships metadata
    for fqn, entry in metadata.items():
        if entry.get("kind") != "class":
            continue
        rels = entry.get("relationships", {})
        if not rels:
            continue
        # Find the node we already created for this class
        qname = fqn
        for node in nodes:
            if node.get("qualified_name") == qname:
                for rel_name, rel_data in rels.items():
                    target_type = rel_data.get("target", "")
                    # Find the target node in our list
                    target_local_id = _find_target_local_id(nodes, target_type, rel_name)
                    if target_local_id:
                        node.setdefault("edges", []).append({
                            "relation_type": rel_data["label"],
                            "target_type": _node_type_for_target(target_type),
                            "target_local_id": target_local_id,
                        })
                break

    return nodes


def _make_module_node(fqn: str, entry: dict) -> dict:
    """Create a ModuleNode payload from a module metadata entry."""
    return {
        "type": "ModuleNode",
        "name": fqn.rsplit(".", 1)[-1],
        "qualified_name": fqn,
        "kind": "module",
        "layer": "as-built",
        "brief_description": entry.get("doc", ""),
        "visibility": "",
        "edges": [],
    }


def _make_class_node(fqn: str, entry: dict, node_type: str) -> dict:
    """Create a codegraph node payload from a class metadata entry."""
    props = entry.get("properties", {})
    kind_value = _KIND_FOR_NODE_TYPE.get(node_type, "class")

    # Use the kind from properties if available (e.g. the ClassNode's kind
    # property defaults to "class")
    if "kind" in props:
        prop_kind = props["kind"].get("default", kind_value)
        if prop_kind and prop_kind != "":
            kind_value = prop_kind

    node: dict = {
        "type": node_type,
        "name": fqn.rsplit(".", 1)[-1],
        "qualified_name": fqn,
        "kind": kind_value,
        "layer": "as-built",
        "visibility": props.get("visibility", {}).get("default", ""),
        "brief_description": entry.get("doc", ""),
        "edges": [],
    }

    # Add class-specific properties from the metadata
    if "module" in props:
        node["module"] = props["module"].get("default", "")
    if "base_classes" in props:
        default = props["base_classes"].get("default", [])
        node["base_classes"] = [b for b in (default if isinstance(default, list) else [])]

    # FileNode uses "path" as its unique identifier instead of qualified_name
    if node_type == "FileNode" and "path" in props:
        node["path"] = fqn

    return node


# Methods inherited from neomodel internals — skip these
_NEMOMODEL_METHODS: set[str] = {
    "__init__",
    "create",
    "create_or_update",
    "cypher",
    "deflate",
    "delete",
    "del_property",
    "edges",
    "element_id",
    "inflate",
    "labels",
    "node",
    "nodes",
    "refresh",
    "refresh_from_properties",
    "save",
    "serialized",
    "serialized_from_db",
}


def _make_method_node(parent_fqn: str, method_name: str, method_data: dict) -> dict:
    """Create a MethodNode payload from a method entry within a class."""
    qualified_name = f"{parent_fqn}::{method_name}"
    doc = method_data.get("doc", "")
    # Truncate the first line as brief_description
    brief = doc.split("\n")[0] if doc else ""

    edges: list[dict] = []
    # This method is composed by its parent class
    parent_type = _node_type_for_class(parent_fqn) or "ClassNode"
    edges.append({
        "relation_type": "COMPOSES",
        "target_type": "MethodNode",
        "target_local_id": method_name,
    })

    return {
        "type": "MethodNode",
        "name": method_name,
        "qualified_name": qualified_name,
        "kind": "method",
        "layer": "as-built",
        "visibility": "public",
        "brief_description": brief,
        "type_signature": method_data.get("signature", ""),
        "detailed_description": doc,
        "edges": edges,
    }


def _make_function_node(fqn: str, entry: dict) -> dict:
    """Create a FunctionNode payload from a function metadata entry."""
    name = fqn.rsplit(".", 1)[-1]
    doc = entry.get("doc", "")
    brief = doc.split("\n")[0] if doc else ""

    return {
        "type": "FunctionNode",
        "name": name,
        "qualified_name": fqn,
        "kind": "function",
        "layer": "as-built",
        "visibility": "public",
        "brief_description": brief,
        "type_signature": entry.get("signature", ""),
        "detailed_description": doc,
        "edges": [],
    }


def _node_type_for_target(target_name: str) -> str:
    """Map a relationship target class name to a codegraph node type."""
    return _CLASS_NAME_TO_NODE_TYPE.get(target_name, "ClassNode")


def _find_target_local_id(nodes: list[dict], target_type: str, rel_name: str) -> str | None:
    """Find the local ID for a relationship target among already-created nodes.

    Searches by node type name matching the target_type string.
    For method/attribute relationships, the target might be a single
    representative or we may skip the edge if there's ambiguity.
    """
    # For singular targets (defined_in, specializes, etc.), find by type
    singular_targets = {
        "defined_in": "FileNode",
        "template_params": "ClassNode",
        "specializes": "ClassNode",
        "base": "ClassNode",
        "realizes": "InterfaceNode",
    }
    # For plural targets (methods, attributes, etc.), skip — they're
    # represented by individual COMPOSES edges from the child MethodNodes
    plural_targets = {
        "methods", "attributes", "base_classes", "derived",
        "depends_on", "depended_on_by", "references", "referred_by",
        "composes", "values", "enum_values",
    }

    if rel_name in plural_targets:
        return None

    # Find a node matching the target type
    for node in nodes:
        if node.get("type") == target_type:
            return node.get("name") or node.get("qualified_name")

    return None


# ---------------------------------------------------------------------------
# Step 3 & 4: Load into LayerGraph and persist to Neo4j
# ---------------------------------------------------------------------------

def load_and_persist(nodes_data: list[dict]) -> None:
    """Load node payloads into a LayerGraph and persist to Neo4j."""
    # Ensure codegraph is importable
    sys.path.insert(0, str(ROOT / "src"))

    # Load Neo4j credentials from .env
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from codegraph.graph import LayerGraph

    graph = LayerGraph.from_json(nodes_data)
    total = sum(1 for _ in graph._all_entries())
    print(f"Loaded {total} nodes into LayerGraph (layer={graph.layer})")
    print(f"Root entries: {len(graph.entries)}")

    graph.to_neo4j()
    print("Persisted to Neo4j")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract codegraph API metadata and load into Neo4j",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip the Sphinx build; load from existing api_metadata.json",
    )
    args = parser.parse_args()

    if not args.skip_build:
        run_sphinx_build()

    if not METADATA_FILE.exists():
        sys.exit(f"Metadata file not found: {METADATA_FILE}")

    with open(METADATA_FILE) as f:
        metadata = json.load(f)

    print(f"Transforming {len(metadata)} metadata entries...")
    nodes_data = _transform(metadata)
    print(f"Produced {len(nodes_data)} codegraph node payloads")

    load_and_persist(nodes_data)
    print("Done.")


if __name__ == "__main__":
    main()
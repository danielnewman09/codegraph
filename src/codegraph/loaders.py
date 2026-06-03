"""Graph loader — deserialize and persist a complete graph from JSON.

The ``load_graph`` function reads a list of node payloads (as produced by
``CodeGraphNode.serialize()``), creates each node in Neo4j, and connects
all edges.  It returns a dict keyed by a stable local identifier so callers
can look up created nodes by name (or path for FileNode).

Expected JSON format (see ``tests/data/design_graph.json`` for an example)::

    [
        {
            "type": "ClassNode",
            "name": "CalculatorEngine",
            "kind": "class",
            "edges": [
                {"relation_type": "COMPOSES", "target_type": "MethodNode",
                 "target_local_id": "add"}
            ]
        },
        ...
    ]

Each edge has:
    - ``relation_type`` — Neo4j relationship label (e.g. "COMPOSES")
    - ``target_type`` — the ``type`` discriminator of the target node class
    - ``target_local_id`` — the lookup key (``name`` for most nodes,
      ``path`` for FileNode) that matches the corresponding node in the array
"""

from __future__ import annotations

from neomodel import RelationshipTo, RelationshipFrom

from codegraph.models.tags import CodeGraphNode


def _node_key(node_data: dict) -> str:
    """Derive a stable local key from a fixture node.

    FileNode uses ``path`` (globally unique), all other nodes use ``name``.
    """
    if node_data["type"] == "FileNode":
        return node_data["path"]
    return node_data["name"]


def _find_relationship_manager(source, relation_type: str, target):
    """Find the relationship manager on *source* matching both
    *relation_type* and the class of *target*.

    This is needed because some relation types (e.g. COMPOSES) have
    multiple managers on the same source class pointing at different
    target types (ClassNode.methods → MethodNode, ClassNode.attributes → AttributeNode).

    Returns the relationship manager attribute (e.g. ``source.methods``).

    Raises ``ValueError`` if no matching manager is found.
    """
    target_cls = type(target)
    for klass in type(source).__mro__:
        for name, val in vars(klass).items():
            if isinstance(val, (RelationshipTo, RelationshipFrom)):
                if val.definition["relation_type"] != relation_type:
                    continue
                rel_target = val.definition.get("model") or val._raw_class
                if rel_target == target_cls:
                    return getattr(source, name)
                if isinstance(rel_target, str) and (
                    rel_target == target_cls.__name__
                    or rel_target.endswith(f".{target_cls.__name__}")
                ):
                    return getattr(source, name)
    raise ValueError(
        f"No '{relation_type}' relationship from "
        f"{type(source).__name__} to {target_cls.__name__}"
    )


def load_graph(graph_data: list[dict]) -> dict[str, CodeGraphNode]:
    """Deserialize a list of node payloads, save them to Neo4j, and
    connect all edges.

    Parameters
    ----------
    graph_data :
        A list of dicts, each in the format produced by
        ``CodeGraphNode.serialize()``.  Every dict must have a ``type``
        key for the ``from_json()`` dispatcher and an ``edges`` key
        (may be empty) where each edge has ``relation_type``,
        ``target_type``, and ``target_local_id``.

    Returns
    -------
    dict[str, CodeGraphNode]
        Mapping from local key (name or path) to the saved node instance.
        Use this to look up nodes after loading, e.g.
        ``nodes["CalculatorEngine"]``.
    """
    # Phase 1: Create and save all nodes
    nodes: dict[str, CodeGraphNode] = {}
    for node_data in graph_data:
        node = CodeGraphNode.from_json(node_data).save()
        nodes[_node_key(node_data)] = node

    # Phase 2: Connect all edges
    for node_data in graph_data:
        source = nodes[_node_key(node_data)]
        for edge in node_data.get("edges", []):
            target = nodes[edge["target_local_id"]]
            manager = _find_relationship_manager(
                source, edge["relation_type"], target
            )
            manager.connect(target)

    return nodes
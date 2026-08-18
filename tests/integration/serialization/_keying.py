"""Shared canonical-key helper for serialization tests (WP A/B).

The serialization suites build hand-made graphs (raw nodes without
canonical keys) and feed them to exporters, which now require keys.
``key_graph`` stamps canonical keys onto every node under a fixed test
scope, following parent chains from the entry tree.
"""


def key_graph(graph, project="codegraph-suite", repo="codegraph"):
    """WP A: assign canonical keys to every node in *graph* in place."""
    from codegraph.identity import IdentityScope, resolve_identity_for

    scope = IdentityScope.repository(project, repo)

    def walk(entries, parent_key=None):
        for entry in entries:
            node = entry.node
            t = type(node).__name__
            parents = {}
            if parent_key:
                if t == "LLR":
                    parents["parent_hlr_key"] = parent_key
                elif t in ("TestNode", "TestFixtureNode",
                           "AssertionNode", "TestStepNode"):
                    parents["parent_key"] = parent_key
                elif t in ("ParameterNode", "ImplementationNode"):
                    parents["parent_callable_key"] = parent_key
                elif t == "SourceFragmentNode":
                    parents["file_key"] = parent_key
            node.canonical_key = resolve_identity_for(
                node, scope, parents=parents
            ).key()
            walk(
                [
                    e
                    for type_children in entry.children.values()
                    for e in type_children.values()
                ],
                node.canonical_key,
            )

    walk(list(graph.entries.values()))
    return graph

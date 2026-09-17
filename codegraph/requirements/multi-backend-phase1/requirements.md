# codegraph: design, requirements

## HLR: `Multi-Backend Architecture — Phase 1`
Extract all Neo4j-specific code from the codegraph core (models, persistence, graph) into a dedicated backends/neo4j/ package behind a Backend abstract interface. Create a backend registry (set_backend/get_backend) so the active backend is configurable via environment or explicit call. Rewire CodeGraphNode, GraphRepository, and LayerGraph to delegate all data access through get_backend(). Phase 1 changes zero behavior — the full test suite must pass against the Neo4j backend with identical semantics.

The Backend ABC in backends/interface.py defines 15 abstract methods across six categories: lifecycle (initialize, health_check), node CRUD (save, delete, get, inflate), node queries (find_by_tag, find_all_by_tag, find_all_by_source, find_all_by_kind), relationship ops (connect, disconnect, get_composed_children, get_all_edges, get_all_edges_outgoing), bulk ops (bulk_save, bulk_load_by_tag), and raw query (execute_raw). Also defines EdgeDescriptor dataclass (relation_type, target_uid, target_type, is_outgoing) and BackendConfig base dataclass.

The Neo4j backend in backends/neo4j/ has 6 sub-modules: connection.py (driver mgmt, migrated from persistence/connection.py), config.py (Neo4jConfig from persistence/config.py), node_ops.py (CRUD extracted from tags.py:_save, _delete, fetch_by_*), rel_ops.py (relationship ops from tags.py:walk_composes, walk_edges, find_relationship_manager), bulk_ops.py (bulk save/load from graph/__init__.py:to_neo4j, from_neo4j), and __init__.py (Neo4jBackend composing sub-ops).

The backend registry in backends/__init__.py provides set_backend(backend) and get_backend() with a module-level _current_backend.

CodeGraphNode rewiring: _save, _delete, fetch_by_tag, fetch_all_by_tag, fetch_all_by_source, fetch_all_by_kind, walk_composes, walk_edges, serialize_edges all become one-line delegations through get_backend(). find_relationship_manager moves to neo4j/rel_ops.py.

GraphRepository rewiring: __init__ accepts a Backend parameter. _get_node_by_qualified_name, _get_member_by_qualified_name delegate through backend.get(). get_by_namespace uses backend.get() + backend.get_composed_children(). save_layer_graph calls backend.bulk_save().

LayerGraph rewiring: to_backend(backend) and from_backend(backend, tag) replace to_neo4j/from_neo4j. Original methods become deprecated wrappers.

Acceptance: full test suite passes against Neo4j; persistence/connection.py and config.py deleted; zero direct neomodel calls in CodeGraphNode except property declarations.
- qualified_name: Multi-Backend Architecture — Phase 1
- tags: requirements

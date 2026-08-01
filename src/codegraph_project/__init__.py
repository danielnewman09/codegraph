"""Project-management models for codegraph.

Provides Component, ProjectMeta, Language, and Dependency node models —
project-level concepts that live alongside codegraph's code-level nodes
(ClassNode, NamespaceNode, etc.) in Neo4j.  All four are pure-Python
(no neomodel dependency).

Migrated from the ticketing system's ``backend_migrated.models`` package.

Usage::

    from codegraph_project.models import Component, ProjectMeta

    proj = ProjectMeta.get_singleton()
    comp = Component(name="backend", description="...").save()
    proj.components.connect(comp)

Graph structure::

    ProjectMeta -[:COMPOSES]-> Component -[:COMPOSES]-> Component (sub)
                            └─[:COMPOSES]-> HLR
                            └─[:GROUPS]-> NamespaceNode | ClassNode
                            └─[:WRITTEN_IN]-> Language
                            └─[:DEPENDS_ON]-> Dependency
"""

from codegraph_project.models import (
    Component,
    Dependency,
    Language,
    ProjectMeta,
)

__all__ = [
    "Component",
    "Dependency",
    "Language",
    "ProjectMeta",
]

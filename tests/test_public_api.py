"""Test that the public API surface is importable from codegraph directly."""


def test_import_nodes():
    from codegraph import FileNode, NamespaceNode, ClassNode, InterfaceNode, EnumNode, MethodNode, AttributeNode, EnumValueNode, ParameterNode
    assert FileNode is not None
    assert NamespaceNode is not None
    assert ClassNode is not None
    assert InterfaceNode is not None
    assert EnumNode is not None
    assert MethodNode is not None
    assert AttributeNode is not None
    assert EnumValueNode is not None
    assert ParameterNode is not None


def test_import_classdiagram():
    from codegraph import ClassDiagram
    assert ClassDiagram is not None


def test_import_edges():
    from codegraph import PREDICATES
    assert isinstance(PREDICATES, list)


def test_import_constants():
    from codegraph import (
        COMPOUND_KINDS,
        MEMBER_KINDS,
        NAMESPACE_KINDS,
        NODE_KINDS,
        LAYERS,
        VISIBILITY_CHOICES,
        PREDICATE_TO_REL_TYPE,
        CONSTRAINTS_AND_INDEXES,
    )
    assert isinstance(COMPOUND_KINDS, list)
    assert isinstance(MEMBER_KINDS, list)
    assert isinstance(NAMESPACE_KINDS, list)
    assert isinstance(NODE_KINDS, list)
    assert isinstance(LAYERS, list)
    assert isinstance(VISIBILITY_CHOICES, list)
    assert isinstance(PREDICATE_TO_REL_TYPE, dict)
    assert isinstance(CONSTRAINTS_AND_INDEXES, list)

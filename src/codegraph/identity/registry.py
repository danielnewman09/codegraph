"""The machine-checked identity registry and canonical identity value object.

This is Work Package 0.1 of the Priority 2 plan: a central identity
module that declares, for every persistable node type, exactly one
canonical identity specification — scope kind, stable artifact category,
and the ordered identity tuple.

Fixed architectural decisions enforced here:

- Shared logical keys: design and as-built observations of the same
  logical code entity share one canonical key and coexist through tags
  and provenance (decision 1).  No logical-entity/observation split.
- ``canonical_key`` beside legacy ``uid`` (decision 2) — this module
  only *computes* the canonical key; the model property and backends are
  later packages.
- Explicit scope (decision 3): ``project`` / ``repository`` /
  ``ecosystem`` via :class:`codegraph.identity.scope.IdentityScope`.
- Versioned percent-encoded key grammar (decision 4), see
  :mod:`codegraph.identity.encoding`.
- Stable artifact categories, not Python class names (decision 5).

The audit (:func:`audit_registry`) is the machine-checked contract that
imports every model package and fails when a concrete registered type
lacks a spec, two types collide on a category, a spec names a missing
property or unknown computed provider, or an intermediate type is
treated as independently persistable.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable

from codegraph.identity.encoding import (
    SUPPORTED_VERSIONS,
    KeyFormatError,
    encode_key,
    parse_key,
)
from codegraph.identity.scope import (
    ECOSYSTEM,
    PROJECT,
    REPOSITORY,
    IdentityScope,
    IdentityScopeError,
)

__all__ = [
    "CanonicalIdentity",
    "IdentityError",
    "IdentitySpec",
    "audit_registry",
    "category_spec",
    "resolve_identity_for",
    "short_label",
    "spec_for",
    "computed_providers",
]

#: Fixed key version for the frozen v1 identity matrix.
KEY_VERSION = 1


class IdentityError(ValueError):
    """Raised when an identity cannot be computed or resolved."""


# ══════════════════════════════════════════════════════════════════════════
# Computed identity providers
# ══════════════════════════════════════════════════════════════════════════
#
# A spec field is either a plain property name (read straight off the
# node) or the name of a computed provider.  Providers receive the node
# and the resolved scope; parent-relative providers additionally receive
# ``parents`` — a mapping of parent-identity field name → canonical key
# of the parent entity (WP1.4 wires these through; until then they raise
# a clear error rather than silently computing a wrong key).

Provider = Callable[[Any, IdentityScope, dict[str, str]], str]


def _canonical_signature_provider(node, scope: IdentityScope, parents) -> str:
    from codegraph.identity.signature import canonical_signature

    return canonical_signature(node)


def _normalized_repository_path_provider(node, scope: IdentityScope, parents) -> str:
    return normalize_repository_path(str(getattr(node, "path", "") or ""))


def _singleton_provider(node, scope: IdentityScope, parents) -> str:
    # ProjectMeta's singleton identity is the fixed constant "project"
    # (the plan's matrix row: ``project / singleton=project``).
    return "project"


def _parent_relative_provider(field: str) -> Provider:
    def provider(node, scope: IdentityScope, parents) -> str:
        value = parents.get(field)
        if value is None:
            raise IdentityError(
                f"field {field!r} on {type(node).__name__} requires parent "
                f"identity context; none provided (Work Package 1.4 wires "
                f"computed parent identities)"
            )
        return value

    provider.__name__ = f"_parent_relative_provider_{field}"
    return provider


#: Registry of computed identity-field providers by field name.
computed_providers: dict[str, Provider] = {
    "canonical_signature": _canonical_signature_provider,
    "normalized_repository_path": _normalized_repository_path_provider,
    "singleton": _singleton_provider,
    "parent_callable_key": _parent_relative_provider("parent_callable_key"),
    "parent_hlr_key": _parent_relative_provider("parent_hlr_key"),
    "parent_key": _parent_relative_provider("parent_key"),
    "file_key": _parent_relative_provider("file_key"),
}


def normalize_repository_path(path: str) -> str:
    """Normalize a repository-relative path to its identity form.

    - backslashes become forward slashes (Windows provenance);
    - a leading ``./`` is stripped;
    - the path is left relative — absolute paths are *not* repository
      identity (scope carries the repository, not the filesystem).
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


# ══════════════════════════════════════════════════════════════════════════
# IdentitySpec
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class IdentitySpec:
    """Declaration of the canonical identity for one persistable type.

    Attributes:
        model_type: The concrete node class.
        category: Stable artifact category (never a Python class name,
            never a name ending in ``Node``).
        scope_kind: ``project`` / ``repository`` / ``ecosystem``.
        fields: Ordered identity-field names — property names or
            registered computed-provider names.
    """

    model_type: type
    category: str
    scope_kind: str
    fields: tuple[str, ...]

    @property
    def has_computed_fields(self) -> bool:
        return any(f in computed_providers for f in self.fields)


# ══════════════════════════════════════════════════════════════════════════
# The identity matrix (v1)
# ══════════════════════════════════════════════════════════════════════════
#
# Reviewed and frozen as v1 on 2026-08-16.  Ambiguous rows resolved:
#   - test ownership → repository scope (as-built tests are indexed as
#     part of a repository, so they share the repository's identity);
#   - Dependency → (manager_name, qualified_name) with project scope;
#   - Language → (qualified_name, version) with project scope.
# Any change to a row below requires a future key version.

#: Intermediate (non-persistable) model bases registered in the model
#: registry.  They may appear in the deserialization registry but must
#: never define a second identity for a stored entity.
EXEMPT_ABSTRACT: frozenset[str] = frozenset(
    {
        "CompoundNode",  # intermediate base for class/interface/enum/...
        "MemberNode",    # intermediate base for method/attribute/...
        "MemoryNode",    # abstract base for the six memory subtypes
    }
)

#: Declared spec rows: (class name, category, scope kind, fields).
_SPEC_ROWS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # ── Project-level management models (project scope) ───────────
    ("ProjectMeta", "project", PROJECT, ("singleton",)),
    ("Component", "component", PROJECT, ("qualified_name",)),
    ("Dependency", "dependency", PROJECT, ("manager_name", "qualified_name")),
    ("Language", "language", PROJECT, ("qualified_name", "version")),
    # ── Code entities (repository scope) ──────────────────────────
    ("NamespaceNode", "namespace", REPOSITORY, ("qualified_name",)),
    ("ModuleNode", "module", REPOSITORY, ("qualified_name",)),
    ("ClassNode", "class", REPOSITORY, ("qualified_name",)),
    ("InterfaceNode", "interface", REPOSITORY, ("qualified_name",)),
    ("EnumNode", "enum", REPOSITORY, ("qualified_name",)),
    ("UnionNode", "union", REPOSITORY, ("qualified_name",)),
    ("ConceptNode", "concept", REPOSITORY, ("qualified_name",)),
    ("MethodNode", "method", REPOSITORY, ("qualified_name", "canonical_signature")),
    ("FunctionNode", "function", REPOSITORY, ("qualified_name", "canonical_signature")),
    ("AttributeNode", "attribute", REPOSITORY, ("qualified_name",)),
    ("EnumValueNode", "enum-value", REPOSITORY, ("qualified_name",)),
    ("DefineNode", "define", REPOSITORY, ("qualified_name",)),
    ("FileNode", "file", REPOSITORY, ("normalized_repository_path",)),
    ("ParameterNode", "parameter", REPOSITORY, ("parent_callable_key", "position")),
    ("ImplementationNode", "implementation", REPOSITORY, ("parent_callable_key", "kind")),
    ("SourceFragmentNode", "source-fragment", REPOSITORY, ("file_key", "start_line", "end_line")),
    ("LiteralNode", "literal", REPOSITORY, ("qualified_name",)),
    # ── Test ownership → repository scope (v1 decision) ───────────
    ("TestNode", "test", REPOSITORY, ("parent_key", "qualified_name")),
    ("TestFixtureNode", "test-fixture", REPOSITORY, ("parent_key", "qualified_name")),
    ("TestStepNode", "test-step", REPOSITORY, ("parent_key", "qualified_name")),
    ("AssertionNode", "assertion", REPOSITORY, ("parent_key", "qualified_name")),
    # ── Requirements (project scope) ──────────────────────────────
    ("HLR", "requirement-hlr", PROJECT, ("qualified_name",)),
    ("LLR", "requirement-llr", PROJECT, ("parent_hlr_key", "qualified_name")),
    # ── Memory (project scope) ────────────────────────────────────
    ("DecisionNode", "memory-decision", PROJECT, ("qualified_name",)),
    ("ConstraintNode", "memory-constraint", PROJECT, ("qualified_name",)),
    ("RationaleNode", "memory-rationale", PROJECT, ("qualified_name",)),
    ("AssumptionNode", "memory-assumption", PROJECT, ("qualified_name",)),
    ("InsightNode", "memory-insight", PROJECT, ("qualified_name",)),
    ("TradeoffNode", "memory-tradeoff", PROJECT, ("qualified_name",)),
)


def _load_all_models() -> None:
    """Import every model package so the registry is complete.

    Importing the four model packages registers all concrete node types
    into ``CodeGraphNode._registry``.
    """
    import codegraph.models  # noqa: F401
    import codegraph_project.models  # noqa: F401
    import codegraph_memory.models  # noqa: F401
    import codegraph_requirements.models  # noqa: F401


@functools.lru_cache(maxsize=1)
def _build_specs() -> dict[type, IdentitySpec]:
    """Build the type → spec map from the declared matrix rows."""
    _load_all_models()
    from codegraph.models.tags import CodeGraphNode

    specs: dict[type, IdentitySpec] = {}
    for class_name, category, scope_kind, fields in _SPEC_ROWS:
        cls = CodeGraphNode._registry.get(class_name)
        if cls is None:
            raise IdentityError(
                f"identity matrix row {class_name!r} is not a registered "
                f"node type — the matrix is out of sync with the models"
            )
        specs[cls] = IdentitySpec(
            model_type=cls,
            category=category,
            scope_kind=scope_kind,
            fields=fields,
        )
    return specs


def _category_map() -> dict[str, IdentitySpec]:
    """Return category → spec, failing on duplicate categories."""
    result: dict[str, IdentitySpec] = {}
    for spec in _build_specs().values():
        if spec.category in result:
            raise IdentityError(
                f"category {spec.category!r} maps to both "
                f"{result[spec.category].model_type.__name__} and "
                f"{spec.model_type.__name__} — categories must be unique"
            )
        result[spec.category] = spec
    return result


@functools.lru_cache(maxsize=1)
def _category_map_cached() -> dict[str, IdentitySpec]:
    return _category_map()


def spec_for(model_type: type) -> IdentitySpec | None:
    """Return the identity spec for a concrete node type, or None."""
    return _build_specs().get(model_type)


def category_spec(category: str) -> IdentitySpec:
    """Return the spec for a stable artifact category.

    Raises:
        IdentityError: if the category is unknown.
    """
    spec = _category_map_cached().get(category)
    if spec is None:
        raise IdentityError(
            f"unknown artifact category {category!r}; registered categories: "
            f"{sorted(_category_map_cached())}"
        )
    return spec


# ══════════════════════════════════════════════════════════════════════════
# CanonicalIdentity
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CanonicalIdentity:
    """A fully-typed canonical identity for one node.

    Attributes:
        version: Key grammar version (always 1 in v1).
        scope: The validated identity scope.
        category: The stable artifact category.
        values: Ordered ``(field, value)`` pairs matching the spec.
    """

    version: int = KEY_VERSION
    scope: IdentityScope = field(default_factory=lambda: IdentityScope(PROJECT, ""))
    category: str = ""
    values: tuple[tuple[str, str], ...] = ()

    # ── Construction ─────────────────────────────────────────────

    @classmethod
    def from_spec(
        cls,
        spec: IdentitySpec,
        scope: IdentityScope,
        values: dict[str, str],
    ) -> "CanonicalIdentity":
        """Build an identity from a spec, validating the field contract.

        Raises:
            IdentityError: on missing, extra, or reordered fields.
        """
        if set(values) != set(spec.fields):
            raise IdentityError(
                f"identity fields for {spec.model_type.__name__} must be "
                f"exactly {spec.fields}, got {tuple(sorted(values))}"
            )
        ordered = tuple((name, values[name]) for name in spec.fields)
        return cls(
            version=KEY_VERSION,
            scope=scope,
            category=spec.category,
            values=ordered,
        )

    # ── Serialization ────────────────────────────────────────────

    def key(self) -> str:
        """The canonical ``cg:v1`` key string (the wire form)."""
        return encode_key(
            self.scope.scope_kind,
            self.scope.scope_id,
            self.category,
            list(self.values),
        )

    def to_dict(self) -> dict:
        """Portable dict form for reports and wire formats."""
        return {
            "version": self.version,
            "scope_kind": self.scope.scope_kind,
            "scope_id": self.scope.scope_id,
            "category": self.category,
            "fields": dict(self.values),
            "key": self.key(),
        }

    @classmethod
    def from_key(cls, key: str) -> "CanonicalIdentity":
        """Strictly decode and validate a canonical key.

        Rejects unknown versions, scope kinds, categories, and any field
        set that does not exactly match the registered spec for the
        category (missing, repeated, extra, or reordered fields).

        Raises:
            KeyFormatError / IdentityScopeError / IdentityError.
        """
        parsed = parse_key(key)
        if parsed.version not in SUPPORTED_VERSIONS:
            raise KeyFormatError(
                f"unsupported key version {parsed.version}; supported: "
                f"{sorted(SUPPORTED_VERSIONS)}"
            )
        scope = IdentityScope(parsed.scope_kind, parsed.scope_id)
        spec = category_spec(parsed.category)
        field_names = tuple(name for name, _ in parsed.fields)
        if field_names != spec.fields:
            raise KeyFormatError(
                f"key fields {field_names} do not match registered order "
                f"{spec.fields} for category {spec.category!r}"
            )
        return cls(
            version=parsed.version,
            scope=scope,
            category=spec.category,
            values=parsed.fields,
        )

    def short_label(self) -> str:
        """A stable, human-readable short label (replaces ``uid[:8]``).

        Uses the category plus the final identity value (decoded), e.g.
        ``class:codegraph.graph.LayerGraph``.
        """
        if self.values:
            return f"{self.category}:{self.values[-1][1]}"
        return self.category

    def __str__(self) -> str:
        return self.key()


# ══════════════════════════════════════════════════════════════════════════
# Resolution
# ══════════════════════════════════════════════════════════════════════════


def resolve_identity_for(
    node: Any,
    scope: IdentityScope,
    *,
    parents: dict[str, str] | None = None,
) -> CanonicalIdentity:
    """Compute the canonical identity for a node under a resolved scope.

    Reads each spec field from the node — plain properties directly,
    computed providers via :data:`computed_providers`.  Parent-relative
    fields (parameter/implementation/fragment/test children) require
    ``parents``; until WP1.4 wires parent identity through, calling them
    without parents raises :class:`IdentityError`.

    Args:
        node: The node instance.
        scope: The resolved identity scope.
        parents: Optional mapping of parent-identity field name → the
            parent's canonical key (``parent_callable_key``,
            ``parent_hlr_key``, ``parent_key``, ``file_key``).

    Raises:
        IdentityError: if the type has no spec or a required field
            cannot be computed.
    """
    spec = spec_for(type(node))
    if spec is None:
        raise IdentityError(
            f"{type(node).__name__} has no canonical identity spec"
        )
    parents = parents or {}
    values: dict[str, str] = {}
    for field_name in spec.fields:
        provider = computed_providers.get(field_name)
        if provider is not None:
            values[field_name] = provider(node, scope, parents)
        else:
            values[field_name] = str(getattr(node, field_name, "") or "")
    return CanonicalIdentity.from_spec(spec, scope, values)


def short_label(identity: CanonicalIdentity | str) -> str:
    """Short-label helper for keys or identities (display-safe)."""
    if isinstance(identity, CanonicalIdentity):
        return identity.short_label()
    try:
        return CanonicalIdentity.from_key(identity).short_label()
    except (KeyFormatError, IdentityScopeError, IdentityError):
        return str(identity)


# ══════════════════════════════════════════════════════════════════════════
# Audit (Work Package 0.1)
# ══════════════════════════════════════════════════════════════════════════


def audit_registry() -> list[str]:
    """Return a list of identity-registry problems (empty = sound).

    Checks, after importing every model package:

    1. every concrete registered production type has an identity spec;
    2. every matrix row names a registered type (build-time check);
    3. no two concrete types share a category unintentionally;
    4. every spec field is a declared property or a registered computed
       provider;
    5. no intermediate/abstract type is treated as independently
       persistable (they are explicitly exempted).
    """
    _load_all_models()
    from codegraph.models.descriptors import PropertyRegistry
    from codegraph.models.tags import CodeGraphNode

    problems: list[str] = []
    specs = _build_specs()

    # Matrix rows that reference unregistered types are caught at build.
    for cls, spec in specs.items():
        # (4) spec fields must exist as properties or providers
        declared_props = PropertyRegistry.properties_of(cls)
        for field_name in spec.fields:
            if field_name in computed_providers:
                continue
            if field_name not in declared_props:
                problems.append(
                    f"{cls.__name__} spec field {field_name!r} is neither a "
                    f"declared property nor a registered computed provider"
                )

    seen_categories: dict[str, type] = {}
    for cls, spec in specs.items():
        if spec.category in seen_categories:
            problems.append(
                f"category {spec.category!r} maps to both "
                f"{seen_categories[spec.category].__name__} and "
                f"{cls.__name__}"
            )
        else:
            seen_categories[spec.category] = cls

    for name, cls in sorted(CodeGraphNode._registry.items()):
        if not cls.__module__.startswith("codegraph"):
            continue  # test-model pollution guard
        if name in EXEMPT_ABSTRACT:
            continue
        if cls not in specs:
            problems.append(
                f"registered type {name} ({cls.__module__}) has no "
                f"canonical identity spec"
            )
        else:
            spec = specs[cls]
            if spec.scope_kind not in ("project", "repository", "ecosystem"):
                problems.append(
                    f"{name} spec has invalid scope kind {spec.scope_kind!r}"
                )

    # Abstract/intermediate types must not accidentally gain a spec.
    for name in EXEMPT_ABSTRACT:
        cls = CodeGraphNode._registry.get(name)
        if cls is None:
            problems.append(
                f"exempt abstract type {name} is no longer registered"
            )
        elif cls in specs:
            problems.append(
                f"exempt abstract type {name} has an identity spec — "
                f"intermediate types cannot define an identity"
            )

    return problems

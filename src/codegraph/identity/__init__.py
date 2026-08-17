"""Canonical identity — transparent, versioned keys for codegraph nodes.

Work Packages 0.1–1.2 of the Priority 2 plan: the machine-checked
identity registry, the frozen v1 identity matrix, the strict ``cg:v1``
key grammar, and the validated scope value object.

Public surface::

    from codegraph.identity import (
        CanonicalIdentity,     # typed value object: scope + category + fields
        IdentityScope,         # validated (scope_kind, scope_id)
        IdentitySpec,          # declaration: type → category + fields
        resolve_identity_for,  # node + scope → CanonicalIdentity
        audit_registry,        # machine-checked registry audit
        short_label,           # stable display label (replaces uid[:8])
    )

Example::

    scope = IdentityScope.repository("codegraph-suite", "codegraph")
    identity = resolve_identity_for(node, scope)
    key = identity.key()   # cg:v1:repository:codegraph-suite%2Fcodegraph:...
"""

from codegraph.identity.context import (
    get_identity_scope,
    identity_scope,
    resolve_scope,
    set_identity_scope,
)
from codegraph.identity.manifest import (
    MANIFEST_NAME,
    ManifestError,
    find_manifest,
    load_manifest,
    manifest_project_id,
    project_scope,
    repository_scope,
    repository_scopes,
    resolve_scope_from_env,
)
from codegraph.identity.encoding import (
    KeyFormatError,
    ParsedKey,
    VERSION_PREFIX,
    decode_segment,
    encode_key,
    encode_segment,
    parse_key,
)
from codegraph.identity.scope import (
    ECOSYSTEM,
    PROJECT,
    REPOSITORY,
    IdentityScope,
    IdentityScopeError,
)
from codegraph.identity.registry import (
    KEY_VERSION,
    OBSERVATION_TAGS,
    PARENT_FIELDS,
    AmbiguousUidError,
    CanonicalIdentity,
    IdentityConflictError,
    IdentityError,
    IdentitySpec,
    KeyConflictError,
    audit_registry,
    category_spec,
    computed_providers,
    missing_parents,
    observation_pair_coexists,
    parent_relative_fields,
    resolve_identity_for,
    short_label,
    spec_for,
)
from codegraph.identity.signature import normalize_type_spacing

__all__ = [
    # Context
    "get_identity_scope",
    "identity_scope",
    "resolve_scope",
    "set_identity_scope",
    # Manifest (WP6.2)
    "MANIFEST_NAME",
    "ManifestError",
    "find_manifest",
    "load_manifest",
    "manifest_project_id",
    "project_scope",
    "repository_scope",
    "repository_scopes",
    "resolve_scope_from_env",
    # Encoding
    "KeyFormatError",
    "ParsedKey",
    "VERSION_PREFIX",
    "encode_key",
    "encode_segment",
    "decode_segment",
    "parse_key",
    # Scope
    "PROJECT",
    "REPOSITORY",
    "ECOSYSTEM",
    "IdentityScope",
    "IdentityScopeError",
    # Registry
    "KEY_VERSION",
    "AmbiguousUidError",
    "CanonicalIdentity",
    "IdentityConflictError",
    "IdentityError",
    "IdentitySpec",
    "KeyConflictError",
    "OBSERVATION_TAGS",
    "PARENT_FIELDS",
    "audit_registry",
    "category_spec",
    "computed_providers",
    "missing_parents",
    "observation_pair_coexists",
    "parent_relative_fields",
    "resolve_identity_for",
    "short_label",
    "spec_for",
    # Signature
    "normalize_type_spacing",
]

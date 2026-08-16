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
    CanonicalIdentity,
    IdentityError,
    IdentitySpec,
    audit_registry,
    category_spec,
    computed_providers,
    resolve_identity_for,
    short_label,
    spec_for,
)

__all__ = [
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
    "CanonicalIdentity",
    "IdentityError",
    "IdentitySpec",
    "audit_registry",
    "category_spec",
    "computed_providers",
    "resolve_identity_for",
    "short_label",
    "spec_for",
]

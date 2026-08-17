"""Identity-test configuration.

The root conftest registers ``tests.backends.sqlite.conftest`` as a
global plugin (when ``CODEGRAPH_BACKEND=sqlite``), whose autouse
``canonical_identity_scope`` fixture wraps every test in an ambient
repository scope.  The identity suite asserts scope semantics —
unscoped saves must raise, and ``get_identity_scope()`` must return
``None`` outside any ``identity_scope`` block — so the ambient scope is
overridden to a no-op here.  Identity tests manage their own scopes
explicitly (fixed decision 3: scope is never inferred or ambient).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def canonical_identity_scope():
    """Identity tests manage scopes explicitly — no ambient scope."""
    yield

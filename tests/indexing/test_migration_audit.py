from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "audit_ddp_migration.py"
spec = importlib.util.spec_from_file_location("migration_audit", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_normalization_is_order_independent_and_only_removes_approved_volatile_fields():
    first = {"type": "ClassNode", "qualified_name": "codegraph_index.x", "uid": "volatile", "name": "X"}
    second = {"name": "X", "qualified_name": "doxygen_index.x", "type": "ClassNode", "uid": "other"}
    assert audit.normalize(first, package="codegraph_index") == audit.normalize(second, package="doxygen_index")


def test_source_inventory_is_deterministic(tmp_path: Path):
    source = tmp_path / "x.py"
    source.write_text("class Example:\n    def method(self): pass\n\ndef test_example(): assert True\n", encoding="utf-8")
    assert audit.source_inventory(tmp_path) == audit.source_inventory(tmp_path)


def test_policy_requires_explicit_lists():
    import json
    policy = json.loads((Path(__file__).parent / "migration_audit_policy.json").read_text())
    assert policy["allowlisted_behavior_changes"] == []
    assert policy["expected_additions"] == []

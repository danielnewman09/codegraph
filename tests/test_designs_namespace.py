import pytest
from codegraph.designs.namespace import ModuleNode


def test_module_node_defaults():
    mod = ModuleNode()
    assert mod.kind == "module"
    assert mod.name == ""
    assert mod.qualified_name == ""


def test_module_node_llm_dump():
    mod = ModuleNode(name="calc", qualified_name="calc")
    dumped = mod.model_dump(tags={"llm"})
    assert dumped["name"] == "calc"
    assert dumped["qualified_name"] == "calc"
    assert "file_path" not in dumped

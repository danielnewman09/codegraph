"""Tests for the repository layer."""
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode
from codegraph.repositories.compound import CompoundRepository
from codegraph.repositories.member import MemberRepository
from codegraph.repositories.namespace import NamespaceRepository
from codegraph.repositories.file import FileRepository
from codegraph.repositories.parameter import ParameterRepository


class TestCompoundRepository:
    def test_save_and_get(self):
        repo = CompoundRepository()
        c = CompoundNode(qualified_name="calc::Calc", kind="class")
        repo.save(c)
        retrieved = repo.get("calc::Calc")
        assert retrieved is not None
        assert retrieved.kind == "class"

    def test_get_returns_none_for_missing(self):
        repo = CompoundRepository()
        assert repo.get("nonexistent::Foo") is None

    def test_find_by_layer(self):
        repo = CompoundRepository()
        CompoundNode(qualified_name="calc::A", kind="class", layer="design").save()
        CompoundNode(qualified_name="calc::B", kind="class", layer="as-built").save()
        CompoundNode(qualified_name="calc::C", kind="class", layer="design").save()
        design = repo.find_by_layer("design")
        assert len(design) == 2

    def test_bulk_save(self):
        repo = CompoundRepository()
        nodes = [
            CompoundNode(qualified_name="calc::X", kind="class"),
            CompoundNode(qualified_name="calc::Y", kind="struct"),
        ]
        saved = repo.bulk_save(nodes)
        assert len(saved) == 2
        assert repo.get("calc::X") is not None
        assert repo.get("calc::Y") is not None

    def test_delete_all_design_layer(self):
        repo = CompoundRepository()
        CompoundNode(qualified_name="calc::D", kind="class", layer="design").save()
        CompoundNode(qualified_name="calc::E", kind="class", layer="as-built").save()
        count = repo.delete_all_design_layer()
        assert count == 1
        assert repo.get("calc::D") is None
        assert repo.get("calc::E") is not None

    def test_connect_member(self):
        repo = CompoundRepository()
        c = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        m = MemberNode(qualified_name="calc::Calc::add", kind="method").save()
        repo.connect_member("calc::Calc", "calc::Calc::add")
        members = repo.get_members("calc::Calc")
        assert len(members) == 1
        assert members[0].qualified_name == "calc::Calc::add"

    def test_connect_base(self):
        repo = CompoundRepository()
        child = CompoundNode(qualified_name="calc::Child", kind="class").save()
        parent = CompoundNode(qualified_name="calc::Parent", kind="class").save()
        repo.connect_base("calc::Child", "calc::Parent")
        retrieved = repo.get("calc::Child")
        bases = list(retrieved.base.all())
        assert len(bases) == 1
        assert bases[0].qualified_name == "calc::Parent"


class TestMemberRepository:
    def test_save_and_get(self):
        repo = MemberRepository()
        m = MemberNode(qualified_name="calc::Foo::bar", kind="method")
        repo.save(m)
        retrieved = repo.get("calc::Foo::bar")
        assert retrieved is not None
        assert retrieved.kind == "method"

    def test_bulk_save(self):
        repo = MemberRepository()
        nodes = [
            MemberNode(qualified_name="calc::Foo::x", kind="variable"),
            MemberNode(qualified_name="calc::Foo::y", kind="variable"),
        ]
        repo.bulk_save(nodes)
        assert repo.get("calc::Foo::x") is not None
        assert repo.get("calc::Foo::y") is not None


class TestNamespaceRepository:
    def test_save_and_get(self):
        repo = NamespaceRepository()
        n = NamespaceNode(qualified_name="std")
        repo.save(n)
        retrieved = repo.get("std")
        assert retrieved is not None

    def test_connect_compound(self):
        repo = NamespaceRepository()
        ns = NamespaceNode(qualified_name="calc").save()
        c = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        repo.connect_compound("calc", "calc::Calc")
        retrieved = repo.get("calc")
        compounds = list(retrieved.compounds.all())
        assert len(compounds) == 1
        assert compounds[0].qualified_name == "calc::Calc"


class TestFileRepository:
    def test_save_and_get(self):
        repo = FileRepository()
        f = FileNode(refid="file_123")
        repo.save(f)
        retrieved = repo.get("file_123")
        assert retrieved is not None


class TestParameterRepository:
    def test_save_and_find(self):
        repo = ParameterRepository()
        p = ParameterNode(position=0, name="x", member_refid="ref_abc").save()
        results = repo.find_by_member_refid("ref_abc")
        assert len(results) == 1
        assert results[0].name == "x"

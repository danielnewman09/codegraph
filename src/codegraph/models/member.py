"""Member node models — stubs for compound relationship imports."""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty


class MethodNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="method")


class AttributeNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="attribute")


class EnumValueNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="enumvalue")


class FunctionNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="function")


class DefineNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="define")

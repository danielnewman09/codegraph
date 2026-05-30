# Codegraph

Shared Neo4j codebase graph data model.

Provides Pydantic models for codebase graph nodes (`File`, `Namespace`,
`Compound`, `Member`, `Parameter`), edge definitions (`CodebaseEdge`),
and constants (kinds, layers, predicates, schema DDL).

Used by:
- [Doxygen Dependency Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser) — populates `as-built` and `dependency` layers
- [Ticketing System](https://github.com/danielnewman09/ticketing-system) — adds the `design` layer

## Install

```bash
pip install codegraph
```

## Usage

```python
from codegraph import CompoundNode, MemberNode, CodebaseEdge

# Create a design-layer class
calc = CompoundNode(
    qualified_name="calc::Calculator",
    name="Calculator",
    kind="class",
    layer="design",
    protection="public",
)

# Add a method
add = MemberNode(
    qualified_name="calc::Calculator::add",
    name="add",
    kind="method",
    layer="design",
    type_signature="int",
    argsstring="(int a, int b)",
    protection="public",
)

# Define a relationship
edge = CodebaseEdge(
    subject_qualified_name="calc::Calculator",
    predicate="composes",
    object_qualified_name="calc::Calculator::add",
)

# Serialize to dict for Neo4j driver
calc_dict = calc.model_dump()
```

The implementation plan has been written to `docs/plans/2026-06-07-to-dict-from-dict.md`. Here's a summary of the 11 tasks:

| Task | Description |
|---|---|
| 1 | Add `CodeGraphNode.to_dict()` — node-level full-fidelity serialization |
| 2 | Add `CodeGraphNode.from_dict()` — node-level deserialization; refactor `from_json()` to delegate |
| 3 | Add `CompositeEntry.to_dict()` — entry-level serialization with composes and references |
| 4 | Add `CompositeEntry.from_dict()` — entry-level deserialization |
| 5 | Add `LayerGraph.to_dict()` — graph-level serialization with layer metadata |
| 6 | Add `LayerGraph.from_dict()` — graph-level deserialization (dict + legacy bare-list format) |
| 7 | Refactor `serialize()` to delegate to `to_dict(fields="llm")` |
| 8 | Refactor `LayerGraph._serialize_entry()` into `CompositeEntry.to_dict()` + `_json_serialize_entry` |
| 9 | Refactor `LayerGraph.from_json()` to delegate to `from_dict()` |
| 10 | Consolidate JSON import logic (flatten `_from_json_nested`/`_from_json_flat` into `from_dict()`) |
| 11 | Run full test suite and fix any failures |

The plan is in `docs/plans/2026-06-07-to-dict-from-dict.md` and matches the spec at GitHub Issue #3.
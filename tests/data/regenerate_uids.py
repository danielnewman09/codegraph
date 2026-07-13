"""Regenerate UIDs in design_graph.json to match the current _compute_uid().

After the UID algorithm change (now includes 'source' in the hash), the
fixture UIDs are stale. This script recomputes each node's UID using the
current algorithm and updates node data + edge target_local_id references.
"""
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "design_graph.json"


def main():
    with open(FIXTURE) as f:
        data = json.load(f)

    from codegraph.graph import LayerGraph
    from codegraph.models.tags import CodeGraphNode

    # Build mapping: old_uid -> new_uid
    uid_map: dict[str, str] = {}

    for node_data in data:
        old_uid = node_data.get("uid", "")
        if not old_uid:
            continue

        # Remove the old uid so deserialize computes a fresh one
        node_data_copy = dict(node_data)
        node_data_copy.pop("uid", None)

        # Deserialize — this will compute a fresh deterministic uid
        # because uid is missing from data
        node = CodeGraphNode.deserialize(node_data_copy)
        new_uid = node._uid_value()
        if new_uid and new_uid != old_uid:
            uid_map[old_uid] = new_uid
            print(f"  {node_data.get('type'):16s} {old_uid[:20]}... -> {new_uid[:20]}...")

    if not uid_map:
        print("All UIDs are already up to date.")
        return

    print(f"\nUpdating {len(uid_map)} UIDs across {len(data)} nodes...")

    # Update node UIDs and edge references
    for node_data in data:
        old_uid = node_data.get("uid", "")
        if old_uid in uid_map:
            node_data["uid"] = uid_map[old_uid]

        for edge in node_data.get("edges", []):
            old_tid = edge.get("target_local_id", "")
            if old_tid in uid_map:
                edge["target_local_id"] = uid_map[old_tid]

    with open(FIXTURE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"Wrote {FIXTURE}")


if __name__ == "__main__":
    main()

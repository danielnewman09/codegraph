# Neo4j Backup & Restore

> **Date:** 2026-06-25
> **Status:** operational
> **Scripts:** `scripts/backup-neo4j.sh`, `scripts/restore-neo4j.sh`
> **Scheduling:** `scripts/com.codegraph.neo4j-backup.plist` (launchd, daily at 03:00)

---

## Overview

The Neo4j knowledge graph is a destructive target — re-indexing via
`doxygen-index` can clobber enriched descriptions, and `--clear` wipes
the entire database.  The backup system protects against data loss
with portable `neo4j-admin` logical dumps, automated daily backups,
and a tested restore procedure.

### Risk factors

| Risk | Consequence | Mitigation |
|---|---|---|
| `doxygen-index --clear` (full reindex) | Destroys all nodes and relationships | Restore from backup |
| `doxygen-index` (incremental, default) | Overwrites enriched `description` fields with parser defaults (`""`) | Restore from backup, or use `scripts/reingest_enrichment.py` |
| Accidental container removal with `--volumes` | Permanent loss of all data | Backup is stored outside the container bind-mount |
| Disk corruption / OS failure | Data loss | Off-machine backup (manual copy to external drive / cloud) |

---

## Backup architecture

```
codegraph/neo4j/
├── data/          ← bind-mounted into container at /data
├── logs/          ← container logs + backup.log
├── import/        ← bulk-import CSV staging
├── plugins/       ← APOC, etc.
└── backups/       ← dump files (gitignored, kept outside container)
    ├── neo4j-20260625-132113.dump
    ├── neo4j-data-20260625-*.tar.gz   (safety backups from restore)
    └── ...
```

### Dump format

Backups use `neo4j-admin database dump`, which produces a **portable
logical dump** in Neo4j 5.x Zstandard-compressed format (magic: `DZV1`).
These dumps can be restored to any Neo4j 5.x Community Edition instance,
regardless of hardware or filesystem.

At time of writing, a full codegraph database (21,187 nodes, 11
relationship types, ~803 MB data directory) produces an ~81 MB dump
file.

### Two backup modes

| Mode | Command | Pros | Cons |
|---|---|---|---|
| **dump** | `backup-neo4j.sh` | Portable across instances; compact; integrity-checked | Requires stopping Neo4j (~30s downtime) |
| **tar** | `backup-neo4j.sh --tar` | Fast; no container stop needed (if DB idle) | Filesystem-dependent; not portable across OS/architectures |

Dump mode is the recommended default.  Tar mode is used automatically
as a pre-restore safety net in `restore-neo4j.sh`.

---

## Manual backup

```bash
# Standard logical dump (recommended)
scripts/backup-neo4j.sh

# Filesystem-level tar backup
scripts/backup-neo4j.sh --tar

# Keep only the last 7 backups (rotation)
scripts/backup-neo4j.sh --keep 7
```

The container is stopped during dump mode (typically < 30 seconds)
and restarted automatically.  Backups are written to
`codegraph/neo4j/backups/` with timestamps:

```
neo4j-20260625-132113.dump
```

---

## Automated daily backups (launchd)

A launchd plist schedules a daily backup at 03:00 local time, keeping
the last 7 dump files:

```bash
# Install
launchctl load ~/Library/LaunchAgents/com.codegraph.neo4j-backup.plist

# Check status
launchctl list | grep codegraph

# Uninstall (stop daily backups)
launchctl unload ~/Library/LaunchAgents/com.codegraph.neo4j-backup.plist
```

Logs are written to `codegraph/neo4j/logs/backup.log`.

> **Note:** The plist contains an absolute path to the backup script.
> If you move the project, update the `ProgramArguments` path and reload.

---

## Restore

```bash
scripts/restore-neo4j.sh <backup-file>
```

The restore script accepts:
- A `.dump` file (neo4j-admin logical dump)
- A `.tar.gz` file (filesystem-level backup)

### Restore workflow

1. Creates a **safety backup** of the current database state (tar mode)
2. Stops the Neo4j container
3. Wipes the current data directory
4. Restores from the backup file
5. Fixes file permissions for the Neo4j container user (uid 7474)
6. Starts the container

After restore, wait ~10 seconds for Neo4j to become ready, then verify:

```bash
codegraph-db status
```

---

## Restore validation (2026-06-25)

The dump → restore pipeline was validated end-to-end in an isolated test
container on different ports with a separate data directory:

| Check | Result |
|---|---|
| Total nodes | 21,187 restored |
| As-built tagged nodes | 3,227 (exact match) |
| Relationship types | 11 — all intact (COMPOSES, VERIFIES, CALLEE, INHERITS_FROM, etc.) |
| Test → code graph | TestNode → VERIFIES → CompoundNode chains verified |
| Call graph | TestStepNode → CALLEE → MemberNode chains verified |
| Inheritance | INHERITS_FROM relationships intact |
| Property keys | All 38 property keys present |

### Test restore procedure

To validate a dump without touching the production database:

```bash
# 1. Create a test data directory
TEST_DATA=/tmp/neo4j-restore-test-data
rm -rf "$TEST_DATA"
mkdir -p "$TEST_DATA" "$TEST_DATA/logs"

# 2. Run restore in an isolated container
docker run -d --name neo4j-codegraph-restore-test \
    -p 17687:7687 -p 17474:7474 \
    -v "$TEST_DATA:/data" \
    -v "$TEST_DATA/logs:/logs" \
    -v "$PWD/codegraph/neo4j/backups:/backups:ro" \
    -e NEO4J_AUTH=neo4j/codegraph \
    neo4j:5-community

# 3. Wait for startup, then load the dump
sleep 15
docker run --rm \
    -v "$TEST_DATA:/data" \
    -v "$PWD/codegraph/neo4j/backups:/backups:ro" \
    neo4j:5-community \
    neo4j-admin database load neo4j \
        --from-path=/backups \
        --overwrite-destination=true

# 4. Restart and verify
docker restart neo4j-codegraph-restore-test
sleep 10
cypher-shell -a bolt://localhost:17687 -u neo4j -p codegraph \
    "MATCH (n) RETURN count(n)"

# 5. Clean up
docker stop neo4j-codegraph-restore-test
docker rm neo4j-codegraph-restore-test
rm -rf "$TEST_DATA"
```

> **Important:** `neo4j-admin database load --from-path` expects a
> **directory** containing the dump file (named `<dbname>.dump`), not
> the dump file itself.  The `restore-neo4j.sh` script handles this
> automatically by staging the dump in a temp directory.

---

## Integration with disaster recovery

### Recovering enriched descriptions without full restore

If only the enriched `description` properties were clobbered (by a
reindex without `--clear`), you can recover them from the LLM response
logs without restoring the entire database:

```bash
python scripts/reingest_enrichment.py
```

This parses `codegraph/logs/*_response.md` files and writes back the
LLM-generated descriptions via batched Cypher queries.

### Full disaster recovery checklist

1. **Stop the container:** `codegraph-db stop`
2. **Rename the corrupt data dir** (keep as forensic copy):
   `mv codegraph/neo4j/data codegraph/neo4j/data.corrupt`
3. **Restore from latest backup:**
   `scripts/restore-neo4j.sh codegraph/neo4j/backups/neo4j-<latest>.dump`
4. **Re-apply enrichment** (if backup predates last enrichment run):
   `python -m codegraph_enrich.cli --all --tag as-built`
5. **Verify:** `codegraph-db status`

---

## Manual off-machine backup

Dump files are gitignored and local-only.  Periodically copy them to
an external drive or cloud storage:

```bash
# Copy all backups to an external volume
rsync -av codegraph/neo4j/backups/ /Volumes/Backup/codegraph-neo4j/

# Or archive a specific backup
gzip -c codegraph/neo4j/backups/neo4j-20260625-132113.dump \
    > ~/Desktop/codegraph-neo4j-backup.dump.gz
```

---

## See also

- [reingest_enrichment.py](../../scripts/reingest_enrichment.py) — recover enriched descriptions from LLM logs
- [README.md](../../README.md) — Neo4j Docker container management (`codegraph-db`)
- [Neo4j admin docs](https://neo4j.com/docs/operations-manual/current/backup-restore/) — upstream backup/restore reference

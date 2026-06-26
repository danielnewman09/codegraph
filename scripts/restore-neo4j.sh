#!/bin/bash
# Restore the Neo4j codegraph database from a backup.
#
# Usage:
#   scripts/restore-neo4j.sh <backup-file>
#
# The backup file can be:
#   - A neo4j-admin dump file   (*.dump)
#   - A tar.gz of the data dir  (*.tar.gz)
#
# WARNING: This DESTROYS the current database.  The script stops
# the container, wipes the data directory, restores, and restarts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/codegraph/neo4j/backups"
DATA_DIR="$PROJECT_DIR/codegraph/neo4j/data"
CONTAINER="neo4j-codegraph"
IMAGE="neo4j:5-community"
DB_NAME="neo4j"

BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup-file>"
    echo ""
    echo "Available backups:"
    ls -1th "$BACKUP_DIR/" 2>/dev/null || echo "  (none found)"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    # Try relative to backup dir
    if [[ -f "$BACKUP_DIR/$BACKUP_FILE" ]]; then
        BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
    else
        echo "ERROR: backup file not found: $BACKUP_FILE"
        exit 1
    fi
fi

echo "=== Restore started at $(date) ==="
echo "  Backup:  $BACKUP_FILE"
echo "  Data:    $DATA_DIR"

# ── Auto-backup current state first ─────────────────────────────

echo ""
echo "Creating safety backup of current state before restore ..."
"$SCRIPT_DIR/backup-neo4j.sh" --tar

# ── Stop ────────────────────────────────────────────────────────

docker stop "$CONTAINER" 2>/dev/null || true

# ── Wipe ────────────────────────────────────────────────────────

echo "Wiping current data ..."
rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"

# ── Restore ─────────────────────────────────────────────────────

if [[ "$BACKUP_FILE" == *.dump ]]; then
    echo "Restoring from neo4j-admin dump ..."
    # neo4j-admin load requires --from-path to be a *directory* containing the dump
    # (named <dbname>.dump). Create a staging dir with the correct filename.
    STAGING="$(mktemp -d)"
    cp "$BACKUP_FILE" "$STAGING/neo4j.dump"
    docker run --rm \
        -v "$DATA_DIR:/data" \
        -v "$STAGING:/backups:ro" \
        "$IMAGE" \
        neo4j-admin database load "$DB_NAME" \
            --from-path=/backups \
            --overwrite-destination=true
    rm -rf "$STAGING"

elif [[ "$BACKUP_FILE" == *.tar.gz ]]; then
    echo "Restoring from tar archive ..."
    tar -xzf "$BACKUP_FILE" -C "$PROJECT_DIR/codegraph/neo4j"

else
    echo "ERROR: unrecognized backup format (expected .dump or .tar.gz)"
    exit 1
fi

# ── Fix permissions ─────────────────────────────────────────────

# Neo4j container runs as user neo4j (uid 7474); ensure ownership
echo "Fixing permissions ..."
chmod -R u+rwX "$DATA_DIR"

# ── Start ───────────────────────────────────────────────────────

echo "Starting $CONTAINER ..."
docker start "$CONTAINER"

echo ""
echo "=== Restore complete at $(date) ==="
echo "Neo4j is starting — wait ~10s for it to become ready."

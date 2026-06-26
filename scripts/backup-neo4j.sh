#!/bin/bash
# Backup the Neo4j codegraph database using neo4j-admin dump.
# Produces a portable, consistent logical dump that can be restored
# to any Neo4j 5.x Community Edition instance.
#
# Usage:
#   scripts/backup-neo4j.sh              # standard dump backup
#   scripts/backup-neo4j.sh --tar        # fast tar backup (filesystem-level)
#   scripts/backup-neo4j.sh --keep 7     # keep only last 7 backups
#
# The database must be offline during dump, so the container is
# briefly stopped.  Downtime is typically < 30 seconds.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/codegraph/neo4j/backups"
CONTAINER="neo4j-codegraph"
IMAGE="neo4j:5-community"
DB_NAME="neo4j"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

MODE="dump"
KEEP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tar)    MODE="tar" ;;
        --keep)   KEEP="$2"; shift ;;
        --help)   echo "Usage: $0 [--tar] [--keep N]"; exit 0 ;;
        *)        echo "Unknown flag: $1"; exit 1 ;;
    esac
    shift
done

mkdir -p "$BACKUP_DIR"

# ── Pre-flight ──────────────────────────────────────────────────

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "ERROR: container '$CONTAINER' is not running"
    echo "Start it with: codegraph_setup db_start"
    exit 1
fi

echo "=== Neo4j backup started at $(date) ==="
echo "  Mode:      $MODE"
echo "  Container: $CONTAINER"
echo "  Backups:   $BACKUP_DIR"

# ── Stop Neo4j ──────────────────────────────────────────────────

echo "Stopping $CONTAINER ..."
docker stop "$CONTAINER"

# ── Create backup ───────────────────────────────────────────────

BACKUP_FILE=""

if [[ "$MODE" == "dump" ]]; then
    echo "Creating logical dump via neo4j-admin ..."
    docker run --rm \
        -v "$PROJECT_DIR/codegraph/neo4j/data:/data" \
        -v "$BACKUP_DIR:/backups" \
        "$IMAGE" \
        neo4j-admin database dump "$DB_NAME" --to-path=/backups

    # neo4j-admin names the dump "<dbname>.dump"
    BACKUP_FILE="$BACKUP_DIR/neo4j-${TIMESTAMP}.dump"
    mv "$BACKUP_DIR/neo4j.dump" "$BACKUP_FILE"

elif [[ "$MODE" == "tar" ]]; then
    echo "Creating tar backup of data directory ..."
    BACKUP_FILE="$BACKUP_DIR/neo4j-data-${TIMESTAMP}.tar.gz"
    tar -czf "$BACKUP_FILE" -C "$PROJECT_DIR/codegraph/neo4j" data
fi

# ── Restart Neo4j ───────────────────────────────────────────────

echo "Starting $CONTAINER ..."
docker start "$CONTAINER"

# ── Verify ──────────────────────────────────────────────────────

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup: $BACKUP_FILE  ($SIZE)"

if [[ "$MODE" == "dump" ]]; then
    # Neo4j 5.x dumps use Zstandard-compressed format (magic: DZV1)
    MAGIC=$(head -c 4 "$BACKUP_FILE")
    if [[ "$MAGIC" == "DZV1" ]]; then
        echo "Integrity: header check PASSED (Neo4j 5.x Zstd dump)"
    else
        echo "WARNING: unexpected dump header '$MAGIC' — file may be corrupt"
    fi
fi

# ── Retention ───────────────────────────────────────────────────

if [[ -n "$KEEP" ]]; then
    echo "Rotating backups: keeping last $KEEP ..."
    cd "$BACKUP_DIR"
    # List files sorted by time, oldest first; delete all but the last $KEEP
    if [[ "$MODE" == "dump" ]]; then
        ls -1t neo4j-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -v
    else
        ls -1t neo4j-data-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -v
    fi
fi

echo "=== Backup complete at $(date) ==="

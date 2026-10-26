#!/bin/sh
# Daily backup: PostgreSQL dump + media → tarball → off-server (rclone remote). Run by cron on the host:
#   15 3 * * *  cd /opt/manasety/app && sh deploy/backup.sh >> /var/log/manasety-backup.log 2>&1
set -eu
cd "$(dirname "$0")/.."
. ./.env
STAMP=$(date -u +%Y%m%d-%H%M%S)
DIR=/opt/manasety/backups
STATUS=/opt/manasety/instance/backup-status.json
mkdir -p "$DIR"
OUT="$DIR/manasety-$STAMP.tar.gz"

fail() {
  printf '{"ok": false, "finished_at": "%s", "error": "%s"}\n' "$(date -u +%FT%TZ)" "$1" > "$STATUS"
  exit 1
}

docker compose exec -T db pg_dump -U manasety -Fc manasety > "$DIR/db-$STAMP.dump" || fail "pg_dump failed"
tar -czf "$OUT" -C "$DIR" "db-$STAMP.dump" -C /opt/manasety media instance/backup-status.json 2>/dev/null \
  || tar -czf "$OUT" -C "$DIR" "db-$STAMP.dump" -C /opt/manasety media || fail "tar failed"
rm -f "$DIR/db-$STAMP.dump"

REMOTE="${BACKUP_REMOTE:-}"
if [ -n "$REMOTE" ]; then
  rclone copy "$OUT" "$REMOTE/" || fail "upload to $REMOTE failed"
else
  fail "BACKUP_REMOTE not set: backup kept on this server only"
fi

# keep 14 local copies
ls -1t "$DIR"/manasety-*.tar.gz | tail -n +15 | xargs -r rm -f
SIZE=$(du -h "$OUT" | cut -f1)
LAST_TEST=$(cat /opt/manasety/instance/last-restore-test 2>/dev/null || echo "")
printf '{"ok": true, "finished_at": "%s", "file": "%s", "size": "%s", "remote": "%s", "last_restore_test": "%s"}\n' \
  "$(date -u +%FT%TZ)" "$(basename "$OUT")" "$SIZE" "$REMOTE" "$LAST_TEST" > "$STATUS"

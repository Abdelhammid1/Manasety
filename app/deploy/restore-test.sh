#!/bin/sh
# Periodic restore test (run on STAGING, never production):
#   sh deploy/restore-test.sh /opt/manasety/backups/manasety-YYYYmmdd-HHMMSS.tar.gz
set -eu
ARCHIVE="$1"
WORK=$(mktemp -d)
tar -xzf "$ARCHIVE" -C "$WORK"
DUMP=$(ls "$WORK"/db-*.dump | head -n1)
docker compose exec -T db dropdb -U manasety --if-exists manasety_restore_test
docker compose exec -T db createdb -U manasety manasety_restore_test
docker compose exec -T db pg_restore -U manasety -d manasety_restore_test < "$DUMP"
ROWS=$(docker compose exec -T db psql -U manasety -d manasety_restore_test -tAc "select count(*) from sections")
[ "$ROWS" -gt 0 ] || { echo "restore produced no sections"; exit 1; }
date -u +%FT%TZ > /opt/manasety/instance/last-restore-test
rm -rf "$WORK"
echo "restore OK: $ROWS sections"

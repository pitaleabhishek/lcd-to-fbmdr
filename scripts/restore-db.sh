#!/usr/bin/env bash
# Restore an encrypted backup. This is destructive: it drops and recreates
# objects in the target database. Stop the web service first and require an
# explicit confirmation.
set -euo pipefail

: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
file="${1:?usage: $0 <backup.dump.enc>}"
if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
  echo "set RESTORE_CONFIRM=yes to confirm the destructive restore" >&2
  exit 1
fi
[ -f "$file" ] || { echo "no such backup: $file" >&2; exit 1; }

openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass env:BACKUP_PASSPHRASE -in "$file" \
  | docker compose exec -T db sh -c \
      'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" \
       -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges'

echo "restored $file"

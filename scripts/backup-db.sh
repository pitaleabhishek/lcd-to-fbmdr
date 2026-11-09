#!/usr/bin/env bash
# Encrypted Postgres backup. The dump is piped straight into OpenSSL; plaintext
# never touches the disk. Keep BACKUP_PASSPHRASE separate from the backup file.
set -euo pipefail

: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE to a long passphrase}"
if [ "${#BACKUP_PASSPHRASE}" -lt 16 ]; then
  echo "BACKUP_PASSPHRASE must be at least 16 characters" >&2
  exit 1
fi

mkdir -p backups
umask 077
stamp="$(date +%Y%m%d-%H%M%S)"
out="backups/mdr-${stamp}.dump.enc"

docker compose exec -T db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
   --format=custom --no-owner --no-privileges' \
  | openssl enc -aes-256-cbc -pbkdf2 -salt \
      -pass env:BACKUP_PASSPHRASE -out "$out"

chmod 600 "$out"
echo "wrote $out"
echo "store the passphrase separately; the backup cannot be opened without it"

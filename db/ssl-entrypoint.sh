#!/bin/sh
# Generate a local self-signed certificate for Postgres TLS before the server
# starts. This is a development/demo certificate: clients use sslmode=require,
# which encrypts the connection without claiming a public CA identity.
set -e

CERT_DIR="$(dirname "${PGDATA:-/var/lib/postgresql/data}")/server-certs"
mkdir -p "$CERT_DIR"

if [ ! -s "$CERT_DIR/server.crt" ] || [ ! -s "$CERT_DIR/server.key" ]; then
  if ! openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.crt" \
    -subj "/CN=db" \
    -addext "subjectAltName=DNS:db,DNS:localhost,IP:127.0.0.1" \
    >/dev/null 2>&1; then
    echo "could not generate the Postgres TLS certificate" >&2
    exit 1
  fi
fi

chown postgres:postgres "$CERT_DIR/server.key" "$CERT_DIR/server.crt"
chmod 600 "$CERT_DIR/server.key"
chmod 644 "$CERT_DIR/server.crt"

exec docker-entrypoint.sh "$@"

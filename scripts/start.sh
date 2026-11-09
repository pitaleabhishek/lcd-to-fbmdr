#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed."
  echo "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  echo "On Linux, install Docker Engine and the Compose plugin."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed, but the Docker daemon is not running."
  echo "Start Docker Desktop or the Docker service, then run this script again."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  compose="docker-compose"
else
  echo "Docker Compose is not installed."
  echo "Install the Compose plugin, then run this script again."
  exit 1
fi

echo "Starting Postgres..."
$compose up -d db

echo "Waiting for Postgres..."
tries=0
until $compose exec -T db pg_isready -U mdr -d mdr >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 60 ]; then
    echo
    echo "Postgres did not become ready."
    echo "Run: $compose logs db"
    exit 1
  fi
  printf "."
  sleep 2
done
echo

echo "Building the app..."
$compose build web

echo "Running migrations and demo setup..."
$compose run --rm web python manage.py demo_setup

echo "Starting the app..."
$compose up -d web

cat <<EOF

LCD to FBMDR is running.

  URL:      http://127.0.0.1:8000
  Resident: resident / resident123
  FNO:      fno / fno123

Stop it with: $compose down
Reset it with: $compose down -v && ./start.sh
EOF

if [ "${NO_BROWSER:-0}" != "1" ]; then
  if command -v open >/dev/null 2>&1; then
    open http://127.0.0.1:8000
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 || true
  fi
fi

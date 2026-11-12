$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed."
    Write-Host "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is installed, but the Docker daemon is not running."
    Write-Host "Start Docker Desktop, then run this script again."
    exit 1
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Compose is not installed."
    Write-Host "Install the Compose plugin, then run this script again."
    exit 1
}

Write-Host "Starting Postgres..."
docker compose up -d db

Write-Host "Waiting for Postgres..."
$tries = 0
while ($true) {
    docker compose exec -T db pg_isready -U mdr -d mdr *> $null
    if ($LASTEXITCODE -eq 0) { break }
    $tries++
    if ($tries -ge 60) {
        Write-Host "Postgres did not become ready."
        Write-Host "Run: docker compose logs db"
        exit 1
    }
    Start-Sleep -Seconds 2
}

Write-Host "Building the app..."
docker compose build web

Write-Host "Running migrations and demo setup..."
docker compose run --rm web python manage.py demo_setup
if ($LASTEXITCODE -ne 0) {
    Write-Host "Demo setup failed."
    exit 1
}

Write-Host "Starting the app..."
docker compose up -d web

Write-Host ""
Write-Host "LCG to FBMDR is running."
Write-Host "  URL:      http://127.0.0.1:8000"
Write-Host "  Resident: resident / resident123"
Write-Host "  FNO:      fno / fno123"
Write-Host ""
Write-Host "Stop it with: docker compose down"
Write-Host "Reset it with: docker compose down -v; .\start.ps1"

Start-Process "http://127.0.0.1:8000"

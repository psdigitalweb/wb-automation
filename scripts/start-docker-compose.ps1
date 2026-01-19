# Script to start Docker Compose for EcomCore
# Handles port conflicts by stopping conflicting containers
# Usage: .\scripts\start-docker-compose.ps1

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "=== EcomCore Docker Compose Startup ===" -ForegroundColor Cyan

# Navigate to docker compose directory
$composeDir = Join-Path $PSScriptRoot ".." "infra" "docker"
if (-not (Test-Path $composeDir)) {
    Write-Host "Error: docker-compose.yml not found at $composeDir" -ForegroundColor Red
    exit 1
}

Set-Location $composeDir
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Gray

# Check for port 8000 conflicts
Write-Host "`n=== Checking for port 8000 conflicts ===" -ForegroundColor Cyan
$port8000Containers = docker ps -a --filter "publish=8000" --format "{{.Names}}" 2>$null
if ($port8000Containers) {
    Write-Host "Found containers using port 8000:" -ForegroundColor Yellow
    $port8000Containers | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    
    if ($Force) {
        Write-Host "Stopping conflicting containers..." -ForegroundColor Yellow
        $port8000Containers | ForEach-Object {
            Write-Host "  Stopping $_..." -ForegroundColor Gray
            docker stop $_ 2>$null | Out-Null
            docker rm $_ 2>$null | Out-Null
        }
        Write-Host "Conflicting containers stopped." -ForegroundColor Green
    } else {
        Write-Host "`nPort 8000 is in use. Options:" -ForegroundColor Yellow
        Write-Host "  1. Run with -Force to stop conflicting containers:" -ForegroundColor Cyan
        Write-Host "     .\scripts\start-docker-compose.ps1 -Force" -ForegroundColor White
        Write-Host "  2. Or manually stop the containers:" -ForegroundColor Cyan
        $port8000Containers | ForEach-Object {
            Write-Host "     docker stop $_" -ForegroundColor White
        }
        exit 1
    }
}

# Check for other conflicting containers from old projects
Write-Host "`n=== Checking for old docker-* containers ===" -ForegroundColor Cyan
$oldContainers = docker ps -a --filter "name=docker-" --format "{{.Names}}" 2>$null
if ($oldContainers) {
    Write-Host "Found old containers (docker-*):" -ForegroundColor Yellow
    $oldContainers | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    if ($Force) {
        Write-Host "Stopping old containers..." -ForegroundColor Yellow
        docker compose -p docker down 2>$null | Out-Null
        Write-Host "Old containers stopped." -ForegroundColor Green
    }
}

# Stop existing ecomcore containers
Write-Host "`n=== Stopping existing ecomcore containers ===" -ForegroundColor Cyan
docker compose down 2>$null | Out-Null

# Start services
Write-Host "`n=== Starting Docker Compose services ===" -ForegroundColor Cyan
docker compose up -d --build

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: docker compose up failed" -ForegroundColor Red
    exit 1
}

# Wait for services to start
Write-Host "`n=== Waiting for services to start (10 seconds) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Check status
Write-Host "`n=== Service Status ===" -ForegroundColor Cyan
docker compose ps

Write-Host "`n=== Service URLs ===" -ForegroundColor Cyan
Write-Host "  Frontend:  http://localhost" -ForegroundColor Green
Write-Host "  API:       http://localhost:8000" -ForegroundColor Green
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Adminer:   http://localhost/adminer/ (requires auth)" -ForegroundColor Green

Write-Host "`n=== Done! ===" -ForegroundColor Green

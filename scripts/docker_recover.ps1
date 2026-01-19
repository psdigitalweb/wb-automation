# Docker Recovery Script for EcomCore
# Cleans up Docker resources for this project to resolve filesystem/metadata corruption issues
# Usage: .\scripts\docker_recover.ps1 [-RemoveVolumes] [-FullCleanup] [-SkipStop] [-TimeoutSecStop <seconds>]
# Can be run from any directory - automatically resolves paths

param(
    [switch]$RemoveVolumes,
    [switch]$FullCleanup,
    [switch]$SkipStop,
    [int]$TimeoutSecStop = 60
)

$ErrorActionPreference = "Continue"

Write-Host "=== EcomCore Docker Recovery ===" -ForegroundColor Cyan
Write-Host "This script will clean up Docker resources for the ecomcore project." -ForegroundColor Yellow
Write-Host ""

# Helper function to run external commands with timeout
function Invoke-ExternalCommandWithTimeout {
    param(
        [string]$File,
        [string[]]$Arguments,
        [int]$TimeoutSec
    )
    
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    
    try {
        $process = Start-Process -FilePath $File -ArgumentList $Arguments -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        
        $completed = $process.WaitForExit($TimeoutSec * 1000)
        
        if (-not $completed) {
            # Timeout - force kill
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            $exitCode = -1
            $status = "TIMEOUT"
        } else {
            $exitCode = $process.ExitCode
            $status = if ($exitCode -eq 0) { "OK" } else { "FAIL" }
        }
        
        $stdout = if (Test-Path $stdoutFile) { Get-Content $stdoutFile -Raw } else { "" }
        $stderr = if (Test-Path $stderrFile) { Get-Content $stderrFile -Raw } else { "" }
        
        return @{
            ExitCode = $exitCode
            StdOut = $stdout
            StdErr = $stderr
            Status = $status
        }
    } finally {
        if (Test-Path $stdoutFile) { Remove-Item $stdoutFile -Force -ErrorAction SilentlyContinue }
        if (Test-Path $stderrFile) { Remove-Item $stderrFile -Force -ErrorAction SilentlyContinue }
    }
}

# Step 0: Docker responsiveness check
Write-Host "=== Step 0: Checking Docker Engine responsiveness ===" -ForegroundColor Cyan
$dockerCheck = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("info") -TimeoutSec 10

if ($dockerCheck.Status -eq "TIMEOUT" -or $dockerCheck.ExitCode -ne 0) {
    Write-Host "Docker Engine is unresponsive. Do: (1) Restart Docker Desktop, (2) wsl --shutdown, (3) restart Docker Desktop, then rerun." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Docker Engine is responsive" -ForegroundColor Green

# Resolve repo root and docker compose directory (works from any directory)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$composeDir = Join-Path $repoRoot "infra" "docker"

if (-not (Test-Path (Join-Path $composeDir "docker-compose.yml"))) {
    Write-Host "Error: docker-compose.yml not found at $composeDir" -ForegroundColor Red
    exit 1
}

# Set COMPOSE_PROJECT_NAME to ensure stable project naming
$env:COMPOSE_PROJECT_NAME = "ecomcore"

# Change to compose directory
Set-Location $composeDir
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Gray
Write-Host "COMPOSE_PROJECT_NAME: $env:COMPOSE_PROJECT_NAME" -ForegroundColor Gray

# Step 1: Stop and remove project containers
if (-not $SkipStop) {
    Write-Host "`n=== Step 1: Stopping and removing ecomcore containers ===" -ForegroundColor Cyan
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting stop phase..." -ForegroundColor Gray
    
    # Strategy A: Try docker compose down with timeout
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Attempting: docker compose down --timeout 20 --remove-orphans" -ForegroundColor Gray
    $resultA = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "down", "--timeout", "20", "--remove-orphans") -TimeoutSec $TimeoutSecStop
    
    if ($resultA.Status -eq "OK" -and $resultA.ExitCode -eq 0) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ✓ Containers stopped and removed via compose down" -ForegroundColor Green
    } elseif ($resultA.Status -eq "TIMEOUT" -or ($resultA.Status -eq "FAIL" -and $resultA.ExitCode -ne 0)) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ⚠ Compose down failed or timed out, trying fallback..." -ForegroundColor Yellow
        
        # Strategy B: Collect containers by label and stop individually
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Collecting project containers by label..." -ForegroundColor Gray
        $containerResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("ps", "-a", "--filter", "label=com.docker.compose.project=ecomcore", "--format", "{{.ID}} {{.Names}}") -TimeoutSec 30
        
        if ($containerResult.Status -eq "OK" -and $containerResult.ExitCode -eq 0) {
            $containerLines = $containerResult.StdOut.Trim() -split "`n" | Where-Object { $_.Trim() -ne "" }
            
            if ($containerLines.Count -eq 0 -or ($containerLines.Count -eq 1 -and $containerLines[0].Trim() -eq "")) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] No project containers found" -ForegroundColor Gray
            } else {
                $containerIds = $containerLines | ForEach-Object { ($_ -split '\s+')[0] }
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Found $($containerIds.Count) container(s), attempting stop..." -ForegroundColor Gray
                
                # Try docker stop with timeout
                $stopResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("stop", "-t", "10") + $containerIds -TimeoutSec $TimeoutSecStop
                
                if ($stopResult.Status -eq "OK" -or $stopResult.Status -eq "TIMEOUT") {
                    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Stop command completed (may have timed out)" -ForegroundColor Gray
                }
                
                # Strategy C: Force remove if stop failed or timed out
                if ($stopResult.Status -eq "TIMEOUT" -or ($stopResult.Status -eq "FAIL" -and $stopResult.ExitCode -ne 0)) {
                    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ⚠ Stop failed/timed out, forcing removal..." -ForegroundColor Yellow
                    $rmResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("rm", "-f") + $containerIds -TimeoutSec $TimeoutSecStop
                    
                    if ($rmResult.Status -eq "OK" -or $rmResult.Status -eq "TIMEOUT") {
                        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Force removal completed" -ForegroundColor Gray
                    }
                } else {
                    # Remove stopped containers
                    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Removing stopped containers..." -ForegroundColor Gray
                    $rmResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("rm") + $containerIds -TimeoutSec $TimeoutSecStop
                }
            }
        } else {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ⚠ Could not collect container list (may be OK if none exist)" -ForegroundColor Yellow
        }
        
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ✓ Stop phase completed (with fallbacks)" -ForegroundColor Green
    } else {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ✓ Containers stopped and removed" -ForegroundColor Green
    }
} else {
    Write-Host "`n=== Step 1: Stopping containers (SKIPPED via -SkipStop) ===" -ForegroundColor Cyan
    Write-Host "Skipping stop phase as requested" -ForegroundColor Yellow
}

# Step 2: Remove project-specific images
Write-Host "`n=== Step 2: Removing ecomcore images ===" -ForegroundColor Cyan
$imagesResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("images", "--filter", "reference=ecomcore-*", "--format", "{{.ID}}") -TimeoutSec 30
if ($imagesResult.Status -eq "OK" -and $imagesResult.ExitCode -eq 0) {
    $images = $imagesResult.StdOut.Trim() -split "`n" | Where-Object { $_.Trim() -ne "" }
    if ($images) {
        $images | ForEach-Object {
            Write-Host "  Removing image $_..." -ForegroundColor Gray
            $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("rmi", $_, "--force") -TimeoutSec 30
        }
        Write-Host "✓ Project images removed" -ForegroundColor Green
    } else {
        Write-Host "✓ No project images to remove" -ForegroundColor Green
    }
} else {
    Write-Host "⚠ Could not list images (may be OK)" -ForegroundColor Yellow
}

# Step 3: Prune builder cache
Write-Host "`n=== Step 3: Pruning Docker builder cache ===" -ForegroundColor Cyan
$pruneBuilderResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("builder", "prune", "-af") -TimeoutSec 120
if ($pruneBuilderResult.Status -eq "OK") {
    Write-Host "✓ Builder cache pruned" -ForegroundColor Green
} elseif ($pruneBuilderResult.Status -eq "TIMEOUT") {
    Write-Host "⚠ Builder prune timed out (continuing...)" -ForegroundColor Yellow
} else {
    Write-Host "⚠ Builder prune failed (continuing...)" -ForegroundColor Yellow
}

# Step 4: Prune unused containers, images, and networks
Write-Host "`n=== Step 4: Pruning unused Docker resources ===" -ForegroundColor Cyan
$pruneSystemResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("system", "prune", "-af") -TimeoutSec 180
if ($pruneSystemResult.Status -eq "OK") {
    Write-Host "✓ Unused resources pruned" -ForegroundColor Green
} elseif ($pruneSystemResult.Status -eq "TIMEOUT") {
    Write-Host "⚠ System prune timed out (continuing...)" -ForegroundColor Yellow
} else {
    Write-Host "⚠ System prune failed (continuing...)" -ForegroundColor Yellow
}

# Step 5: Remove volumes (optional, requires confirmation)
if ($RemoveVolumes) {
    Write-Host "`n=== Step 5: Removing ecomcore volumes ===" -ForegroundColor Cyan
    Write-Host "WARNING: This will delete all database data!" -ForegroundColor Red
    $volumesResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("volume", "ls", "--filter", "name=ecomcore", "--format", "{{.Name}}") -TimeoutSec 30
    if ($volumesResult.Status -eq "OK" -and $volumesResult.ExitCode -eq 0) {
        $volumes = $volumesResult.StdOut.Trim() -split "`n" | Where-Object { $_.Trim() -ne "" }
        if ($volumes) {
            $volumes | ForEach-Object {
                Write-Host "  Removing volume $_..." -ForegroundColor Gray
                $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("volume", "rm", $_) -TimeoutSec 30
            }
            Write-Host "✓ Project volumes removed" -ForegroundColor Green
        } else {
            Write-Host "✓ No project volumes to remove" -ForegroundColor Green
        }
    } else {
        Write-Host "⚠ Could not list volumes (may be OK)" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n=== Step 5: Volumes (skipped) ===" -ForegroundColor Cyan
    Write-Host "Volumes preserved. Use -RemoveVolumes to delete them." -ForegroundColor Yellow
}

# Step 6: Full cleanup (optional, more aggressive)
if ($FullCleanup) {
    Write-Host "`n=== Step 6: Full Docker cleanup ===" -ForegroundColor Cyan
    Write-Host "WARNING: This removes ALL unused containers, networks, images, and build cache!" -ForegroundColor Red
    $fullCleanupResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("system", "prune", "-a", "-f", "--volumes") -TimeoutSec 180
    if ($fullCleanupResult.Status -eq "OK") {
        Write-Host "✓ Full cleanup completed" -ForegroundColor Green
    } elseif ($fullCleanupResult.Status -eq "TIMEOUT") {
        Write-Host "⚠ Full cleanup timed out (continuing...)" -ForegroundColor Yellow
    } else {
        Write-Host "⚠ Full cleanup failed (continuing...)" -ForegroundColor Yellow
    }
}

# Step 7: Check for port 8000 conflicts before starting
Write-Host "`n=== Step 7: Checking for port 8000 conflicts ===" -ForegroundColor Cyan
$port8000Result = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("ps", "-a", "--filter", "publish=8000", "--format", "{{.Names}}") -TimeoutSec 30
$port8000Containers = $null
if ($port8000Result.Status -eq "OK" -and $port8000Result.ExitCode -eq 0) {
    $port8000Containers = $port8000Result.StdOut.Trim() -split "`n" | Where-Object { $_.Trim() -ne "" }
}

$port8000Process = $null

if ($port8000Containers) {
    Write-Host "Found Docker containers using port 8000:" -ForegroundColor Yellow
    $port8000Containers | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    
    # Check if it's an ecomcore container
    $ecomcoreContainer = $port8000Containers | Where-Object { $_ -like "ecomcore-*" }
    if (-not $ecomcoreContainer) {
        Write-Host "`nNon-ecomcore container detected. Options:" -ForegroundColor Yellow
        Write-Host "  A) Stop the conflicting container:" -ForegroundColor Cyan
        $port8000Containers | ForEach-Object {
            Write-Host "     docker stop $_" -ForegroundColor White
            Write-Host "     docker rm $_" -ForegroundColor White
        }
        Write-Host "  B) Use port 8001 instead (override file will be created)" -ForegroundColor Cyan
        $useOverride = Read-Host "Stop container (A) or use port 8001 (B)? [A/B]"
        
        if ($useOverride -eq "B" -or $useOverride -eq "b") {
            Write-Host "Creating docker-compose.override.yml with port 8001..." -ForegroundColor Yellow
            $overrideContent = @"
services:
  api:
    ports:
      - "8001:8000"
"@
            $overrideContent | Out-File -FilePath "docker-compose.override.yml" -Encoding utf8
            Write-Host "✓ Override file created. API will be available on port 8001" -ForegroundColor Green
            Write-Host "  To remove override later: Remove docker-compose.override.yml" -ForegroundColor Gray
        } else {
            Write-Host "Stopping conflicting containers..." -ForegroundColor Yellow
            $port8000Containers | ForEach-Object {
                $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("stop", $_) -TimeoutSec 30
                $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("rm", $_) -TimeoutSec 30
            }
            Write-Host "✓ Conflicting containers stopped" -ForegroundColor Green
        }
    }
}

# Check Windows processes on port 8000
try {
    $netstat = netstat -ano | Select-String ":8000" | Select-String "LISTENING"
    if ($netstat) {
        Write-Host "`nWindows process detected on port 8000:" -ForegroundColor Yellow
        $netstat | ForEach-Object {
            $pid = ($_ -split '\s+')[-1]
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "  PID $pid : $($process.ProcessName)" -ForegroundColor Yellow
            } else {
                Write-Host "  PID $pid : (process not found)" -ForegroundColor Yellow
            }
        }
        Write-Host "`nNote: This script does not kill Windows processes automatically." -ForegroundColor Yellow
        Write-Host "If needed, manually stop the process or use port 8001 override." -ForegroundColor Yellow
    }
} catch {
    # Ignore netstat errors
}

# Step 8: Rebuild and start
Write-Host "`n=== Step 8: Rebuilding and starting services ===" -ForegroundColor Cyan
Write-Host "Running: docker compose up -d --build" -ForegroundColor Gray

$composeUpResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "up", "-d", "--build") -TimeoutSec 300
$composeOutputString = $composeUpResult.StdOut + $composeUpResult.StdErr

if ($composeUpResult.Status -eq "OK" -and $composeUpResult.ExitCode -eq 0) {
    Write-Host "`n✓ Recovery completed successfully!" -ForegroundColor Green
    
    # Wait a moment for containers to start
    Write-Host "Waiting for services to start..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
    
    Write-Host "`n=== Service Status ===" -ForegroundColor Cyan
    $psResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "ps") -TimeoutSec 30
    if ($psResult.Status -eq "OK") {
        Write-Host $psResult.StdOut
    }
    
    # Check if services are running
    $psOutput = if ($psResult.Status -eq "OK") { $psResult.StdOut } else { "" }
    $servicesRunning = $true
    $missingServices = @()
    
    if ($psOutput -notmatch "nginx" -or $psOutput -notmatch "Up") {
        $servicesRunning = $false
        if ($psOutput -notmatch "nginx") { $missingServices += "nginx" }
    }
    if ($psOutput -notmatch "frontend" -or ($psOutput -match "frontend" -and $psOutput -notmatch "Up")) {
        $servicesRunning = $false
        if ($psOutput -notmatch "frontend") { $missingServices += "frontend" }
    }
    if ($psOutput -notmatch "api" -or ($psOutput -match "api" -and $psOutput -notmatch "Up")) {
        $servicesRunning = $false
        if ($psOutput -notmatch "api") { $missingServices += "api" }
    }
    
    if (-not $servicesRunning -or $missingServices.Count -gt 0) {
        Write-Host "`n⚠ Some services are not running. Showing logs..." -ForegroundColor Yellow
        $servicesToCheck = @("api", "frontend", "nginx")
        foreach ($service in $servicesToCheck) {
            Write-Host "`n--- Logs for $service (last 100 lines) ---" -ForegroundColor Cyan
            $logResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "logs", "--tail=100", $service) -TimeoutSec 30
            if ($logResult.Status -eq "OK") {
                Write-Host $logResult.StdOut
            }
        }
    }
    
    # Determine API port
    $apiPort = "8000"
    if (Test-Path "docker-compose.override.yml") {
        $apiPort = "8001"
    }
    
    Write-Host "`n=== Service URLs ===" -ForegroundColor Cyan
    Write-Host "  Frontend:  http://localhost" -ForegroundColor Green
    Write-Host "  API:       http://localhost:$apiPort" -ForegroundColor Green
    Write-Host "  API Docs:  http://localhost:$apiPort/docs" -ForegroundColor Green
    Write-Host "  Adminer:   http://localhost/adminer/ (requires auth)" -ForegroundColor Green
    
    Write-Host "`n=== Verification ===" -ForegroundColor Cyan
    Write-Host "Run verification commands from infra/docker/README.md to confirm all services are working." -ForegroundColor Yellow
} else {
    Write-Host "`n✗ Recovery completed but docker compose up failed" -ForegroundColor Red
    
    # Check if it's a port conflict
    if ($composeOutputString -match "port.*already allocated" -or $composeOutputString -match "Bind.*failed" -or $composeOutputString -match "address already in use") {
        Write-Host "`n⚠ Port conflict detected!" -ForegroundColor Yellow
        
        # Re-check port 8000
        $port8000Result = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("ps", "-a", "--filter", "publish=8000", "--format", "{{.Names}}") -TimeoutSec 30
        $port8000Containers = $null
        if ($port8000Result.Status -eq "OK" -and $port8000Result.ExitCode -eq 0) {
            $port8000Containers = $port8000Result.StdOut.Trim() -split "`n" | Where-Object { $_.Trim() -ne "" }
        }
        
        if ($port8000Containers) {
            Write-Host "`nDocker containers using port 8000:" -ForegroundColor Yellow
            $port8000Containers | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
            
            $ecomcoreContainer = $port8000Containers | Where-Object { $_ -like "ecomcore-*" }
            if (-not $ecomcoreContainer) {
                Write-Host "`nOptions:" -ForegroundColor Cyan
                Write-Host "  A) Stop conflicting containers and retry:" -ForegroundColor White
                $port8000Containers | ForEach-Object {
                    Write-Host "     docker stop $_" -ForegroundColor Gray
                    Write-Host "     docker rm $_" -ForegroundColor Gray
                }
                Write-Host "  B) Use port 8001 instead (creates override file):" -ForegroundColor White
                Write-Host "     Create docker-compose.override.yml with:" -ForegroundColor Gray
                Write-Host "     services:" -ForegroundColor Gray
                Write-Host "       api:" -ForegroundColor Gray
                Write-Host "         ports:" -ForegroundColor Gray
                Write-Host "           - \"8001:8000\"" -ForegroundColor Gray
                
                $choice = Read-Host "`nChoose option (A/B) or press Enter to exit"
                if ($choice -eq "B" -or $choice -eq "b") {
                    $overrideContent = @"
services:
  api:
    ports:
      - "8001:8000"
"@
                    $overrideContent | Out-File -FilePath "docker-compose.override.yml" -Encoding utf8 -NoNewline
                    Write-Host "✓ Override file created. Retrying..." -ForegroundColor Green
                    $retryResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "up", "-d", "--build") -TimeoutSec 300
                    if ($retryResult.Status -eq "OK" -and $retryResult.ExitCode -eq 0) {
                        Write-Host "✓ Services started on port 8001" -ForegroundColor Green
                        Write-Host "  API: http://localhost:8001" -ForegroundColor Green
                        Write-Host "  API Docs: http://localhost:8001/docs" -ForegroundColor Green
                        Write-Host "  To remove override: Delete docker-compose.override.yml" -ForegroundColor Gray
                    }
                } elseif ($choice -eq "A" -or $choice -eq "a") {
                    Write-Host "Stopping conflicting containers..." -ForegroundColor Yellow
                    $port8000Containers | ForEach-Object {
                        $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("stop", $_) -TimeoutSec 30
                        $null = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("rm", $_) -TimeoutSec 30
                    }
                    Write-Host "Retrying docker compose up..." -ForegroundColor Yellow
                    $retryResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "up", "-d", "--build") -TimeoutSec 300
                }
            }
        }
        
        # Check Windows processes
        try {
            $netstat = netstat -ano | Select-String ":8000" | Select-String "LISTENING"
            if ($netstat) {
                Write-Host "`nWindows process on port 8000:" -ForegroundColor Yellow
                $netstat | ForEach-Object {
                    $pid = ($_ -split '\s+')[-1]
                    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    if ($process) {
                        Write-Host "  PID $pid : $($process.ProcessName)" -ForegroundColor Yellow
                    }
                }
                Write-Host "`nNote: This script does not kill Windows processes. Use port 8001 override or stop the process manually." -ForegroundColor Yellow
            }
        } catch {
            # Ignore
        }
    } else {
        Write-Host "`nError output:" -ForegroundColor Yellow
        Write-Host $composeOutputString -ForegroundColor Red
    }
    
    # Always show final status and logs
    Write-Host "`n=== Final Service Status ===" -ForegroundColor Cyan
    $psResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "ps") -TimeoutSec 30
    if ($psResult.Status -eq "OK") {
        Write-Host $psResult.StdOut
    }
    
    $psOutput = if ($psResult.Status -eq "OK") { $psResult.StdOut } else { "" }
    $servicesRunning = $true
    $missingServices = @()
    
    if ($psOutput -notmatch "nginx" -or $psOutput -notmatch "Up") {
        $servicesRunning = $false
        if ($psOutput -notmatch "nginx") { $missingServices += "nginx" }
    }
    if ($psOutput -notmatch "frontend" -or ($psOutput -match "frontend" -and $psOutput -notmatch "Up")) {
        $servicesRunning = $false
        if ($psOutput -notmatch "frontend") { $missingServices += "frontend" }
    }
    if ($psOutput -notmatch "api" -or ($psOutput -match "api" -and $psOutput -notmatch "Up")) {
        $servicesRunning = $false
        if ($psOutput -notmatch "api") { $missingServices += "api" }
    }
    
    if (-not $servicesRunning -or $missingServices.Count -gt 0) {
        Write-Host "`n⚠ Some services are not running. Showing logs..." -ForegroundColor Yellow
        $servicesToCheck = @("api", "frontend", "nginx")
        foreach ($service in $servicesToCheck) {
            Write-Host "`n--- Logs for $service (last 100 lines) ---" -ForegroundColor Cyan
            $logResult = Invoke-ExternalCommandWithTimeout -File "docker" -Arguments @("compose", "logs", "--tail=100", $service) -TimeoutSec 30
            if ($logResult.Status -eq "OK") {
                Write-Host $logResult.StdOut
            }
        }
    }
    
    if ($composeUpResult.Status -ne "OK" -or $composeUpResult.ExitCode -ne 0) {
        Write-Host "`nNext steps:" -ForegroundColor Yellow
        Write-Host "  1. Restart Docker Desktop" -ForegroundColor Cyan
        Write-Host "  2. If using WSL2: wsl --shutdown, then restart Docker Desktop" -ForegroundColor Cyan
        Write-Host "  3. Check disk space on Docker data drive" -ForegroundColor Cyan
        Write-Host "  4. See infra/docker/README.md for advanced recovery steps" -ForegroundColor Cyan
        exit 1
    }
}

Write-Host "`n=== Done! ===" -ForegroundColor Green

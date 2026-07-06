$ErrorActionPreference = "Stop"

Write-Host "[deploy] Stopping service-agent-lab..."
docker compose down
Write-Host "[deploy] Stopped."

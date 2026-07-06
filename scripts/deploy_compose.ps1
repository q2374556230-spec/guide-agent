$ErrorActionPreference = "Stop"

Write-Host "[deploy] Building and starting service-agent-lab with Docker Compose..."
docker compose up -d --build

Write-Host "[deploy] Current services:"
docker compose ps

Write-Host "[deploy] Running smoke tests..."
python scripts\smoke_test.py

Write-Host "[deploy] Done. Open http://localhost:8000"

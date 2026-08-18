# setup.ps1 — Windows equivalent of setup.sh.
# Written to mirror setup.sh step-for-step; authored and reviewed on macOS,
# NOT yet executed on native Windows — treat as best-effort and report issues.
$ErrorActionPreference = "Stop"

Write-Host "== substrate-friction setup (Windows) =="
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv is required: https://docs.astral.sh/uv/  (winget install astral-sh.uv)"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker Desktop is required."
}

uv sync --extra dev
docker compose up -d
Write-Host "waiting for the engine (Bolt 7687)..."
$ok = $false
foreach ($i in 1..60) {
  try {
    uv run python -c "from friction.client import connect; from friction.config import Settings; connect(Settings.from_env(), prefer='bolt').close()" 2>$null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
  } catch {}
  Start-Sleep -Seconds 1
}
if (-not $ok) {
  Write-Warning "engine not reachable — ensure secrets/token exists (32-byte local dev token; see docker-compose.yml). Cache-backed commands (friction gate / verify / compare) work without the engine."
}
uv run friction gate --arm arm_b
Write-Host "setup complete. Try: uv run friction verify"

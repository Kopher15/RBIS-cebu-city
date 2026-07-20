# push-update.ps1
# Run from the repo root: .\push-update.ps1
# Exports road data from PostGIS, then commits and pushes to GitHub.
# Vercel (linked to this repo) auto-deploys production from main.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot   = $PSScriptRoot
$ScriptsDir = Join-Path $RepoRoot 'scripts'

function Write-Step  { param([string]$msg) Write-Host "`n=> $msg" -ForegroundColor Cyan }
function Write-OK    { param([string]$msg) Write-Host "   OK  $msg" -ForegroundColor Green }
function Write-Fail  { param([string]$msg) Write-Host "   ERR $msg" -ForegroundColor Red; exit 1 }

# ── 1. Export from PostGIS ────────────────────────────────────────────────────
Write-Step 'Exporting road data from PostGIS'

if (-not (Test-Path (Join-Path $ScriptsDir '.env'))) {
    Write-Fail "scripts\.env not found. Copy scripts\.env.example to scripts\.env and fill in DB_PASSWORD."
}

Push-Location $ScriptsDir
try {
    node export-roads.js
    if ($LASTEXITCODE -ne 0) { Write-Fail "export-roads.js exited with code $LASTEXITCODE" }
    Write-OK 'GeoJSON export complete'
} finally {
    Pop-Location
}

# ── 2. Commit updated data files ─────────────────────────────────────────────
Write-Step 'Committing updated data files'

Push-Location $RepoRoot
try {
    git add data/roads.geojson data/last-sync.json

    $status = git status --porcelain -- data/roads.geojson data/last-sync.json
    if (-not $status) {
        Write-Host '   No changes detected — nothing to commit.' -ForegroundColor Yellow
        exit 0
    }

    $syncMeta  = Get-Content (Join-Path $RepoRoot 'data\last-sync.json') -Raw | ConvertFrom-Json
    $syncDate  = $syncMeta.last_sync
    $segments  = $syncMeta.segments_updated
    $commitMsg = "chore: sync road data from PostGIS ($syncDate, $segments segments)"

    git commit -m $commitMsg
    if ($LASTEXITCODE -ne 0) { Write-Fail "git commit failed" }
    Write-OK "Committed: $commitMsg"

    # ── 3. Push to GitHub (triggers Vercel production deploy) ─────────────────
    Write-Step 'Pushing to GitHub (origin main)'
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Fail "git push failed" }
    Write-OK 'Pushed to https://github.com/Kopher15/RBIS-cebu-city'

} finally {
    Pop-Location
}

Write-Host "`n== Done. Dashboard data is publishing (GitHub + Vercel). ==" -ForegroundColor Green

<#
.SYNOPSIS
    One-click sync runner for gpkg-postgis-sync.

.DESCRIPTION
    Resolves project root, activates venv if present, sets PYTHONPATH,
    and invokes the sync orchestrator. Verbose by default; pass -Quiet
    for scheduled runs.

.PARAMETER Quiet
    Suppresses console output. File logging is unaffected.

.EXAMPLE
    .\run-sync.ps1
    Runs the sync with verbose console output.

.EXAMPLE
    .\run-sync.ps1 -Quiet
    Runs the sync silently (file logs still written).

.NOTES
    Exit codes:
      0 = success
      1 = orchestrator failure (sync_log row marked failed)
      2 = launcher error (config missing, Python missing, etc.)
#>

[CmdletBinding()]
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

# Resolve project root from this script's location.
# scripts/run-sync.ps1 -> project root is parent of scripts/
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if (-not $Quiet) {
    Write-Host "=== gpkg-postgis-sync runner ===" -ForegroundColor Cyan
    Write-Host "Project root: $ProjectRoot"
}

# Verify config exists
$ConfigPath = Join-Path $ProjectRoot "config\sync.config.json"
if (-not (Test-Path $ConfigPath)) {
    Write-Host "ERROR: Config not found: $ConfigPath" -ForegroundColor Red
    exit 2
}

# Determine Python executable: prefer venv, fall back to system python
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
    if (-not $Quiet) { Write-Host "Python: $Python (venv)" }
} else {
    $Python = "python"
    if (-not $Quiet) { Write-Host "Python: system python (no .venv detected)" }
}

# Set PYTHONPATH so the orchestrator's imports resolve
$SrcPath = Join-Path $ProjectRoot "src"
$env:PYTHONPATH = $SrcPath

# Locate entry script
$EntryScript = Join-Path $ScriptDir "_run_sync_entry.py"
if (-not (Test-Path $EntryScript)) {
    Write-Host "ERROR: Entry script missing: $EntryScript" -ForegroundColor Red
    exit 2
}

# Run
if (-not $Quiet) {
    Write-Host "Invoking orchestrator..." -ForegroundColor Cyan
    Write-Host ""
}

if ($Quiet) {
    & $Python $EntryScript --quiet
} else {
    & $Python $EntryScript
}
$ExitCode = $LASTEXITCODE

if (-not $Quiet) {
    Write-Host ""
    if ($ExitCode -eq 0) {
        Write-Host "=== Sync completed successfully ===" -ForegroundColor Green
    } else {
        Write-Host "=== Sync FAILED (exit $ExitCode) ===" -ForegroundColor Red
    }
}

exit $ExitCode

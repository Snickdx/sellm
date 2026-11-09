# Scenario package sync for sellm.
# sellm/scenarios is the canonical authoring home (not seproject).
#
# Default: inventory sellm packages.
# Optional: push sellm → sibling seproject mirror (legacy consumers only).
#
# Usage:
#   .\scripts\sync-scenarios.ps1
#   .\scripts\sync-scenarios.ps1 -PushToSeproject
param(
    [switch]$PushToSeproject
)

$ErrorActionPreference = "Stop"

$SellmRoot = Split-Path -Parent $PSScriptRoot
$SrcRoot = Join-Path $SellmRoot "scenarios"
$SeprojectRoot = Join-Path (Split-Path -Parent $SellmRoot) "seproject\scenarios"

$slugs = @(
    "career-advising",
    "job-board",
    "library",
    "student-accommodation",
    "ta-allocations",
    "thesis-tracker",
    "uwi-connect"
)

if (-not (Test-Path $SrcRoot)) {
    Write-Error "Missing sellm scenarios at $SrcRoot"
}

Write-Host "Canonical scenarios: $SrcRoot"
foreach ($slug in $slugs) {
    $src = Join-Path $SrcRoot $slug
    if (Test-Path $src) {
        Write-Host "  ok $slug"
    }
    else {
        Write-Host "  missing $slug"
    }
}

if (-not $PushToSeproject) {
    Write-Host "Done. Author in sellm/scenarios; reindex via POST /api/admin/scenarios/reindex or scripts/reindex_scenarios.py"
    Write-Host "To mirror outward: .\scripts\sync-scenarios.ps1 -PushToSeproject"
    exit 0
}

if (-not (Test-Path (Split-Path -Parent $SeprojectRoot))) {
    Write-Error "Missing sibling seproject repo for push at $(Split-Path -Parent $SeprojectRoot)"
}

New-Item -ItemType Directory -Force -Path $SeprojectRoot | Out-Null
foreach ($slug in $slugs) {
    $src = Join-Path $SrcRoot $slug
    $dst = Join-Path $SeprojectRoot $slug
    if (-not (Test-Path $src)) {
        Write-Warning "Skip missing sellm package: $slug"
        continue
    }
    if (Test-Path $dst) {
        Remove-Item $dst -Recurse -Force
    }
    Copy-Item $src $dst -Recurse -Force
    Write-Host "pushed $slug -> seproject"
}

Write-Host "Done. sellm remains source of truth; seproject is a mirror only."

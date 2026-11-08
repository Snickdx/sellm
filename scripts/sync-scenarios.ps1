# Sync approved scenario packages from seproject plat into sellm/scenarios.
# Run from sellm root (or any cwd); paths are relative to this script's parent.
$ErrorActionPreference = "Stop"
$SellmRoot = Split-Path -Parent $PSScriptRoot
$SrcRoot = Join-Path (Split-Path -Parent $SellmRoot) "seproject\scenarios"
$DstRoot = Join-Path $SellmRoot "scenarios"

if (-not (Test-Path $SrcRoot)) {
    Write-Error "Missing seproject scenarios at $SrcRoot"
}

$slugs = @(
    "career-advising",
    "job-board",
    "library",
    "student-accommodation",
    "ta-allocations",
    "thesis-tracker",
    "uwi-connect"
)

New-Item -ItemType Directory -Force -Path $DstRoot | Out-Null
foreach ($slug in $slugs) {
    $src = Join-Path $SrcRoot $slug
    $dst = Join-Path $DstRoot $slug
    if (-not (Test-Path $src)) {
        Write-Error "Missing scenario package: $src"
    }
    if (Test-Path $dst) {
        Remove-Item $dst -Recurse -Force
    }
    Copy-Item $src $dst -Recurse -Force
    Write-Host "synced $slug"
}

Write-Host "Done. Scenarios are under sellm/scenarios (SCENARIOS_ROOT)."

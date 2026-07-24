<#
.SYNOPSIS
    Garbage collection: remove regenerable build artifacts and caches.
    Does NOT touch source, docs, or git-tracked files.
.EXAMPLE
    pwsh scripts/gc.ps1
    pwsh scripts/gc.ps1 -DryRun
#>
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Dirs = @(
    'ai/build', 'ai/install', 'ai/log'
)
$Patterns = @(
    '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', '*.egg-info'
)

function Remove-Target([string]$Path) {
    if ($DryRun) {
        Write-Host "[dry-run] would remove: $Path"
    } else {
        Remove-Item -Recurse -Force $Path
        Write-Host "removed: $Path"
    }
}

Write-Host "== Garbage collection (root: $Root) =="

foreach ($d in $Dirs) {
    if (Test-Path $d) { Remove-Target $d }
}

foreach ($p in $Patterns) {
    Get-ChildItem -Path . -Recurse -Force -Filter $p -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\\.git\\' } |
        ForEach-Object { Remove-Target $_.FullName }
}

if ($DryRun) {
    Write-Host "== dry-run complete (nothing deleted) =="
} else {
    Write-Host "== done =="
}

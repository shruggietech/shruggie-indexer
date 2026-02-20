<#
.SYNOPSIS
    Builds shruggie-indexer standalone executables via PyInstaller.

.DESCRIPTION
    This script invokes PyInstaller against both the CLI and GUI spec files to
    produce standalone executables in the dist/ directory. Each target is built
    with a separate workpath to avoid collisions.

    The script checks for UPX availability and logs the result. If UPX is not
    installed, PyInstaller silently skips compression — the build succeeds with
    larger executables.

    This script MUST be invoked from the repository root directory.
    The virtual environment MUST be active and PyInstaller MUST be installed.

.PARAMETER Target
    Build target to produce. Valid values: cli, gui, all.
    When set to 'all' or omitted, builds both CLI and GUI executables.

.PARAMETER Clean
    If specified, removes existing dist/ and build/ directories before building.

.PARAMETER Help
    Displays this help text and exits.

.EXAMPLE
    .\scripts\build.ps1
    Builds both CLI and GUI executables.

.EXAMPLE
    .\scripts\build.ps1 -Target cli
    Builds only the CLI executable.

.EXAMPLE
    .\scripts\build.ps1 -Clean
    Cleans build artifacts and builds both executables.

.NOTES
    Project:  shruggie-indexer
    Requires: Python >= 3.12, PyInstaller, virtual environment active
    License:  Apache 2.0
#>

[CmdletBinding()]
param(
    [Parameter(HelpMessage = "Build target: cli, gui, or all (default: all).")]
    [ValidateSet("cli", "gui", "all")]
    [string]$Target = "all",

    [Parameter(HelpMessage = "Remove existing dist/ and build/ before building.")]
    [switch]$Clean,

    [Parameter(HelpMessage = "Display help text and exit.")]
    [Alias("h")]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

$CliSpecFile = "shruggie-indexer-cli.spec"
$GuiSpecFile = "shruggie-indexer-gui.spec"
$DistDir = "dist"
$BuildDir = "build"

# -------------------------------------------------------------------
# Help
# -------------------------------------------------------------------

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    return
}

# -------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------

function Test-Prerequisites {
    <#
    .SYNOPSIS
        Validates that the build environment is correctly configured.
    #>

    # Check that we're in the repository root
    if (-not (Test-Path "pyproject.toml")) {
        Write-Error "This script must be invoked from the repository root (pyproject.toml not found)."
    }

    # Check that the virtual environment is active
    if (-not $env:VIRTUAL_ENV) {
        Write-Error "Virtual environment is not active. Run: .\.venv\Scripts\Activate.ps1"
    }

    # Check that PyInstaller is available
    $pyinstaller = Get-Command "pyinstaller" -ErrorAction SilentlyContinue
    if (-not $pyinstaller) {
        Write-Error "PyInstaller is not installed. Run: pip install pyinstaller"
    }
    Write-Host "[build] PyInstaller found: $($pyinstaller.Source)" -ForegroundColor Cyan

    # Check that spec files exist
    if (-not (Test-Path $CliSpecFile)) {
        Write-Error "CLI spec file not found: $CliSpecFile"
    }
    if (-not (Test-Path $GuiSpecFile)) {
        Write-Error "GUI spec file not found: $GuiSpecFile"
    }
}

function Test-UPXAvailability {
    <#
    .SYNOPSIS
        Checks whether UPX is available for executable compression.
    #>
    $upx = Get-Command "upx" -ErrorAction SilentlyContinue
    if ($upx) {
        $upxVersion = & upx --version 2>&1 | Select-Object -First 1
        Write-Host "[build] UPX found: $upxVersion" -ForegroundColor Green
        Write-Host "[build] Executables will be UPX-compressed." -ForegroundColor Green
    }
    else {
        Write-Host "[build] UPX not found — executables will not be compressed." -ForegroundColor Yellow
        Write-Host "[build] Install UPX for 30-50% smaller executables: https://upx.github.io/" -ForegroundColor Yellow
    }
}

function Invoke-PyInstallerBuild {
    <#
    .SYNOPSIS
        Runs PyInstaller against a spec file.
    #>
    param(
        [string]$SpecFile,
        [string]$Label,
        [string]$WorkPath
    )

    Write-Host ""
    Write-Host "[build] Building $Label executable..." -ForegroundColor Cyan
    & pyinstaller $SpecFile --distpath $DistDir --workpath $WorkPath --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller build failed for $Label ($SpecFile)."
    }
    Write-Host "[build] $Label build completed." -ForegroundColor Green
}

function Test-BuildOutput {
    <#
    .SYNOPSIS
        Verifies that the expected executables exist in dist/.
    #>
    param(
        [string]$Label,
        [string]$ExecutableName
    )

    # On Windows, append .exe
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $ExecutableName = "$ExecutableName.exe"
    }

    $outputPath = Join-Path $DistDir $ExecutableName
    if (Test-Path $outputPath) {
        $fileInfo = Get-Item $outputPath
        $sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
        Write-Host "[build] $Label executable verified: $outputPath ($sizeMB MB)" -ForegroundColor Green
    }
    else {
        Write-Error "$Label executable not found at expected path: $outputPath"
    }
}

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host "  shruggie-indexer  —  build.ps1       " -ForegroundColor White
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host ""

# 1. Validate prerequisites
Test-Prerequisites

# 2. Check UPX availability
Test-UPXAvailability

# 3. Clean if requested
if ($Clean) {
    Write-Host "[build] Cleaning previous build artifacts..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
    Write-Host "[build] Clean complete." -ForegroundColor Green
}

# 4. Build targets
$buildCli = ($Target -eq "all") -or ($Target -eq "cli")
$buildGui = ($Target -eq "all") -or ($Target -eq "gui")

if ($buildCli) {
    Invoke-PyInstallerBuild -SpecFile $CliSpecFile -Label "CLI" -WorkPath (Join-Path $BuildDir "cli")
    Test-BuildOutput -Label "CLI" -ExecutableName "shruggie-indexer"
}

if ($buildGui) {
    Invoke-PyInstallerBuild -SpecFile $GuiSpecFile -Label "GUI" -WorkPath (Join-Path $BuildDir "gui")
    Test-BuildOutput -Label "GUI" -ExecutableName "shruggie-indexer-gui"
}

# 5. Summary
Write-Host ""
Write-Host "[build] Build complete. Artifacts in $DistDir/:" -ForegroundColor Green
Get-ChildItem -Path $DistDir -File | ForEach-Object {
    $sizeMB = [math]::Round($_.Length / 1MB, 2)
    Write-Host "    $($_.Name)  ($sizeMB MB)" -ForegroundColor White
}
Write-Host ""

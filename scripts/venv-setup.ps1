<#
.SYNOPSIS
    Creates and configures a Python virtual environment for shruggie-indexer development.

.DESCRIPTION
    This script creates a Python virtual environment in the repository root (.venv/),
    installs the shruggie-indexer package in editable mode with all development and GUI
    dependencies, and verifies that the installation succeeded.

    The script is idempotent — it is safe to re-run at any time. If the virtual
    environment already exists, it will be reused (not recreated) unless the -Force
    switch is specified.

    This script MUST be invoked from the repository root directory.

.PARAMETER PythonPath
    Path to a specific Python interpreter. If not specified, the script searches
    for 'python3' then 'python' on PATH and verifies the version is >= 3.12.

.PARAMETER Force
    If specified, removes any existing .venv/ directory and creates a fresh
    virtual environment from scratch.

.PARAMETER Extras
    Comma-separated list of pip extras to install. Defaults to 'dev,gui'.
    Use 'dev' for headless environments where GUI dependencies are not needed.

.PARAMETER Help
    Displays this help text and exits.

.EXAMPLE
    .\scripts\venv-setup.ps1
    Creates or reuses .venv/ and installs the package with [dev,gui] extras.

.EXAMPLE
    .\scripts\venv-setup.ps1 -Force
    Removes any existing .venv/ and creates a fresh environment.

.EXAMPLE
    .\scripts\venv-setup.ps1 -Extras "dev"
    Installs with only the [dev] extra (no GUI dependencies).

.EXAMPLE
    .\scripts\venv-setup.ps1 -PythonPath "C:\Python312\python.exe"
    Uses a specific Python interpreter to create the virtual environment.

.NOTES
    Project:  shruggie-indexer
    Requires: Python >= 3.12
    License:  Apache 2.0
#>

[CmdletBinding()]
param(
    [Parameter(HelpMessage = "Path to a specific Python interpreter.")]
    [string]$PythonPath,

    [Parameter(HelpMessage = "Remove existing .venv/ and recreate from scratch.")]
    [switch]$Force,

    [Parameter(HelpMessage = "Comma-separated pip extras to install (default: 'dev,gui').")]
    [string]$Extras = "dev,gui",

    [Parameter(HelpMessage = "Display help text and exit.")]
    [Alias("h")]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

$MinPythonMajor = 3
$MinPythonMinor = 12
$VenvDir = ".venv"

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

function Find-Python {
    <#
    .SYNOPSIS
        Locates a suitable Python interpreter.
    #>
    param([string]$PythonPath)

    if ($PythonPath) {
        if (-not (Test-Path $PythonPath)) {
            Write-Error "Specified Python path does not exist: $PythonPath"
        }
        return $PythonPath
    }

    foreach ($candidate in @("python3", "python")) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) {
            return $found.Source
        }
    }

    Write-Error "No Python interpreter found on PATH. Install Python >= $MinPythonMajor.$MinPythonMinor and ensure it is on PATH."
}

function Test-PythonVersion {
    <#
    .SYNOPSIS
        Validates that the interpreter meets the minimum version requirement.
    #>
    param([string]$Interpreter)

    $versionOutput = & $Interpreter --version 2>&1
    if ($versionOutput -match "(\d+)\.(\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        $patch = $Matches[3]

        if ($major -lt $MinPythonMajor -or ($major -eq $MinPythonMajor -and $minor -lt $MinPythonMinor)) {
            Write-Error "Python $major.$minor.$patch found, but >= $MinPythonMajor.$MinPythonMinor is required."
        }

        Write-Verbose "Using Python $major.$minor.$patch at: $Interpreter"
        return "$major.$minor.$patch"
    }
    else {
        Write-Error "Could not determine Python version from: $versionOutput"
    }
}

function Initialize-VirtualEnvironment {
    <#
    .SYNOPSIS
        Creates or reuses a virtual environment.
    #>
    param(
        [string]$Interpreter,
        [switch]$Force
    )

    if ($Force -and (Test-Path $VenvDir)) {
        Write-Host "[venv-setup] Removing existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }

    if (Test-Path $VenvDir) {
        Write-Host "[venv-setup] Virtual environment already exists at ./$VenvDir — reusing." -ForegroundColor Cyan
    }
    else {
        Write-Host "[venv-setup] Creating virtual environment at ./$VenvDir ..." -ForegroundColor Cyan
        & $Interpreter -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create virtual environment."
        }
    }
}

function Get-VenvPython {
    <#
    .SYNOPSIS
        Returns the path to the Python interpreter inside the virtual environment.
    #>
    $candidate = Join-Path $VenvDir "Scripts" "python.exe"
    if (Test-Path $candidate) {
        return $candidate
    }
    # Fallback for non-Windows layouts (shouldn't happen on Windows, but be safe)
    $candidate = Join-Path $VenvDir "bin" "python"
    if (Test-Path $candidate) {
        return $candidate
    }
    Write-Error "Could not locate Python interpreter inside $VenvDir."
}

function Install-ProjectPackage {
    <#
    .SYNOPSIS
        Installs the package in editable mode with the specified extras.
    #>
    param(
        [string]$VenvPython,
        [string]$Extras
    )

    Write-Host "[venv-setup] Upgrading pip..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pip upgrade failed (non-fatal). Continuing with current pip version."
    }

    $installTarget = ".[$Extras]"
    Write-Host "[venv-setup] Installing shruggie-indexer in editable mode with [$Extras] extras..." -ForegroundColor Cyan
    & $VenvPython -m pip install -e $installTarget
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Package installation failed."
    }
}

function Test-Installation {
    <#
    .SYNOPSIS
        Verifies that the package installed correctly.
    #>
    param([string]$VenvPython)

    Write-Host "[venv-setup] Verifying installation..." -ForegroundColor Cyan

    # Verify the package is importable
    & $VenvPython -c "from shruggie_indexer._version import __version__; print(f'shruggie-indexer v{__version__}')"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Verification failed: could not import shruggie_indexer."
    }

    Write-Host "[venv-setup] Installation verified successfully." -ForegroundColor Green
}

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host "  shruggie-indexer  —  venv-setup.ps1  " -ForegroundColor White
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host ""

# 1. Find and validate the Python interpreter
$python = Find-Python -PythonPath $PythonPath
Test-PythonVersion -Interpreter $python | Out-Null

# 2. Create or reuse the virtual environment
Initialize-VirtualEnvironment -Interpreter $python -Force:$Force

# 3. Locate the venv Python
$venvPython = Get-VenvPython

# 4. Install the package
Install-ProjectPackage -VenvPython $venvPython -Extras $Extras

# 5. Verify
Test-Installation -VenvPython $venvPython

Write-Host ""
Write-Host "[venv-setup] Done. Activate the environment with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host ""

<#
.SYNOPSIS
    Runs the shruggie-indexer test suite via pytest.

.DESCRIPTION
    This script activates the project virtual environment and runs pytest with
    configurable scope, markers, and coverage options. It supports both named
    test categories (unit, integration, conformance, platform) and automatic
    discovery of available test directories.

    When invoked without arguments, the script runs the full test suite. When
    a category name is provided, only that category's tests are executed.

    This script MUST be invoked from the repository root directory.

.PARAMETER Category
    Test category to run. Valid values: unit, integration, conformance, platform, all.
    When set to 'all' or omitted, runs the full test suite.
    Multiple categories can be specified as a comma-separated string (e.g., "unit,conformance").

.PARAMETER Discover
    Lists all available test categories and their test file counts, then exits.
    Useful for verifying which test directories exist and contain tests.

.PARAMETER Coverage
    Enables pytest-cov coverage reporting with term-missing output.

.PARAMETER Marker
    A pytest marker expression to filter tests (e.g., "not slow", "not requires_exiftool").
    Passed directly to pytest's -m flag.

.PARAMETER ExtraArgs
    Additional arguments passed through to pytest verbatim.
    Specify as an array of strings.

.PARAMETER VerboseTests
    Enables pytest verbose output (-v).

.PARAMETER Help
    Displays this help text and exits.

.EXAMPLE
    .\scripts\test.ps1
    Runs the full test suite.

.EXAMPLE
    .\scripts\test.ps1 -Category unit
    Runs only unit tests.

.EXAMPLE
    .\scripts\test.ps1 -Category "unit,conformance"
    Runs unit and conformance tests.

.EXAMPLE
    .\scripts\test.ps1 -Discover
    Lists available test categories and their test counts.

.EXAMPLE
    .\scripts\test.ps1 -Category integration -Marker "not requires_exiftool"
    Runs integration tests excluding those that require exiftool.

.EXAMPLE
    .\scripts\test.ps1 -Coverage
    Runs all tests with coverage reporting.

.EXAMPLE
    .\scripts\test.ps1 -Category unit -VerboseTests -ExtraArgs @("--tb=short", "-x")
    Runs unit tests verbosely, with short tracebacks and fail-fast.

.NOTES
    Project:  shruggie-indexer
    Requires: Virtual environment created by venv-setup.ps1
    License:  Apache 2.0
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, HelpMessage = "Test category: unit, integration, conformance, platform, all")]
    [string]$Category = "all",

    [Parameter(HelpMessage = "List available test categories and exit.")]
    [switch]$Discover,

    [Parameter(HelpMessage = "Enable coverage reporting.")]
    [switch]$Coverage,

    [Parameter(HelpMessage = "Pytest marker expression for -m flag.")]
    [string]$Marker,

    [Parameter(HelpMessage = "Additional arguments passed to pytest.")]
    [string[]]$ExtraArgs,

    [Parameter(HelpMessage = "Enable verbose pytest output.")]
    [Alias("v")]
    [switch]$VerboseTests,

    [Parameter(HelpMessage = "Display help text and exit.")]
    [Alias("h")]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

$VenvDir = ".venv"
$TestsDir = "tests"
$ValidCategories = @("unit", "integration", "conformance", "platform")

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

function Get-VenvPython {
    <#
    .SYNOPSIS
        Returns the path to the Python interpreter inside the virtual environment.
    #>
    $candidate = Join-Path $VenvDir "Scripts" "python.exe"
    if (Test-Path $candidate) {
        return $candidate
    }
    $candidate = Join-Path $VenvDir "bin" "python"
    if (Test-Path $candidate) {
        return $candidate
    }
    Write-Error @"
Virtual environment not found at ./$VenvDir.
Run '.\scripts\venv-setup.ps1' first to create the environment.
"@
}

function Get-AvailableCategory {
    <#
    .SYNOPSIS
        Discovers test categories by scanning the tests/ directory for subdirectories
        that contain test_*.py files.
    #>
    $categories = [System.Collections.Generic.List[PSCustomObject]]::new()

    if (-not (Test-Path $TestsDir)) {
        return $categories
    }

    foreach ($dir in (Get-ChildItem -Path $TestsDir -Directory)) {
        $testFiles = Get-ChildItem -Path $dir.FullName -Filter "test_*.py" -File -ErrorAction SilentlyContinue
        $count = ($testFiles | Measure-Object).Count
        if ($count -gt 0) {
            $categories.Add([PSCustomObject]@{
                Name      = $dir.Name
                Path      = $dir.FullName
                FileCount = $count
            })
        }
    }

    return $categories
}

function Show-Discovery {
    <#
    .SYNOPSIS
        Displays available test categories with file counts.
    #>
    $available = Get-AvailableCategory

    Write-Host ""
    Write-Host "Available test categories:" -ForegroundColor Cyan
    Write-Host ""

    if ($available.Count -eq 0) {
        Write-Host "  (none found — no test_*.py files in $TestsDir/*/)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Expected category directories:" -ForegroundColor DarkGray
        foreach ($cat in $ValidCategories) {
            Write-Host "    tests/$cat/" -ForegroundColor DarkGray
        }
        Write-Host ""
        return
    }

    $maxNameLen = ($available | ForEach-Object { $_.Name.Length } | Measure-Object -Maximum).Maximum
    foreach ($cat in $available) {
        $paddedName = $cat.Name.PadRight($maxNameLen)
        $fileLabel = if ($cat.FileCount -eq 1) { "file" } else { "files" }
        Write-Host "  $paddedName  $($cat.FileCount) test $fileLabel" -ForegroundColor White
    }

    Write-Host ""

    # Show registered categories with no tests yet
    $missingCategories = $ValidCategories | Where-Object { $_ -notin ($available | ForEach-Object { $_.Name }) }
    if ($missingCategories.Count -gt 0) {
        Write-Host "  Categories with no tests yet:" -ForegroundColor DarkGray
        foreach ($cat in $missingCategories) {
            Write-Host "    $cat" -ForegroundColor DarkGray
        }
        Write-Host ""
    }
}

function Resolve-Category {
    <#
    .SYNOPSIS
        Resolves the Category parameter into a list of test directory paths.
    #>
    param([string]$CategoryInput)

    if ($CategoryInput -eq "all") {
        return @($TestsDir)
    }

    $requested = $CategoryInput -split "," | ForEach-Object { $_.Trim().ToLower() }
    $paths = [System.Collections.Generic.List[string]]::new()

    foreach ($cat in $requested) {
        if ($cat -notin $ValidCategories) {
            Write-Error "Unknown test category: '$cat'. Valid categories: $($ValidCategories -join ', '), all"
        }

        $catPath = Join-Path $TestsDir $cat
        if (-not (Test-Path $catPath)) {
            Write-Warning "Test category directory does not exist: $catPath (skipping)"
            continue
        }

        $paths.Add($catPath)
    }

    if ($paths.Count -eq 0) {
        Write-Error "No valid test directories found for category: '$CategoryInput'"
    }

    return $paths.ToArray()
}

function Build-PytestArgList {
    <#
    .SYNOPSIS
        Constructs the pytest argument list from script parameters.
    #>
    param(
        [string[]]$TestPaths,
        [switch]$VerboseTests,
        [string[]]$ExtraArgs
    )

    $argList = [System.Collections.Generic.List[string]]::new()

    # Test paths
    foreach ($p in $TestPaths) {
        $argList.Add($p)
    }

    # Verbose
    if ($VerboseTests) {
        $argList.Add("-v")
    }

    # Coverage
    if ($Coverage) {
        $argList.Add("--cov=shruggie_indexer")
        $argList.Add("--cov-report=term-missing")
    }

    # Marker expression
    if ($Marker) {
        $argList.Add("-m")
        $argList.Add($Marker)
    }

    # Pass-through arguments
    if ($ExtraArgs) {
        foreach ($a in $ExtraArgs) {
            $argList.Add($a)
        }
    }

    return $argList.ToArray()
}

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host "  shruggie-indexer  —  test.ps1         " -ForegroundColor White
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host ""

# Handle discovery mode
if ($Discover) {
    Show-Discovery
    return
}

# 1. Locate virtual environment Python
$venvPython = Get-VenvPython

# 2. Resolve test category to directories
$testPaths = Resolve-Category -CategoryInput $Category

# 3. Build pytest arguments
$pytestArgs = Build-PytestArgList -TestPaths $testPaths -VerboseTests:$VerboseTests -ExtraArgs $ExtraArgs

# 4. Display what we're running
$categoryLabel = if ($Category -eq "all") { "all categories" } else { $Category }
Write-Host "[test] Running tests: $categoryLabel" -ForegroundColor Cyan

if ($Marker) {
    Write-Host "[test] Marker filter: $Marker" -ForegroundColor Cyan
}

if ($Coverage) {
    Write-Host "[test] Coverage reporting: enabled" -ForegroundColor Cyan
}

Write-Host "[test] Command: $venvPython -m pytest $($pytestArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""

# 5. Execute pytest
& $venvPython -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

# 6. Report result
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "[test] All tests passed." -ForegroundColor Green
}
elseif ($exitCode -eq 5) {
    Write-Host "[test] No tests were collected." -ForegroundColor Yellow
}
else {
    Write-Host "[test] Tests failed with exit code: $exitCode" -ForegroundColor Red
}

exit $exitCode

param(
    [ValidateSet('src', 'tests', 'all')]
    [string]$Target = 'src'
)

$venvPython = '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    $venvPython = '.venv/bin/python'
}

if (-not (Test-Path $venvPython)) {
    Write-Error 'Virtual environment not found. Run scripts/venv-setup first.'
}

function Invoke-Ruff([string]$PathTarget) {
    Write-Host "[lint] ruff check $PathTarget/" -ForegroundColor Cyan
    & $venvPython -m ruff check "$PathTarget/"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if ($Target -eq 'all') {
    Invoke-Ruff 'src'
    Invoke-Ruff 'tests'
}
else {
    Invoke-Ruff $Target
}

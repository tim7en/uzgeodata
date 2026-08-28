$ErrorActionPreference = 'Stop'

$qgisPython = Get-ChildItem -Path 'C:\Program Files\QGIS*\bin\python-qgis*.bat' -File -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if (-not $qgisPython) {
    throw 'QGIS Python was not found under C:\Program Files\QGIS*. Install QGIS or run build_hydrography_reference.py with a Python environment containing osgeo.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
& $qgisPython.FullName (Join-Path $PSScriptRoot 'build_hydrography_reference.py') --root $projectRoot @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

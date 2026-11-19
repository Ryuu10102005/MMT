$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$omnetRoot = Split-Path (Split-Path $projectRoot -Parent) -Parent
$env:PATH = "$omnetRoot/bin;$omnetRoot/tools/win32.x86_64/clang64/bin;$omnetRoot/tools/win32.x86_64/usr/bin;" + $env:PATH
$env:OMNETPP_ROOT = $omnetRoot
Push-Location $projectRoot
try {
    & "$omnetRoot/tools/win32.x86_64/usr/bin/make.exe" MODE=release -j4
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    & python "$PSScriptRoot/run.py" record-build
    if ($LASTEXITCODE -ne 0) { throw 'Recording build provenance failed' }
} finally { Pop-Location }

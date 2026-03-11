param(
    [string]$PythonExe = ".\venv\Scripts\python.exe",
    [string]$InnoSetupCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $projectRoot "AdminAssistant.spec"
$installerScript = Join-Path $projectRoot "installer\AdminAssistant.iss"
$distDir = Join-Path $projectRoot "dist\AdminAssistant"
$srcDir = Join-Path $projectRoot "src"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (-not (Test-Path $InnoSetupCompiler)) {
    throw "Inno Setup compiler not found: $InnoSetupCompiler"
}

$versionJson = @'
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from admin_assistant.version import APP_AUTHOR, APP_NAME, __version__
print(json.dumps({"app_name": APP_NAME, "version": __version__, "publisher": APP_AUTHOR}))
'@

$versionInfo = $versionJson | & $PythonExe - | ConvertFrom-Json

Write-Host "Building PyInstaller package for $($versionInfo.app_name) v$($versionInfo.version)..."
Push-Location $projectRoot
try {
    $previousPythonPath = $env:PYTHONPATH
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $env:PYTHONPATH = $srcDir
    }
    else {
        $env:PYTHONPATH = "$srcDir;$previousPythonPath"
    }

    & $PythonExe -m PyInstaller --clean -y $specPath
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}

if (-not (Test-Path (Join-Path $distDir "AdminAssistant.exe"))) {
    throw "Packaged executable not found in $distDir"
}

Write-Host "Compiling Inno Setup installer..."
& $InnoSetupCompiler `
    "/DMyAppVersion=$($versionInfo.version)" `
    "/DMyAppPublisher=$($versionInfo.publisher)" `
    "/DMyAppName=$($versionInfo.app_name)" `
    "/DDistDir=$distDir" `
    $installerScript

Write-Host "Installer build complete."

param(
    [string]$PythonExe = ".\venv\Scripts\python.exe",
    [string]$InnoSetupCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

function Resolve-ExecutablePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Tool,
        [Parameter(Mandatory = $true)]
        [string]$DisplayName
    )

    if (Test-Path $Tool) {
        return (Resolve-Path $Tool).Path
    }

    $command = Get-Command $Tool -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }

    throw "$DisplayName not found: $Tool"
}

$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}
$scriptDir = Split-Path -Parent $scriptPath
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$specPath = Join-Path $projectRoot "AdminAssistant.spec"
$installerScript = Join-Path $projectRoot "installer\AdminAssistant.iss"
$distDir = Join-Path $projectRoot "dist\AdminAssistant"
$srcDir = Join-Path $projectRoot "src"

if (-not (Test-Path $specPath)) {
    throw "PyInstaller spec file not found: $specPath"
}

if (-not (Test-Path $installerScript)) {
    throw "Installer script not found: $installerScript"
}

if (-not (Test-Path $srcDir)) {
    throw "Source directory not found: $srcDir"
}

$specPath = (Resolve-Path $specPath).Path
$installerScript = (Resolve-Path $installerScript).Path
$srcDir = (Resolve-Path $srcDir).Path
$resolvedPythonExe = Resolve-ExecutablePath -Tool $PythonExe -DisplayName "Python executable"
$resolvedInnoSetupCompiler = Resolve-ExecutablePath -Tool $InnoSetupCompiler -DisplayName "Inno Setup compiler"

$versionJson = @'
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from admin_assistant.version import APP_AUTHOR, APP_NAME, __version__
print(json.dumps({"app_name": APP_NAME, "version": __version__, "publisher": APP_AUTHOR}))
'@

$versionInfo = $versionJson | & $resolvedPythonExe - | ConvertFrom-Json

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

    & $resolvedPythonExe -m PyInstaller --clean -y $specPath
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}

if (-not (Test-Path (Join-Path $distDir "AdminAssistant.exe"))) {
    throw "Packaged executable not found in $distDir"
}

$distDir = (Resolve-Path $distDir).Path

Write-Host "Compiling Inno Setup installer..."
& $resolvedInnoSetupCompiler `
    "/DMyAppVersion=$($versionInfo.version)" `
    "/DMyAppPublisher=$($versionInfo.publisher)" `
    "/DMyAppName=$($versionInfo.app_name)" `
    "/DDistDir=$distDir" `
    $installerScript

$installerPath = Join-Path $projectRoot ("installer\AdminAssistant_v{0}_Setup.exe" -f $versionInfo.version)
if (-not (Test-Path $installerPath)) {
    throw "Installer output not found: $installerPath"
}

$installerPath = (Resolve-Path $installerPath).Path
Write-Host "Installer build complete: $installerPath"
Write-Output $installerPath

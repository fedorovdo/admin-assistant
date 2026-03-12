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

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    $quotedArguments = ($ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_ -replace '"', '\"') + '"'
        }
        else {
            $_
        }
    }) -join ' '

    try {
        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $quotedArguments `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -NoNewWindow `
            -Wait `
            -PassThru

        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (-not (Test-Path $path)) {
                continue
            }

            Get-Content -LiteralPath $path -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host $_
            }
        }

        if ($process.ExitCode -ne 0) {
            throw "$FailureMessage (exit code $($process.ExitCode))"
        }
    }
    finally {
        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path $path) {
                Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Resolve-InstallerOutputPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallerDir,
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $expectedPath = Join-Path $InstallerDir ("AdminAssistant_v{0}_Setup.exe" -f $Version)
    if (Test-Path $expectedPath) {
        return (Resolve-Path $expectedPath).Path
    }

    $fallback = Get-ChildItem -Path $InstallerDir -Filter "AdminAssistant*_Setup.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -ne $fallback) {
        return $fallback.FullName
    }

    return $null
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

    Invoke-LoggedCommand `
        -FilePath $resolvedPythonExe `
        -ArgumentList @("-m", "PyInstaller", "--clean", "-y", $specPath) `
        -FailureMessage "PyInstaller build failed"
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
Invoke-LoggedCommand `
    -FilePath $resolvedInnoSetupCompiler `
    -ArgumentList @(
        "/DMyAppVersion=$($versionInfo.version)",
        "/DMyAppPublisher=$($versionInfo.publisher)",
        "/DMyAppName=$($versionInfo.app_name)",
        "/DDistDir=$distDir",
        $installerScript
    ) `
    -FailureMessage "Inno Setup build failed"

$installerDir = Join-Path $projectRoot "installer"
$installerPath = Resolve-InstallerOutputPath -InstallerDir $installerDir -Version $versionInfo.version
if ([string]::IsNullOrWhiteSpace($installerPath)) {
    throw "Installer output not found in $installerDir"
}

Write-Host "Installer build complete: $installerPath"

if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_ENV)) {
    Add-Content -Path $env:GITHUB_ENV -Value "INSTALLER_PATH=$installerPath"
}

Write-Output $installerPath

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$InstallerUrl,
    [Parameter(Mandatory = $true)]
    [string]$Sha256,
    [string]$ProductCode = "{A4B4D6A0-7E75-4A54-AF4C-9D8C56A0C712}"
)

$ErrorActionPreference = "Stop"

function Write-Utf8NoBomFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $directory = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($directory) -and -not (Test-Path $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$normalizedVersion = $Version.Trim()
if ($normalizedVersion.StartsWith("v")) {
    $normalizedVersion = $normalizedVersion.Substring(1)
}

$normalizedInstallerUrl = $InstallerUrl.Trim()
$normalizedSha256 = $Sha256.Trim().ToUpperInvariant()
$normalizedProductCode = $ProductCode.Trim()

$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}

$scriptDir = Split-Path -Parent $scriptPath
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$manifestDir = Join-Path $projectRoot "manifests\f\fedorovdo\AdminAssistant\$normalizedVersion"

$versionManifestPath = Join-Path $manifestDir "fedorovdo.AdminAssistant.yaml"
$localeManifestPath = Join-Path $manifestDir "fedorovdo.AdminAssistant.locale.en-US.yaml"
$installerManifestPath = Join-Path $manifestDir "fedorovdo.AdminAssistant.installer.yaml"

$versionManifest = @"
# yaml-language-server: `$schema=https://aka.ms/winget-manifest.version.1.12.0.schema.json
PackageIdentifier: fedorovdo.AdminAssistant
PackageVersion: $normalizedVersion
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.12.0
"@

$localeManifest = @"
# yaml-language-server: `$schema=https://aka.ms/winget-manifest.defaultLocale.1.12.0.schema.json
PackageIdentifier: fedorovdo.AdminAssistant
PackageVersion: $normalizedVersion
PackageLocale: en-US
Publisher: Dmitrii Fedorov
PublisherUrl: https://github.com/fedorovdo
PublisherSupportUrl: https://github.com/fedorovdo/admin-assistant/issues
Author: Dmitrii Fedorov
PackageName: Admin Assistant
PackageUrl: https://github.com/fedorovdo/admin-assistant
ShortDescription: AI-powered desktop tool for server troubleshooting and incident investigation.
Description: Admin Assistant is a Windows desktop application for SSH execution, reusable scripts, AI analysis, suggested actions, fix plans, and safe incident investigation workflows.
License: MIT
LicenseUrl: https://github.com/fedorovdo/admin-assistant/blob/main/LICENSE
Copyright: Copyright (c) 2026 Dmitrii Fedorov
Moniker: admin-assistant
Tags:
  - ssh
  - server
  - troubleshooting
  - incident-response
  - ai
ManifestType: defaultLocale
ManifestVersion: 1.12.0
"@

$installerManifest = @"
# yaml-language-server: `$schema=https://aka.ms/winget-manifest.installer.1.12.0.schema.json
PackageIdentifier: fedorovdo.AdminAssistant
PackageVersion: $normalizedVersion
InstallerType: inno
Scope: machine
UpgradeBehavior: install
Installers:
  - Architecture: x64
    InstallerUrl: $normalizedInstallerUrl
    InstallerSha256: $normalizedSha256
    ProductCode: "$normalizedProductCode"
ManifestType: installer
ManifestVersion: 1.12.0
"@

Write-Utf8NoBomFile -Path $versionManifestPath -Content $versionManifest
Write-Utf8NoBomFile -Path $localeManifestPath -Content $localeManifest
Write-Utf8NoBomFile -Path $installerManifestPath -Content $installerManifest

Write-Host "Generated Winget manifests in $manifestDir"

if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) {
    Add-Content -Path $env:GITHUB_OUTPUT -Value "manifest_dir=$manifestDir"
}

Write-Output $manifestDir

<#
.SYNOPSIS
  Build + cai plugin NwMcpBridge cho Autodesk Navisworks Manage 2025 (tu tim thu muc cai tu shortcut .lnk).

.EXAMPLE
  .\build_bridge.ps1 -DetectOnly                  # chi do thu muc cai, phien ban, DLL API (khong build)
  .\build_bridge.ps1                              # build + copy vao <thu muc cai>\Plugins\NwMcpBridge\ (can quyen Admin)
  .\build_bridge.ps1 -Mode Bundle                 # cai dang bundle vao %APPDATA%\Autodesk\ApplicationPlugins (khong can Admin)
  .\build_bridge.ps1 -InstallDir "D:\Autodesk\Navisworks Manage 2025"
#>
param(
    [string]$ShortcutPath = "C:\Users\Public\Desktop\Navisworks Manage 2025.lnk",
    [string]$InstallDir,
    [ValidateSet("InstallDir", "Bundle")] [string]$Mode = "InstallDir",
    [string]$BundleSeries = "Nw22",    # SeriesMin/SeriesMax trong PackageContents.xml (Mode Bundle) - doi chieu docs Autodesk neu khong nap
    [string]$BundleFolder = "v22",     # thu muc con Contents\<v..> (Navisworks 2025 = v22 theo docs APS)
    [string]$Configuration = "Release",
    [switch]$DetectOnly
)

$ErrorActionPreference = "Stop"
$projectDir = Join-Path $PSScriptRoot "..\bridge\NwMcpBridge"
$addIn = "NwMcpBridge"

function Resolve-ShortcutTarget([string]$lnk) {
    if (-not (Test-Path $lnk)) { return $null }
    $sh = New-Object -ComObject WScript.Shell
    $link = $sh.CreateShortcut($lnk)
    return $link.TargetPath
}

# 1) Thu muc cai: tham so > shortcut > duong dan mac dinh
if (-not $InstallDir) {
    $target = Resolve-ShortcutTarget $ShortcutPath
    if ($target) {
        Write-Host "Shortcut      : $ShortcutPath"
        Write-Host "  -> target   : $target"
        $InstallDir = Split-Path -Parent $target
    }
}
if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir "Autodesk.Navisworks.Api.dll"))) {
    $default = "C:\Program Files\Autodesk\Navisworks Manage 2025"
    if (Test-Path (Join-Path $default "Autodesk.Navisworks.Api.dll")) { $InstallDir = $default }
}
if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir "Autodesk.Navisworks.Api.dll"))) {
    throw "Khong tim thay Autodesk.Navisworks.Api.dll. Dung -InstallDir <thu muc chua Roamer.exe / Autodesk.Navisworks.Api.dll>."
}
$InstallDir = (Resolve-Path $InstallDir).Path.TrimEnd('\') + '\'
Write-Host "Thu muc cai   : $InstallDir"

$exe = Get-ChildItem $InstallDir -Filter "Roamer.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $exe) { $exe = Get-ChildItem $InstallDir -Filter "*.exe" | Where-Object { $_.Name -match "Navis|Roamer|Manage" } | Select-Object -First 1 }
if ($exe) { Write-Host "Chuong trinh  : $($exe.Name) v$($exe.VersionInfo.ProductVersion)" }

foreach ($dll in "Autodesk.Navisworks.Api.dll", "Autodesk.Navisworks.Clash.dll", "Autodesk.Navisworks.Timeliner.dll",
                 "Autodesk.Navisworks.Takeoff.dll", "Autodesk.Navisworks.ComApi.dll", "Autodesk.Navisworks.Controls.dll") {
    $ok = Test-Path (Join-Path $InstallDir $dll)
    Write-Host ("  {0,-40} {1}" -f $dll, $(if ($ok) { "OK" } else { "khong co" }))
}
$apiVer = (Get-Item (Join-Path $InstallDir "Autodesk.Navisworks.Api.dll")).VersionInfo.FileVersion
Write-Host "  API version                              $apiVer"
$pluginsDir = Join-Path $InstallDir "Plugins"
Write-Host "  Thu muc Plugins                          $(if (Test-Path $pluginsDir) { 'co' } else { 'khong co' })"
if ($DetectOnly) { return }

# 2) Build (Navisworks 2025 = .NET Framework 4.8)
Write-Host "`n== Build $addIn ($Configuration, net48) =="
dotnet build $projectDir -c $Configuration -p:NavisworksDir="$InstallDir"
if ($LASTEXITCODE -ne 0) { throw "Build that bai." }
$outDir = Join-Path $projectDir "bin\$Configuration\net48"
if (-not (Test-Path (Join-Path $outDir "$addIn.dll"))) { throw "Khong thay $addIn.dll trong $outDir" }

# 3) Cai
if ($Mode -eq "InstallDir") {
    $dest = Join-Path $pluginsDir $addIn
    try {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item (Join-Path $outDir "*") $dest -Recurse -Force
    } catch {
        throw "Khong ghi duoc vao '$dest' ($($_.Exception.Message)). Chay PowerShell bang 'Run as administrator' hoac dung -Mode Bundle."
    }
    Write-Host "Da cai plugin vao: $dest"
} else {
    $bundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\$addIn.bundle"
    $contents = Join-Path $bundle "Contents\$BundleFolder"
    New-Item -ItemType Directory -Force -Path $contents | Out-Null
    Copy-Item (Join-Path $outDir "*") $contents -Recurse -Force
    $xml = @"
<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="Navisworks" ProductType="Application" Name="$addIn"
                    AppVersion="0.1.0" Description="MCP bridge cho Claude" Author="TEDI"
                    UpgradeCode="{6C0B5F0A-3C84-4B63-9A7E-5E0D4F2A1B77}">
  <CompanyDetails Name="TEDI" />
  <Components>
    <RuntimeRequirements OS="Win64" Platform="Navisworks" SeriesMin="$BundleSeries" SeriesMax="$BundleSeries" />
    <ComponentEntry AppName="$addIn" AppType="ManagedPlugin" ModuleName="./Contents/$BundleFolder/$addIn.dll"
                    AppDescription="MCP bridge cho Claude" />
  </Components>
</ApplicationPackage>
"@
    Set-Content -Path (Join-Path $bundle "PackageContents.xml") -Value $xml -Encoding UTF8
    Write-Host "Da cai bundle vao: $bundle"
    Write-Host "(Neu Navisworks khong nap bundle: kiem tra SeriesMin/SeriesMax/ten thu muc theo docs APS, hoac dung -Mode InstallDir.)"
}

Write-Host @"

== Buoc tiep theo ==
1) Khoi dong lai Navisworks Manage 2025 va mo mot mo hinh (hoac de trong).
2) Plugin tu bat khi khoi dong. Kiem tra: tab Add-ins > MCP Bridge (hien trang thai), hoac xem file
   %LOCALAPPDATA%\NwMcp\bridge.json  va  %LOCALAPPDATA%\NwMcp\bridge.log
3) Neu moi lenh bao 'Main thread khong phan hoi': bam Add-ins > MCP Bridge 1 lan.
4) Cau hinh MCP client (Claude Desktop / Claude Code) - xem Navisworks_MCP\README.md
"@

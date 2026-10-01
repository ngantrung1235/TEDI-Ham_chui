<#
.SYNOPSIS
  Do runtime .NET cua OpenTunnel Designer 2026, build add-in OTDMcpBridge va copy ra thu muc cai dat.

.EXAMPLE
  # Chi kiem tra ban cai (khong build)
  .\build_bridge.ps1 -DetectOnly

  # Build + cai vao %LOCALAPPDATA%\OTDMcp\bin
  .\build_bridge.ps1

  # Chi dinh thu muc cai OTD (thu muc chua ustation.dll)
  .\build_bridge.ps1 -InstallDir "D:\Bentley\OpenTunnel Designer 2026\OpenTunnelDesigner"
#>
param(
    [string]$InstallDir,
    [string]$DeployDir = (Join-Path $env:LOCALAPPDATA "OTDMcp\bin"),
    [string]$Configuration = "Release",
    [switch]$DetectOnly
)

$ErrorActionPreference = "Stop"
$projectDir = Join-Path $PSScriptRoot "..\bridge\OTDMcpBridge"

function Find-InstallDir {
    $roots = @("$env:ProgramFiles\Bentley", "${env:ProgramFiles(x86)}\Bentley") | Where-Object { $_ -and (Test-Path $_) }
    foreach ($root in $roots) {
        $hit = Get-ChildItem $root -Directory -Filter "*OpenTunnel*" -ErrorAction SilentlyContinue |
            ForEach-Object { Get-ChildItem $_.FullName -Recurse -Depth 2 -Filter "ustation.dll" -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if ($hit) { return $hit.DirectoryName }
    }
    return $null
}

if (-not $InstallDir) { $InstallDir = Find-InstallDir }
if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir "ustation.dll"))) {
    throw "Khong tim thay thu muc cai OpenTunnel Designer (thu muc chua ustation.dll). Dung -InstallDir."
}
$InstallDir = (Resolve-Path $InstallDir).Path.TrimEnd('\') + '\'
Write-Host "Thu muc OTD   : $InstallDir"

# Phien ban san pham (mong doi 26.00.00.83 cho OTD 2026)
$exe = Get-ChildItem $InstallDir -Filter "*.exe" |
    Where-Object { $_.Name -match "OpenTunnel|ustation|MicroStation" } | Select-Object -First 1
if ($exe) { Write-Host "Chuong trinh  : $($exe.Name) v$($exe.VersionInfo.ProductVersion)" }

# Runtime: *.runtimeconfig.json => .NET (Core) ; *.exe.config => .NET Framework
$tfm = $null
$rc = Get-ChildItem $InstallDir -Filter "*.runtimeconfig.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($rc) {
    $json = Get-Content $rc.FullName -Raw | ConvertFrom-Json
    $fw = @($json.runtimeOptions.framework) + @($json.runtimeOptions.frameworks) | Where-Object { $_ } | Select-Object -First 1
    $major = ($fw.version -split '\.')[0]
    $tfm = "net$major.0-windows"
    Write-Host "Runtime       : $($fw.name) $($fw.version)  (tu $($rc.Name))"
} elseif (Get-ChildItem $InstallDir -Filter "*.exe.config" -ErrorAction SilentlyContinue) {
    $tfm = "net48"
    Write-Host "Runtime       : .NET Framework 4.x (co *.exe.config)"
} else {
    $tfm = "net48"
    Write-Warning "Khong xac dinh duoc runtime, mac dinh net48. Neu add-in khong nap duoc, build lai voi net8.0-windows."
}
Write-Host "Target build  : $tfm"

$required = "ustation.dll", "Bentley.DgnPlatformNET.dll", "Bentley.GeometryNET.dll",
            "Bentley.GeometryNET.Structs.dll", "Bentley.ECObjects3.dll"
foreach ($dll in $required) {
    $ok = Test-Path (Join-Path $InstallDir $dll)
    Write-Host ("  {0,-34} {1}" -f $dll, $(if ($ok) { "OK" } else { "THIEU" }))
}
$interop = @("Assemblies\Bentley.Interop.MicroStationDGN.dll", "Bentley.Interop.MicroStationDGN.dll") |
    Where-Object { Test-Path (Join-Path $InstallDir $_) } | Select-Object -First 1
Write-Host ("  {0,-34} {1}" -f "Bentley.Interop.MicroStationDGN.dll", $(if ($interop) { "OK ($interop)" } else { "THIEU" }))

$civil = Get-ChildItem $InstallDir -Filter "Bentley.CifNET*.dll" -ErrorAction SilentlyContinue | Measure-Object
$tunnel = Get-ChildItem $InstallDir -Recurse -Depth 1 -Filter "*Tunnel*.dll" -ErrorAction SilentlyContinue | Select-Object -First 10
Write-Host "  Bentley.CifNET*.dll (OpenRoads)    : $($civil.Count) file"
if ($tunnel) { Write-Host "  DLL chua 'Tunnel'                  : $(($tunnel | ForEach-Object Name) -join ', ')" }

if ($DetectOnly) { return }

Write-Host "`n== Build OTDMcpBridge ($Configuration, $tfm) =="
dotnet build $projectDir -c $Configuration -p:OtdInstallDir="$InstallDir" -p:OtdTargetFramework=$tfm
if ($LASTEXITCODE -ne 0) { throw "Build that bai." }

$outDir = Join-Path $projectDir "bin\$Configuration\$tfm"
New-Item -ItemType Directory -Force -Path $DeployDir | Out-Null
Copy-Item (Join-Path $outDir "*") $DeployDir -Recurse -Force
Write-Host "Da copy add-in vao: $DeployDir"

$cfgPath = $DeployDir.Replace('\', '/').TrimEnd('/') + '/'
Write-Host @"

== Buoc tiep theo ==
1) Them vao file cau hinh user cua OTD (vd ...\Configuration\Personal.ucf hoac WorkSpace .cfg):

     MS_ADDINPATH > $cfgPath
     MS_DGNAPPS   > OTDMcpBridge        # (tuy chon) tu nap khi mo file DGN

2) Khoi dong lai OTD, mo file DGN, go key-in:  mdl load OTDMcpBridge
   Kiem tra:                                    OTDMCP STATUS
3) Cau hinh MCP client (Claude Desktop / Claude Code) - xem OpenTunnel_MCP\README.md
"@

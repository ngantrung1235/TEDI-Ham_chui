<#
.SYNOPSIS
  Script CHUNG: do runtime .NET cua san pham Bentley (nen MicroStation), build add-in MCP bridge
  va copy ra thu muc cai dat. Duoc goi tu script mong cua tung san pham, vd:
    OpenTunnel_MCP\scripts\build_bridge.ps1   (OTDMcpBridge)
    OpenBridge_MCP\scripts\build_bridge.ps1   (OBDMcpBridge)
#>
param(
    [Parameter(Mandatory)] [string]$ProjectDir,      # thu muc chua <AddInName>.csproj
    [Parameter(Mandatory)] [string]$AddInName,       # OTDMcpBridge | OBDMcpBridge
    [Parameter(Mandatory)] [string]$ProductPattern,  # "*OpenTunnel*" | "*OpenBridge*" (thu muc trong ...\Bentley)
    [Parameter(Mandatory)] [string]$DeployDir,
    [string]$InstallDir,
    [string]$Configuration = "Release",
    [switch]$DetectOnly
)

$ErrorActionPreference = "Stop"
$projectDir = $ProjectDir

function Find-InstallDir {
    $roots = @("$env:ProgramFiles\Bentley", "${env:ProgramFiles(x86)}\Bentley") | Where-Object { $_ -and (Test-Path $_) }
    foreach ($root in $roots) {
        $hit = Get-ChildItem $root -Directory -Filter $ProductPattern -ErrorAction SilentlyContinue |
            ForEach-Object { Get-ChildItem $_.FullName -Recurse -Depth 2 -Filter "ustation.dll" -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if ($hit) { return $hit.DirectoryName }
    }
    return $null
}

if (-not $InstallDir) { $InstallDir = Find-InstallDir }
if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir "ustation.dll"))) {
    throw "Khong tim thay thu muc cai san pham ($ProductPattern, thu muc chua ustation.dll). Dung -InstallDir."
}
$InstallDir = (Resolve-Path $InstallDir).Path.TrimEnd('\') + '\'
Write-Host "Thu muc cai   : $InstallDir"

# Phien ban san pham (OTD 2026 = 26.00.00.83, OBD 2026 = 26.00.00.142)
$exeHint = $ProductPattern.Trim('*')
$exe = Get-ChildItem $InstallDir -Filter "*.exe" |
    Where-Object { $_.Name -match "$exeHint|ustation|MicroStation" } | Select-Object -First 1
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
$productDlls = Get-ChildItem $InstallDir -Recurse -Depth 1 -Filter "*$($exeHint -replace '^Open','')*.dll" -ErrorAction SilentlyContinue | Select-Object -First 15
Write-Host "  Bentley.CifNET*.dll (OpenRoads)    : $($civil.Count) file"
if ($productDlls) { Write-Host "  DLL rieng san pham                 : $(($productDlls | ForEach-Object Name) -join ', ')" }

if ($DetectOnly) { return }

Write-Host "`n== Build $AddInName ($Configuration, $tfm) =="
dotnet build $projectDir -c $Configuration -p:BentleyInstallDir="$InstallDir" -p:BentleyTargetFramework=$tfm
if ($LASTEXITCODE -ne 0) { throw "Build that bai." }

$outDir = Join-Path $projectDir "bin\$Configuration\$tfm"
New-Item -ItemType Directory -Force -Path $DeployDir | Out-Null
Copy-Item (Join-Path $outDir "*") $DeployDir -Recurse -Force
Write-Host "Da copy add-in vao: $DeployDir"

$cfgPath = $DeployDir.Replace('\', '/').TrimEnd('/') + '/'
Write-Host @"

== Buoc tiep theo ==
1) Them vao file cau hinh user cua san pham (vd ...\Configuration\Personal.ucf hoac WorkSpace .cfg):

     MS_ADDINPATH > $cfgPath
     MS_DGNAPPS   > $AddInName        # (tuy chon) tu nap khi mo file DGN

2) Khoi dong lai san pham, mo file DGN, go key-in:  mdl load $AddInName
   Kiem tra trang thai bang key-in <PREFIX> STATUS (OTDMCP STATUS / OBDMCP STATUS)
3) Cau hinh MCP client (Claude Desktop / Claude Code) - xem README.md cua san pham
"@

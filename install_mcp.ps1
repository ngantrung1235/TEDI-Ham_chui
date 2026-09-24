# Cai dat ca hai MCP (PLAXIS 3D + AutoCAD) va dang ky voi Claude Code tren terminal.
#   powershell -ExecutionPolicy Bypass -File .\install_mcp.ps1 -PlaxisPassword "matkhau"
# Thu muc .\wheels (neu co) cho phep cai offline voi Python 3.12.
param([string]$PlaxisPassword = "", [ValidateSet("user", "project", "local")][string]$Scope = "user")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$wheels = Join-Path $root "wheels"
foreach ($pkg in @("PLAXIS3D_MCP", "AUTOCAD_MCP")) {
    $dir = Join-Path $root $pkg
    if ((Test-Path $wheels) -and -not (Test-Path (Join-Path $dir "wheels"))) {
        New-Item -ItemType Junction -Path (Join-Path $dir "wheels") -Target $wheels | Out-Null
    }
}
Write-Host "==================== PLAXIS 3D MCP ====================" -ForegroundColor Magenta
if ($PlaxisPassword) {
    & (Join-Path $root "PLAXIS3D_MCP\install.ps1") -Password $PlaxisPassword -Scope $Scope
} else {
    & (Join-Path $root "PLAXIS3D_MCP\install.ps1") -Scope $Scope
}
Write-Host "==================== AutoCAD MCP ======================" -ForegroundColor Magenta
& (Join-Path $root "AUTOCAD_MCP\install.ps1") -Scope $Scope
Write-Host ""
Write-Host "Hoan tat. Mo terminal moi, go 'claude' roi '/mcp': se thay 'plaxis3d' va 'autocad'." -ForegroundColor Green

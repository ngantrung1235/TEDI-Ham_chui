# Cai dat PLAXIS 3D MCP server (Windows PowerShell)
# Chay: powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if (-not (Test-Path ".venv")) {
    if ($py -eq "py") { & py -3 -m venv .venv } else { & python -m venv .venv }
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[test]"
& .\.venv\Scripts\python.exe -m pytest -q

$exe = Join-Path $root ".venv\Scripts\python.exe"
Write-Host ""
Write-Host "Da cai xong. Dang ky voi Claude Code bang lenh:" -ForegroundColor Green
Write-Host "  claude mcp add plaxis3d --scope user -e PLAXIS_PASSWORD=<mat-khau> -- `"$exe`" -m plaxis3d_mcp"
Write-Host "Nho bat Expert > Configure remote scripting server trong PLAXIS 3D Input (port 10000)."

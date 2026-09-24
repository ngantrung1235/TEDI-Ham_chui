# Cai dat PLAXIS 3D MCP server va dang ky voi Claude Code (terminal).
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Password "matkhau" -Scope user
#
# -Password : mat khau Remote scripting server da dat trong PLAXIS 3D Input
# -Scope    : user (moi thu muc), project (ghi .mcp.json vao thu muc hien tai), local
# -NoRegister : chi cai dat, khong dang ky voi Claude Code
param(
    [string]$Password = "",
    [ValidateSet("user", "project", "local")][string]$Scope = "user",
    [int]$Port = 10000,
    [switch]$NoRegister
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# 1. Python >= 3.10
Step "Kiem tra Python"
$py = $null
$candidates = @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python"))
foreach ($cand in $candidates) {
    if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
    $args0 = @($cand | Select-Object -Skip 1)
    try {
        $v = & $cand[0] @args0 -c "import sys; print(sys.version_info >= (3, 10))" 2>&1
        if ("$v".Trim() -eq "True") { $py = $cand; break }
    } catch {}
}
if (-not $py) { throw "Can Python >= 3.10 (https://www.python.org/downloads/). Nho tick 'Add python.exe to PATH'." }
Write-Host "    dung: $($py -join ' ')"

# 2. venv + packages
Step "Tao moi truong ao .venv va cai thu vien"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $pyArgs = @($py | Select-Object -Skip 1) + @("-m", "venv", ".venv")
    & $py[0] @pyArgs
}
$exe = Join-Path $root ".venv\Scripts\python.exe"
& $exe -m pip install --upgrade pip | Out-Null
& $exe -m pip install -e ".[all]"
if ($LASTEXITCODE -ne 0) { throw "pip install that bai" }

# 3. tests
Step "Chay kiem thu"
& $exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Kiem thu that bai" }

# 4. register with Claude Code
if ($NoRegister) { Write-Host "Bo qua dang ky (-NoRegister)."; exit 0 }
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "Chua thay lenh 'claude'. Cai Claude Code: npm install -g @anthropic-ai/claude-code" -ForegroundColor Yellow
    Write-Host "Sau do chay lai script nay, hoac tu dang ky:"
    Write-Host "  claude mcp add plaxis3d --scope $Scope -e PLAXIS_PASSWORD=<mat-khau> -- `"$exe`" -m plaxis3d_mcp"
    exit 0
}
if (-not $Password) {
    $sec = Read-Host "Mat khau Remote scripting server cua PLAXIS" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
Step "Dang ky MCP 'plaxis3d' voi Claude Code (scope: $Scope)"
try { & claude mcp remove plaxis3d --scope $Scope *> $null } catch {}  # ignore "not found"
& claude mcp add plaxis3d --scope $Scope -e "PLAXIS_PASSWORD=$Password" -e "PLAXIS_INPUT_PORT=$Port" -- "$exe" -m plaxis3d_mcp
if ($LASTEXITCODE -ne 0) { throw "claude mcp add that bai" }

# 5. connection check (PLAXIS may not be open yet)
Step "Kiem tra ket noi PLAXIS (can mo PLAXIS 3D Input va bat Remote scripting server)"
$env:PLAXIS_PASSWORD = $Password
$env:PLAXIS_INPUT_PORT = "$Port"
& $exe -m plaxis3d_mcp --check

Write-Host ""
Write-Host "XONG. Mo terminal moi, go 'claude', roi go /mcp de thay 'plaxis3d'." -ForegroundColor Green
Write-Host "Tinh toan lau: dat `$env:MCP_TOOL_TIMEOUT = '7200000' truoc khi chay 'claude'."

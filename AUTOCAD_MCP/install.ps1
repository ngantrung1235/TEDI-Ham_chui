# Cai dat AutoCAD MCP server va dang ky voi Claude Code (terminal).
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Scope project -ProgId "AutoCAD.Application.24"
#
# -Scope    : user (moi thu muc) | project (.mcp.json trong thu muc hien tai) | local
# -ProgId   : ep dung mot san pham/phien ban (mac dinh: tu tim AutoCAD dang chay, moi phien ban)
# -NoRegister : chi cai dat
param(
    [ValidateSet("user", "project", "local")][string]$Scope = "user",
    [string]$ProgId = "",
    [switch]$NoRegister
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

Step "Kiem tra Python"
$py = $null
foreach ($cand in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.13"), @("py", "-3.10"), @("python"))) {
    if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
    $a = @($cand | Select-Object -Skip 1)
    try {
        $v = & $cand[0] @a -c "import sys; print(sys.version_info >= (3, 10))" 2>&1
        if ("$v".Trim() -eq "True") { $py = $cand; break }
    } catch {}
}
if (-not $py) { throw "Can Python >= 3.10 (https://www.python.org/downloads/), tick 'Add python.exe to PATH'." }
Write-Host "    dung: $($py -join ' ')"

Step "Tao .venv va cai thu vien"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $a = @($py | Select-Object -Skip 1) + @("-m", "venv", ".venv")
    & $py[0] @a
}
$exe = Join-Path $root ".venv\Scripts\python.exe"
$installed = $false
foreach ($w in @((Join-Path $root "wheels"), (Join-Path (Split-Path $root -Parent) "wheels"))) {
    if (Test-Path $w) {
        Write-Host "    cai offline tu $w"
        & $exe -m pip install --no-index --find-links $w --upgrade pip | Out-Null
        & $exe -m pip install --no-index --find-links $w -e ".[all]"
        $installed = ($LASTEXITCODE -eq 0)
        break
    }
}
if (-not $installed) {
    & $exe -m pip install --upgrade pip | Out-Null
    & $exe -m pip install -e ".[all]"
    if ($LASTEXITCODE -ne 0) { throw "pip install that bai" }
}

Step "Chay kiem thu"
& $exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Kiem thu that bai" }

if ($NoRegister) { exit 0 }
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "Chua co lenh 'claude'. Cai: npm install -g @anthropic-ai/claude-code" -ForegroundColor Yellow
    Write-Host "  claude mcp add autocad --scope $Scope -- `"$exe`" -m autocad_mcp"
    exit 0
}
Step "Dang ky MCP 'autocad' voi Claude Code (scope: $Scope)"
try { & claude mcp remove autocad --scope $Scope *> $null } catch {}
$envArgs = @()
if ($ProgId) { $envArgs = @("-e", "AUTOCAD_PROGID=$ProgId") }
& claude mcp add autocad --scope $Scope @envArgs -- "$exe" -m autocad_mcp
if ($LASTEXITCODE -ne 0) { throw "claude mcp add that bai" }

Step "Kiem tra ket noi AutoCAD (mo AutoCAD truoc; neu khong co se dung che do DXF)"
if ($ProgId) { $env:AUTOCAD_PROGID = $ProgId }
& $exe -m autocad_mcp --check

Write-Host ""
Write-Host "XONG. Mo terminal moi, go 'claude', roi '/mcp' de thay 'autocad'." -ForegroundColor Green

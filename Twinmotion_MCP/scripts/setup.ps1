<#
.SYNOPSIS
  Kiem tra moi truong va cai MCP Twinmotion (khong can build C#: MCP nay chi dung Python).

.EXAMPLE
  .\setup.ps1                                  # doc shortcut mac dinh, cai goi Python, in cau hinh Claude
  .\setup.ps1 -Uia                             # cai them pywinauto (UI Automation, tuy chon)
  .\setup.ps1 -ShortcutPath "D:\Desktop\Twinmotion.lnk"
#>
param(
    [string]$ShortcutPath = "C:\Users\Public\Desktop\Twinmotion 2026.1 For Revit.lnk",
    [switch]$Uia
)

$ErrorActionPreference = "Stop"
$serverDir = (Resolve-Path (Join-Path $PSScriptRoot "..\server")).Path

# 1) Shortcut -> exe
if (-not (Test-Path $ShortcutPath)) {
    throw "Khong thay shortcut: $ShortcutPath  (dung -ShortcutPath hoac dat bien moi truong TM_EXE tro thang toi Twinmotion.exe)"
}
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($ShortcutPath)
Write-Host "Shortcut      : $ShortcutPath"
Write-Host "  target      : $($link.TargetPath)"
Write-Host "  arguments   : $($link.Arguments)"
Write-Host "  working dir : $($link.WorkingDirectory)"
if (-not $link.TargetPath -or -not (Test-Path $link.TargetPath)) {
    Write-Warning "Muc tieu cua shortcut khong ton tai/khong doc duoc. Dat TM_EXE = duong dan Twinmotion.exe."
}

# 2) Phien ban + quyen
if ($link.TargetPath -and (Test-Path $link.TargetPath)) {
    Write-Host "  version     : $((Get-Item $link.TargetPath).VersionInfo.ProductVersion)"
}
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "Quyen Admin   : $isAdmin"
Write-Host "  (Neu Twinmotion chay voi quyen Admin thi MCP/Claude cung phai chay Admin, neu khong Windows UIPI se CHAN chuot/phim.)"

# 3) Python + uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warning "Chua co 'uv'. Cai: winget install --id=astral-sh.uv -e   (hoac dung pip: pip install -e ..\..\Mcp_Common\python -e .)"
} else {
    Push-Location $serverDir
    try {
        if ($Uia) { uv sync --extra uia } else { uv sync }
    } finally { Pop-Location }
}

# 4) Cau hinh Claude
$dirJson = $serverDir.Replace('\', '\\')
Write-Host @"

== Cau hinh Claude Desktop (%APPDATA%\Claude\claude_desktop_config.json) ==
{
  "mcpServers": {
    "twinmotion": {
      "command": "uv",
      "args": ["--directory", "$dirJson", "run", "tm-mcp"],
      "env": { "TM_SHORTCUT": "$($ShortcutPath.Replace('\', '\\'))" }
    }
  }
}

== Claude Code ==
claude mcp add twinmotion -e TM_SHORTCUT="$ShortcutPath" -- uv --directory "$serverDir" run tm-mcp

Che do CHI-DOC (khong chuot/phim):  them  "TM_MCP_ALLOW_INPUT": "0"  vao env.
Dung khan cap: dua chuot vao goc tren-trai man hinh.
"@

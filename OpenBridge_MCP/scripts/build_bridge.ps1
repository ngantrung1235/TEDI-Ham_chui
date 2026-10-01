<#
.SYNOPSIS
  Build + cai add-in OBDMcpBridge cho OpenBridge Designer 2026 (26.00.00.142).
.EXAMPLE
  .\build_bridge.ps1 -DetectOnly        # chi do thu muc cai, runtime .NET, DLL Bentley
  .\build_bridge.ps1                    # build + copy vao %LOCALAPPDATA%\OBDMcp\bin
  .\build_bridge.ps1 -InstallDir "D:\Bentley\OpenBridge Designer 2026\OpenBridgeDesigner"
#>
param(
    [string]$InstallDir,
    [string]$DeployDir = (Join-Path $env:LOCALAPPDATA "OBDMcp\bin"),
    [string]$Configuration = "Release",
    [switch]$DetectOnly
)

& (Join-Path $PSScriptRoot "..\..\Bentley_MCP_Core\scripts\build_bridge.ps1") `
    -ProjectDir (Join-Path $PSScriptRoot "..\bridge\OBDMcpBridge") `
    -AddInName "OBDMcpBridge" -ProductPattern "*OpenBridge*" `
    -DeployDir $DeployDir -InstallDir $InstallDir -Configuration $Configuration -DetectOnly:$DetectOnly

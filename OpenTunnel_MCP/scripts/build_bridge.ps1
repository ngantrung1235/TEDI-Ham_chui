<#
.SYNOPSIS
  Build + cai add-in OTDMcpBridge cho OpenTunnel Designer 2026 (26.00.00.83).
.EXAMPLE
  .\build_bridge.ps1 -DetectOnly        # chi do thu muc cai, runtime .NET, DLL Bentley
  .\build_bridge.ps1                    # build + copy vao %LOCALAPPDATA%\OTDMcp\bin
  .\build_bridge.ps1 -InstallDir "D:\Bentley\OpenTunnel Designer 2026\OpenTunnelDesigner"
#>
param(
    [string]$InstallDir,
    [string]$DeployDir = (Join-Path $env:LOCALAPPDATA "OTDMcp\bin"),
    [string]$Configuration = "Release",
    [switch]$DetectOnly
)

& (Join-Path $PSScriptRoot "..\..\Bentley_MCP_Core\scripts\build_bridge.ps1") `
    -ProjectDir (Join-Path $PSScriptRoot "..\bridge\OTDMcpBridge") `
    -AddInName "OTDMcpBridge" -ProductPattern "*OpenTunnel*" `
    -DeployDir $DeployDir -InstallDir $InstallDir -Configuration $Configuration -DetectOnly:$DetectOnly

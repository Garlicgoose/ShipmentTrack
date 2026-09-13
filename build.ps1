# -*- coding: utf-8 -*-
# Shipment Track 一键打包脚本（Windows PowerShell）
# 1) PyInstaller 构建 onedir
# 2) 将默认 JSON 复制到 data 文件夹，并复制使用说明
# Chromium 始终作为外接依赖，不复制进安装目录。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist\Shipment Track"
$dataDir = Join-Path $dist "data"

Write-Host "=== Step 1: PyInstaller build ==="
python -m PyInstaller ShipmentTrack.spec --noconfirm --clean

Write-Host "=== Step 2: copy data defaults & readme ==="
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot "filename_mappings.json") -Destination $dataDir -Force
Copy-Item (Join-Path $PSScriptRoot "delivery_status_mappings.json") -Destination $dataDir -Force
Copy-Item (Join-Path $PSScriptRoot "使用说明.txt") -Destination $dist -Force

Write-Host "=== Done ==="
Write-Host "输出目录: $dist"
Write-Host "启动: $dist\Shipment Track.exe"
Write-Host "首次运行请在设置页自动检测或手动选择外接 Chromium 的 chrome.exe。"

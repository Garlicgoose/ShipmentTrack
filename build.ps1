# -*- coding: utf-8 -*-
# Shipment Track 一键打包脚本（Windows PowerShell）
# 1) PyInstaller 构建 onedir
# 2) 构建 GetMachineId.exe（给同事查机器码用）
# 3) 复制默认文件名映射 + 使用说明
# Chromium 始终作为外接依赖，不复制进安装目录。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist\Shipment Track"

Write-Host "=== Step 1: PyInstaller build ==="
python -m PyInstaller ShipmentTrack.spec --noconfirm --clean

Write-Host "=== Step 2: build GetMachineId.exe ==="
python -m PyInstaller --onefile --console --name GetMachineId `
    --distpath $dist --workpath (Join-Path $PSScriptRoot "build\gm") `
    --specpath (Join-Path $PSScriptRoot "build\gm") `
    (Join-Path $PSScriptRoot "machine_id.py") | Out-Null

Write-Host "=== Step 3: copy defaults & readme ==="
Copy-Item (Join-Path $PSScriptRoot "filename_mappings.json") -Destination $dist -Force
Copy-Item (Join-Path $PSScriptRoot "delivery_status_mappings.json") -Destination $dist -Force
Copy-Item (Join-Path $PSScriptRoot "使用说明.txt") -Destination $dist -Force

Write-Host "=== Done ==="
Write-Host "输出目录: $dist"
Write-Host "启动: $dist\Shipment Track.exe"
Write-Host "首次运行请在设置页自动检测或手动选择外接 Chromium 的 chrome.exe。"

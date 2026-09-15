# -*- coding: utf-8 -*-
# Shipment Track 一键打包脚本（Windows PowerShell）
# 1) PyArmor 混淆授权核心
# 2) PyInstaller 构建 onedir
# 3) 将默认 JSON 复制到 data 文件夹，并复制使用说明
# 使用系统已安装的 Edge/Chrome，不复制浏览器进安装目录。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist\Shipment Track"
$dataDir = Join-Path $dist "data"
$authObfuscated = Join-Path $PSScriptRoot "build\auth_obfuscated"
$authRuntime = Join-Path $PSScriptRoot "build\auth_runtime"
$authorizationPackage = Resolve-Path (Join-Path $PSScriptRoot "..\..\python_modules\authorization\authorization")

Write-Host "=== Step 1: obfuscate authorization core ==="
pyarmor gen -O $authObfuscated -r license.py $authorizationPackage
if ($LASTEXITCODE -ne 0) { throw "PyArmor authorization obfuscation failed." }
New-Item -ItemType Directory -Path $authRuntime -Force | Out-Null
Copy-Item (Join-Path $authObfuscated "pyarmor_runtime_000000") `
    -Destination $authRuntime -Recurse -Force

Write-Host "=== Step 2: PyInstaller build ==="
python -m PyInstaller ShipmentTrack.spec --noconfirm --clean

Write-Host "=== Step 3: copy data defaults & readme ==="
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot "filename_mappings.json") -Destination $dataDir -Force
Copy-Item (Join-Path $PSScriptRoot "delivery_status_mappings.json") -Destination $dataDir -Force
Copy-Item (Join-Path $PSScriptRoot "使用说明.txt") -Destination $dist -Force

Write-Host "=== Done ==="
Write-Host "输出目录: $dist"
Write-Host "启动: $dist\Shipment Track.exe"
Write-Host "首次运行请在设置页选择并检测已安装的 Edge 或 Google Chrome。"

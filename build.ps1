# -*- coding: utf-8 -*-
# Shipment Track 一键打包脚本（Windows PowerShell）
# 1) PyInstaller 构建 onedir
# 2) 把 Playwright Chromium 复制到 dist/Shipment Track/chrome/（不打包进 exe）
# 3) 构建 GetMachineId.exe（给同事查机器码用）
# 4) 复制 settings.json + 使用说明.txt 到输出目录

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 可靠获取 LocalAppData（后台进程下 $env:LOCALAPPDATA 可能为空）
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $localAppData) { $localAppData = "C:\Users\$env:USERNAME\AppData\Local" }

$dist = Join-Path $PSScriptRoot "dist\Shipment Track"

Write-Host "=== Step 1: PyInstaller build ==="
python -m PyInstaller ShipmentTrack.spec --noconfirm --clean

Write-Host "=== Step 2: copy chromium ==="
$chromeTarget = Join-Path $dist "chrome\chrome-win64"
New-Item -ItemType Directory -Force -Path $chromeTarget | Out-Null

$msPlaywright = Join-Path $localAppData "ms-playwright"
$chromeSrc = Get-ChildItem -Path $msPlaywright -Directory -Filter "chromium-*" |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $chromeSrc) {
    throw "找不到 Playwright Chromium: $msPlaywright"
}
$srcExe = Join-Path $chromeSrc.FullName "chrome-win64\chrome.exe"
if (-not (Test-Path $srcExe)) {
    throw "chrome.exe 不存在: $srcExe"
}

Write-Host "复制 Chromium: $($chromeSrc.FullName)\chrome-win64 -> $chromeTarget"
Copy-Item -Path (Join-Path $chromeSrc.FullName "chrome-win64\*") `
          -Destination $chromeTarget -Recurse -Force

Write-Host "=== Step 3: build GetMachineId.exe ==="
python -m PyInstaller --onefile --console --name GetMachineId `
    --distpath $dist --workpath (Join-Path $PSScriptRoot "build\gm") `
    --specpath (Join-Path $PSScriptRoot "build\gm") `
    (Join-Path $PSScriptRoot "machine_id.py") | Out-Null

Write-Host "=== Step 4: copy settings & readme ==="
Copy-Item (Join-Path $PSScriptRoot "settings.json") -Destination $dist -Force
Copy-Item (Join-Path $PSScriptRoot "使用说明.txt") -Destination $dist -Force

Write-Host "=== Done ==="
Write-Host "输出目录: $dist"
Write-Host "启动: $dist\Shipment Track.exe"

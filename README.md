# ShipmentTrack（快递批量查询 v0.6）

PySide6 中文工具：DHL / DSV / EI / UPS / FedEx 批量查状态（WorkTool 0.6
track 模块独立版）。输出 Excel 列：运单号/快递公司/状态/抵达时间/用时(秒)/备注。

## 运行（源码）
```
pip install PySide6 playwright pandas openpyxl requests pypdf pyinstaller
playwright install chromium
python main.py
```

## 打包（onedir，Chromium 不打包进 exe）
```
powershell -ExecutionPolicy Bypass -File build.ps1
# 1) PyInstaller ShipmentTrack.spec（onedir，collect_all playwright）
# 2) 复制 Chromium → dist\Shipment Track\chrome\chrome-win64
# 3) 生成 GetMachineId.exe / settings.json / 使用说明.txt
# 产物: dist\Shipment Track\Shipment Track.exe（整文件夹拷贝使用）
# 注意: build.ps1 必须保存为 UTF-8 with BOM（PS5.1 中文乱码问题）
```

## FedEx 逻辑（2026-09-02 修订）
- 先 trackingnumbers 正常查主单（非 MPS）——无子单运单以官网状态为准
- associatedshipments 探测子单：<40 全查，子单全 Delivered 才算送达
- 查到 40 条（可能隐藏子单）：40 条全 DL → 默认送达 + 备注"子单超过39需人工查询"
- POD（签名 PDF）：送达才下载，命名 = 主单号.pdf

## 授权
- 自动联网检查 MyWorkTool_License 仓库 ShipmentTrack_license.json
  （REFRESH_HOURS=0 每次启动检查；网络端关闭 → Unable to start 英文报错）
- 机器码：运行 GetMachineId.exe 获取，加到 GitHub JSON

## 目录
```
main.py / units.py / license.py / machine_id.py / ShipmentTrack.spec
modules/（tracking_utils/tracking_runner/fedex_module/dhl_module/...）
ui/ / assets/（app_icon.ico）
data/、settings.json（不入库，含 FedEx API 凭据）
```

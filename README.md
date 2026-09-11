# ShipmentTrack v0.7

PySide6 原生 Windows 工具，用于批量查询 DHL / DSV / EI / UPS / FedEx
运单状态、下载已送达货件的 POD，以及合并并核对检验表和 Droplist。

## 运行（源码）
```
pip install -r requirements.txt
playwright install chromium  # Chromium 外接，不进入程序安装包
python main.py
```

## 打包
```
powershell -ExecutionPolicy Bypass -File build.ps1
# 1) PyInstaller ShipmentTrack.spec（onedir，collect_all playwright）
# 2) 生成 GetMachineId.exe
# 3) 复制 filename_mappings.json / 使用说明.txt
# 产物: dist\Shipment Track\Shipment Track.exe（整文件夹拷贝使用）
# Chromium 由用户在设置页自动检测或手动选择 chrome.exe
# 注意: build.ps1 必须保存为 UTF-8 with BOM（PS5.1 中文乱码问题）
```

## 页面

- 跟踪：读取两列 Excel（快递公司、运单号），实时显示状态、抵达时间和备注。
- POD 抽查：风险件必查，其余成功 POD 随机抽查并输出 `pod_audit.xlsx`。
- Excel 合并与核对：合并检验表和 Droplist，按日期与类型比较数量。
- 设置：维护 FedEx API、EI 账号、默认路径、外接 Chromium 和文件名映射。

文件名映射由界面写入 `filename_mappings.json`。FedEx API Secret 和 EI 密码
使用当前 Windows 用户的 DPAPI 加密后写入设置文件。

## FedEx 逻辑（2026-09-02 修订）
- 先 trackingnumbers 正常查主单（非 MPS）——无子单运单以官网状态为准
- associatedshipments 返回 2–39 件时，所有可见关联单全部送达才算送达
- 返回达到 40 件时，40 件全部送达则暂定送达，并写入人工复核备注
- POD（签名 PDF）：送达才下载，命名 = 主单号.pdf

## 授权
- 自动联网检查 MyWorkTool_License 仓库 ShipmentTrack_license.json
  （REFRESH_HOURS=0 每次启动检查；网络端关闭 → Unable to start 英文报错）
- 机器码：运行 GetMachineId.exe 获取，加到 GitHub JSON

## 目录
```
main.py / units.py / license.py / machine_id.py / ShipmentTrack.spec
modules/（跟踪、设置、Excel 合并与核对）
ui/（PySide6 原生界面） / assets/（图标与本地头像）
filename_mappings.json（由设置页维护）
requirements.txt（经过打包验证的依赖版本）
```

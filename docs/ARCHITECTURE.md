# ShipmentTrack 架构

## 技术栈

- Python 3.12
- PySide6 Widgets 原生桌面界面
- requests：FedEx 官方 API
- Playwright：DHL、UPS、EI、DSV，驱动外接 Chromium
- openpyxl：跟踪结果、检验表和 Droplist
- pypdf：POD 抽查；FedEx 验证签名图，其他承运商验证送达字段
- PyInstaller：Windows onedir 打包
- cryptography：Ed25519 签名验证；PyArmor：打包时混淆授权核心

## 目录职责

```text
assets/     应用图标和本地作者头像
docs/       架构说明
modules/    承运商适配、跟踪流程、Excel 核对、设置和 POD 抽查
scripts/    可重复执行的资源生成脚本
tests/      离线单元测试、集成测试和打包配置测试
ui/         PySide6 原生界面、控件、样式和后台线程
```

根目录仅保留程序入口、授权、构建配置、依赖、用户说明和默认映射模板。
打包运行时的设置、映射、缓存和机器标识统一存放于 EXE 同级的 `data/`。

## 运行流程

1. `main.py` 创建应用并执行启动检查。
2. `ui/main_window.py` 提供跟踪、Excel 合并与核对、设置三个页面。
3. `modules/tracking_runner.py` 清洗运单、复用承运商会话并实时回传结果。
4. FedEx 调用官方 API；其他承运商由 `TrackingCarrierSession` 使用外接 Chromium。
5. 只有抵达货件允许下载 POD；只查状态模式不会下载 POD。
6. 所有承运商 POD 完成后随机抽查 5%。FedEx 检查签名，其他承运商检查送达
   字段，结果写入 `pod_audit.xlsx`。
7. 跟踪与 Excel 合并由两个独立 QThread 执行，输出路径也分别保存。

## 映射配置

- `data/filename_mappings.json`：检验表文件名关键字、详细类型及光联/MPO 归总类别。
- `data/delivery_status_mappings.json`：EI、DSV 的额外严格抵达状态。
- `data/settings.json`：界面设置；密码和 Secret 使用 Windows DPAPI 加密。
- `data/fedex_status_cache.json`：FedEx 状态缓存。
- `data/machine_id`、`data/authorization.cache`：机器标识与 DPAPI 授权缓存。

## Excel 输出

- 跟踪：`tracking_result.xlsx`、`tracking_list_cleaned_sorted.xlsx`、可选 `pod_audit.xlsx`。
- 合并：检验表与 Droplist 支持同时或单侧运行；`合并检验表.xlsx` 包含按原类型
  汇总箱数的 `类型箱数` Sheet，Droplist 单侧运行时汇总页写入 Droplist 文件。
- Droplist 明细页按业务表头识别，跳过首个汇总页、Address、Sheet1 和空表。
- 检验表详细类型不会被光联/MPO 覆盖；光联/MPO 只用于核对汇总。

## 打包

`build.ps1` 使用 `ShipmentTrack.spec` 构建。Playwright 驱动进入产物，Chromium 浏览器本体不进入产物，由设置页自动检测或手动指定。

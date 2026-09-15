# ShipmentTrack v1.2

PySide6 原生 Windows 工具，用于批量查询 DHL / DSV / EI / UPS / FedEx
运单状态、下载已送达货件的 POD，以及合并并核对检验表和 Droplist。

## 运行（源码）
```
pip install -r requirements.txt
python main.py
```

## 打包
```
powershell -ExecutionPolicy Bypass -File build.ps1
# 1) PyInstaller ShipmentTrack.spec（onedir，collect_all playwright）
# 2) 将两份默认映射 JSON 复制到 data / 复制使用说明.txt
# 产物: dist\Shipment Track\Shipment Track.exe（整文件夹拷贝使用）
# Edge / Google Chrome 由用户在设置页选择并自动检测
# 注意: build.ps1 必须保存为 UTF-8 with BOM（PS5.1 中文乱码问题）
```

## 页面

- 跟踪：读取两列 Excel（快递公司、运单号），实时显示状态、抵达时间和备注。
- POD 抽查：设置页可为 FedEx、DHL、UPS、EI、DSV 分别设置 0%–100%。
  FedEx 抽中一票时检查查询主页和详情页；所有承运商统一检查 PDF 有效性、
  运单号和送达状态，不再检查签名。结果写入 `pod_audit.xlsx`。
- Excel 合并与核对：检验表和 Droplist 可同时处理，也可任选一侧单独合并；
  对应输出 `合并检验表.xlsx` 或 `合并Droplist.xlsx`。
  已选一侧会生成对应文件，界面未选侧保持空白。两侧都有数据时按日期与
  光联/MPO 归总类别比较数量。检验表明细仍保留澳车、港车、814S 等原类型，
  `类型箱数` Sheet 另行汇总每天各原类型的箱数。
- 设置：维护 FedEx API、EI 账号、默认路径、实际浏览器和文件名映射。
- 送达状态：可为 DHL、EI、DSV 添加额外状态，仅与当前状态完整匹配。
- 更新：启动后从 GitHub 静默检查新版本；头像弹窗可查看更新日志或手动检查。

界面中的 POD 绿色圆点、查询结果、清洗文件、POD 抽查和两份合并 Excel
均可直接点击打开。

跟踪与 Excel 合并使用独立后台任务，可以同时运行；两页各自保存输出路径，
切换页面或完成另一项任务不会清除已经生成的文件按钮。

文件名映射由界面写入 `data/filename_mappings.json`。每条规则保存文件名关键字、
检验表原类型和用于核对的归总类别；归总类别只允许光联或 MPO。FedEx API
Secret 和 EI 密码使用当前 Windows 用户的 DPAPI 加密后写入设置文件。

## FedEx 逻辑（2026-09-14 修订）
- 先 trackingnumbers 正常查主单（非 MPS）——无子单运单以官网状态为准
- associatedshipments 返回 2–39 件时，所有可见关联单全部送达才算送达
- 返回达到 40 件时，40 件全部送达则暂定送达，并写入人工复核备注
- API 只负责快速查询状态，不再请求官方 POD 文档接口
- 只有送达后才启动系统安装的真实 Microsoft Edge，并复用 `data/fedex_edge_profile`
- 自动查询官网后保存两份网页 PDF：`运单号.pdf` 为查询主页，
  `运单号+.pdf` 为点击“查看更多详细信息”后的详情页
- 网页 POD 固定使用英文站；打印前自动关闭 Cookie 和聊天浮层
- Edge 首次启动预热 30 秒，供公司电脑完成账号登录；登录状态保存到持久化配置
- 界面中的同一个绿色 POD 圆点会依次打开这两份文件

## Droplist 识别
- 日期优先从文件名读取，文件名没有日期时读取父文件夹（如 `9.10`）
- 明细页按第 3 行的 `S/O` 与 `QTY` 表头识别，不要求页签名包含日期或类型
- 首个汇总页、`Address`、默认 `Sheet1` 和空表不计入合并数量

## 授权
- 使用 Ed25519 公钥验证 GitHub 共享授权文件，GitHub 中保存机器码摘要和开关。
- 在线关闭授权后，下次联网启动即生效；断网只允许使用最近一次成功验证后的
  24 小时缓存，不再使用本地截止日期授权。
- 授权失败统一显示普通服务错误；授权核心在正式打包时由 PyArmor 混淆。
- 管理员操作见 `docs/AUTHORIZATION.md`。

## 目录
```
main.py / units.py / license.py / ShipmentTrack.spec
modules/（跟踪、设置、Excel 合并与核对）
ui/（PySide6 原生界面） / assets/（图标与本地头像）
docs/ARCHITECTURE.md（框架与目录职责）
E:/python_modules/authorization（共享授权与机器码包）
data/filename_mappings.json（由设置页维护）
data/delivery_status_mappings.json（DHL/EI/DSV 额外抵达状态）
data/settings.json（界面设置，首次保存后生成）
requirements.txt（经过打包验证的依赖版本）
```

## 1.1 浏览器与更新

- DHL、UPS、EI、DSV 使用电脑已安装的 Microsoft Edge 或 Google Chrome，
  不再依赖 Playwright 下载的模拟 Chromium 浏览器。
- DSV 详情页依次尝试实际结果链接、文字元素和结果卡片位置点击。
- DHL 的 Delivered 只允许来自当前状态区域，历史事件全文不再确认送达。
- 设置页可直接验证 FedEx API；OAuth token 按 API 凭据隔离。
- 更新文件从 GitHub 下载后必须通过 SHA-256 校验，程序退出后再安全替换 EXE。

## 1.2 POD 抽查

- 设置中的五个比例互相独立，0% 表示不抽查，100% 表示全部抽查。
- 抽查表字段为运单号、承运商、POD 类型、抽查比例、查询状态、POD 文件、
  PDF 有效、运单号匹配、PDF 提取状态、送达状态匹配、结果和说明。

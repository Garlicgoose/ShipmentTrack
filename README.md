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
powershell -ExecutionPolicy Bypass -File build.ps1 -DistRoot E:\ShipmentTrackBuild
# 1) PyInstaller ShipmentTrack.spec（onedir，collect_all playwright）
# 2) 将两份默认映射 JSON 复制到 data / 复制使用说明.txt
# 产物: 指定目录\Shipment Track\Shipment Track.exe（整文件夹拷贝使用）
# Edge / Google Chrome 由用户在设置页选择并自动检测
# 注意: build.ps1 必须保存为 UTF-8 with BOM（PS5.1 中文乱码问题）
# 旧 dist/data 有设置或授权缓存时构建会拒绝覆盖，务必指定独立空目录
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
- 设置分四个标签页：连接与路径（FedEx API、EI 账号、默认路径、实际浏览器）、映射
  （文件名映射）、货代抵达状态（可为 DHL、EI、DSV 添加额外状态，仅与当前状态完整
  匹配）、POD 抽查比例（五个承运商各自填写 0–100 的整数）。
- 官网语言：DHL（hk-en）、UPS（loc=en_US）由 URL 决定；DSV、EI 没有语言参数，
  程序把浏览器 Accept-Language 与 navigator.language 锁成 en-US，页面若仍为中文
  再兜底点击站点自带的 English 选项，保证状态文案与英文选择器一致。
- FedEx 网页 POD：批量任务只查 API 状态，不自动下载。完成后在跟踪页打开
  「FedEx 半自动 POD」；程序只打开空白浏览器，由用户自行进入 FedEx 网站。
  点击 Tracking ID 输入框后程序逐字填号；用户自行点击 TRACK 和详情，
  程序识别页面并保存两份 PDF。置顶面板不随主窗口最小化。
- 映射设置提供包含/完全/正则匹配方式、真实文件名预览和推荐规则补充；
  使用说明见 `docs/FILENAME_MAPPING_GUIDE.md`。
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
- 在半自动面板中由用户提交查询、打开详情后，程序保存两份网页 PDF：
  `运单号.pdf` 为查询主页，`运单号+.pdf` 为详情页
- 网页 POD 固定使用英文站；打印前自动关闭 Cookie 和聊天浮层
- FedEx 半自动面板独立于其他承运商的 10 秒登录等待；可在浏览器中完成公司登录
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

## 合并异常处理

- 检验表原始列宽不一致时，按最大列数保留所有源列，再追加类型、日期等映射字段。
- 缺失文件不会被虚构；异常文件页会列出缺失的日期/类别和无法匹配的文件。
- 以 2026-09-21 附件复核：9.19 光联加入 Expeditors 映射后两侧均为 1,917；
  9.18 MPO 缺检验表源文件，9.17 MPO 差 98，9.19 MPO 差 355，仍需核源。

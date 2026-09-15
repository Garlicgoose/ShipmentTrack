# ShipmentTrack 更新日志

## 1.2 - 2026-09-15

- FedEx、DHL、UPS、EI、DSV 可以分别设置 0% 至 100% 的 POD 抽查比例。
- FedEx 抽中一票时仍检查查询主页和详情页两份文件。
- POD 抽查统一检查 PDF 有效性、运单号和送达状态，不再检查 FedEx 签名。
- `pod_audit.xlsx` 删除“FedEx签收人字段”，增加“POD类型”和“抽查比例”。

## 1.1 - 2026-09-15

- 修复更换或重新填写 FedEx API 凭据后可能复用旧 token 的问题，并增加 API 验证按钮。
- DHL 只从当前状态区域判断送达，历史时间线不再导致误下载 POD。
- DHL、EI、DSV 均可在设置中维护额外的严格送达状态。
- DSV 详情页支持结果链接、文字元素和结果卡片位置三重进入方式。
- DHL、UPS、EI、DSV 改为驱动电脑已安装的 Microsoft Edge 或 Google Chrome。
- 新增 GitHub 版本检测、SHA-256 下载校验、自动替换和程序内更新日志。

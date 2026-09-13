# 共享程序授权管理

## 当前已经生成的文件

管理员目录位于：

`C:\Users\admin\Documents\Shared-App-License-Admin`

- `ed25519-private.key`：签名私钥。只保存在管理员电脑和离线备份中，禁止上传、
  禁止放入项目、禁止交给使用者。
- `ed25519-public.key`：验证公钥。已经嵌入 ShipmentTrack，以后其他程序复用它。
- `machines.json`：管理员编辑的机器开关源文件，可填写原始机器码及 true/false。
- `authorization.json`：签名后的公开文件，需要上传到 GitHub。

## 首次启用（必须先完成）

将管理员目录中的 `authorization.json` 上传并覆盖：

`MyWorkTool_License/main/ShipmentTrack_license.json`

新版本不再接受旧的简单机器码 JSON。在 GitHub 文件替换为签名格式之前，
新版本会显示普通的服务不可用提示并拒绝启动。

## 日常增加、关闭机器

1. 编辑管理员目录的 `machines.json`：需要使用设为 `true`，关闭设为 `false`。
2. 每次发布把 `--revision` 增加 1，运行：

```powershell
authorization-admin sign `
  --private C:\Users\admin\Documents\Shared-App-License-Admin\ed25519-private.key `
  --machines C:\Users\admin\Documents\Shared-App-License-Admin\machines.json `
  --output C:\Users\admin\Documents\Shared-App-License-Admin\authorization.json `
  --revision 2
```

3. 将新的 `authorization.json` 覆盖上传到同一个 GitHub 文件。

GitHub 中只出现机器码的 SHA-256 摘要，不再公开原始机器码。联网设备在下次
启动时会立即读取关闭状态；断网设备最多可继续使用上次成功验证后的 24 小时。
这是“一天离线有效”与“立即撤权”之间不可避免的边界。

## 迁移到其他程序

先安装共享包，再为新程序写一个类似 `license.py` 的薄适配层：

```powershell
python -m pip install -e E:\python_modules\authorization
```

共享包自身的完整说明位于 `E:\python_modules\authorization\README.md`。新程序复用：

- 同一个 GitHub 签名文件 URL；
- 同一个 `PUBLIC_KEY_B64`；
- 同级共享 `data/authorization.cache` 和 `data/machine_id`；
- 独立的 `app_id`，只用于请求标识，不改变全局机器开关。

所有程序放在同一工具目录时，推荐结构：

```text
MyWorkTools\
├── Shipment Track.exe
├── Other Tool.exe
├── data\
│   ├── machine_id
│   └── authorization.cache
└── _internal\
```

不要把不同 PyInstaller onedir 包里的 `_internal` 目录直接相互覆盖；多个程序
合并到一个目录时，需要使用统一依赖版本和统一 spec 构建。`GetMachineId.exe`
只需单独制作、放一份，不应进入每个业务程序的打包脚本。

## 安全边界

- Ed25519 能证明 GitHub 内容确实由管理员私钥签发，修改机器开关后伪造旧签名
  会验证失败。
- 本地缓存通过 Windows DPAPI 绑定当前用户，并再次校验签名、机器摘要、系统
  时钟回拨和 24 小时期限。
- 启动、进入主窗口、执行两个核心工作流前都有独立检查点。
- PyArmor 只混淆授权核心，提高修改门槛；客户端软件无法做到绝对防破解。
- 当前电脑是 PyArmor trial/non-profits 授权。若用于商业分发，必须先按 PyArmor
  的许可条款购买并激活合适许可证，再构建正式发布包。

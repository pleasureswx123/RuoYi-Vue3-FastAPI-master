# Windows 桌面端 0.1.1 一键打开 NAS 验收记录

2026-11-18，在 Windows x64 工作站上升级安装 Shot Grid 0.1.1 后，使用卢清华账号实测。从「文件与 NAS」点击一次「在文件资源管理器中打开」，Windows 资源管理器即显示所选文件的父目录，全程只点击了一次打开按钮。

## 实机验收

1. 在已安装客户端进入「罗刹夫人」项目，选择镜头版本文件 `LCFR_EP000_001_0360_JH_V002_01.mov`。
2. 点击打开按钮后，正式服务返回已授权的 NAS 目录。通过 Windows Shell 读取实际打开的资源管理器窗口地址，与服务返回值逐项核对，二者一致。目录以 `VIDEO\EP00\001_0360` 结尾，文件列表中存在所选 MOV 文件。
3. 核对 Windows 安装记录中的版本为 `0.1.1`，安装目录下 `tools/ShotGridNas.exe` 的 SHA-256 与构建产物一致。本轮在正式服务上仅验证登录和只读打开目录。

## 构建与回归证据

| 验证 | 执行结果 |
| --- | --- |
| `npm.cmd run build:desktop` | 成功生成 Windows x64 NSIS 安装包。本次实测包的 SHA-256 为 `49AC2876DC8515756B445A297F1230421EB52FB49E410319C07F1256743A04EF`。 |
| `npm.cmd test -- --maxWorkers=1 nasFolderMenu.spec.js nasExplorer.spec.js nasOpenButton.spec.js` | 3 个测试文件、35 项测试全部通过。 |
| `powershell.exe -NoProfile -NonInteractive -File shot-grid-frontend/tests/Test-NasProtocol.ps1` | 签名、公钥不匹配、篡改、过期和重放等检查通过。中文目录往返、18 个非法路径和 7 个非法协议输入均符合预期。 |

前两条命令在 `shot-grid-frontend` 目录执行，最后一条在仓库根目录执行。本记录覆盖 0.1.1 的 NAS 打开功能；提交、审核、FINAL 交付和撤销属于此前桌面端的独立验收范围。

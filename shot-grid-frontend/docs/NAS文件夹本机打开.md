# NAS 文件夹本机打开

## 用户操作

镜头列表或资产制作分项行右键 → 在文件资源管理器中打开。单目录直接唤起工具，不再先弹网页安装框或本机目录确认；多个目录才选择。浏览器自身的首次外部协议提示仍需用户允许，不修改浏览器安全设置。

正常发起打开后不显示浮动提示，也不推断安装状态或打开成功。右键菜单保留“安装／打开帮助”，只读取目录并展示安装／更新、重新打开和复制目录入口，不自动唤起工具。获取目录或签名失败时显示错误及帮助。这里打开版本成果所在目录，不是 FINAL 交付目录，也不会创建目录。

首次使用或更新：点击帮助中的安装／更新工具，下载已经绑定服务器公钥的脚本。在下载目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-ShotGridNas.ps1
```

工具安装到当前用户 `%USERPROFILE%\.shotgrid-nas`，注册 `HKCU\Software\Classes\shotgrid-nas`，无需管理员权限、不常驻。脚本使用 Windows PowerShell 5.1/.NET Framework 编译；只改变本次进程执行策略。安装目录使用用户主目录，避免打包桌面应用的 LocalAppData 文件虚拟化导致更新不生效。升级识别原 `%LOCALAPPDATA%\ShotGridNas` 注册路径；不覆盖其他程序的同名协议。

返回页面重试即可。访问 NAS 使用自己的 Windows 账号权限，安装不能绕过共享 ACL。断网、目录不存在或无权限时工具提示失败。

卸载使用同一脚本加 `-Uninstall`；只删除本工具注册项和 EXE，保留短期重放缓存，不递归删除其他文件。

## 服务端准备与密钥轮换

本功能新增两个鉴权 API，无数据库迁移。服务端需配置 `SHOT_GRID_NAS_SIGNING_KEY_FILE` 指向专用 RSA PEM 私钥（至少2048位）。不要复用 JWT Secret、传输密钥，不把私钥提交仓库或放入前端。未配置时返回503，复制目录仍可用。

生产部署时由运维在仓库外生成密钥，以只读文件挂载到后端，进程环境配置上述绝对路径；文件权限仅应用身份可读。多 Worker/多实例必须共享同一个受控密钥文件。首次安装工具从已鉴权页面获取公钥并固定编译进 EXE，协议请求不能指定公钥或验证服务器地址。

当前生产 Compose 将宿主机 `/etc/ruoyi-shot-grid/nas-opener`（可由 `SHOT_GRID_NAS_SIGNING_HOST_DIR` 指定）只读挂载到 `/run/shot-grid-nas`，固定读取 `signing.pem`。首次部署前在服务器生成独立 RSA 私钥，目录设置 `root:101`、`0750`，私钥设置 `root:101`、`0440`；不得覆盖已有密钥或复制开发私钥。部署脚本会以应用身份执行签名/验签预检，失败则不切换版本。此目录应纳入服务器受限备份，恢复时保持原密钥，以免所有本机工具需要重装。

密钥轮换：替换服务端密钥后旧工具将拒绝新签名，需从页面下载更新工具；不自动信任新公钥。当前只支持一个受信任签名环境。正式部署后本机验收工具也要换成正式环境公钥版本。已签发凭证最多60秒可用，离线验证不能即时撤销，重放防护只针对同一 Windows 用户/本机。

内部 HTTP 沿用项目已确认的可信内网边界，无法防止网络攻击者替换首次下载的脚本/公钥；生产分发应由 IT 审核或可信渠道分发，不能称为 HTTPS 或代码签名保障。不要关闭安全软件或组策略。

## API 与安全边界

- `POST /shot-grid/versions/{version_id}/nas-open-ticket`：`{projectId, taskId, fileId}`。先认证与 `shotgrid:version:query`，再复用版本详情的项目/任务数据范围；只能签发此版本真实文件的父目录，排除 thumbnail/proxy_media。返回 `{folder, uri, expiresIn: 60}`，禁止缓存。
- `GET /shot-grid/nas-opener/public-key`：同样需要认证与查询权限，仅返回公钥 XML。静态脚本是未绑定公钥的模板，直接执行会失败关闭。
- 固定协议 `shotgrid-nas://open-v1/<Base64URL payload>.<Base64URL RSA signature>`。payload 为严格 UTF-8 的五行：用途 SGNAS1、Unix签发秒、Unix过期秒、32位十六进制nonce、精确目录。使用 RSA PKCS1v15/SHA256，60秒有效期，签发时间最多超前本机5秒。每次重试重新获取凭证，不复用过期凭证。
- 前端/后端/本机独立限定 `\\192.168.10.64\共享\子目录`；拒绝其他服务器、本地磁盘、设备路径、管理共享、共享根、空段、点段、控制字符、尾随点/空格、引号、冒号、通配符、百分号、DOS保留名称。限制路径长度2000字符，协议14000字符。
- 工具先验签与时间/用途/路径，再以原子文件创建消费nonce，之后确认目标是目录。只调用固定 Windows explorer.exe，不通过 cmd/PowerShell 拼接业务命令，不打开或执行文件。
- 无效签名不能触发 NAS 访问；原无签名协议被拒绝。任意网站不能自行生成合法凭证。平台授权不代替 NAS ACL，也不能阻止用户手工输入 UNC。

## 验证

```powershell
# 后端目录
.\.venv\Scripts\python.exe -m pytest -q tests/module_shot_grid/test_nas_opener_service.py
# 前端目录
npm.cmd exec -- vitest run tests/unit/nasExplorer.spec.js tests/unit/nasFolderMenu.spec.js
powershell.exe -NoProfile -File tests/Test-NasProtocol.ps1
```

定向检查覆盖路径、签名、过期、未来时间、用途、篡改、错误公钥、重复消费、文件归属、权限拒绝传播、多目录选择、迟到结果隔离和错误回退。原生测试只在临时目录测试nonce，不访问NAS。

2026-10-26 本机真实验证：Chrome → 本地5175新前端 → 本机临时签名验收服务 → 内网鉴权只读版本详情 → 已升级工具 → 资源管理器。镜头项目6 `EP001/001/0050` 打开6个MOV文件；资产项目7“主家杯子”制作分项打开对应PNG。均无工具目录确认；复制目录反馈和绑定公钥安装下载已验证。

本机临时验收服务仅用于不部署情况下读取真实目录，没有修改生产业务数据。生产新接口尚未部署，不能视为生产中间件/数据库完整E2E。其他电脑、Edge、真实卸载后首次安装、断网/无NAS权限手工流程尚未验收。

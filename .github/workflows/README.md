# GitHub 自动检查说明

推送到 main 或提交面向 main 的合并申请时，运行以下检查：

| 配置 | 检查内容 |
| --- | --- |
| frontend.yml | 两端依赖安全、制作端 lint/组件测试、两端构建、部署脚本控制流 |
| backend.yml | Python 3.11/3.12/3.13 后端测试，以及生产依赖锁文件安全审计 |
| ruff.yml | 使用固定 Ruff 版本检查 Python 代码和格式 |
| playwright.yml | 独立 PostgreSQL/Redis、真实后端与管理端浏览器测试 |

同分支新提交取消旧的检查运行，避免重复占用机器。取消不是通过；以最新提交完成的结果为准。后端普通测试明确不连接真实 PostgreSQL 集成库，跳过用例不能视为通过；真实数据库迁移和 NAS 另按隔离验收流程执行。

浏览器测试只使用本轮临时库，不连接公司服务器；使用生产 Dockerfile，明确数据库类型，不读取开发机配置。失败结果可在 Actions 对应运行页的 artifacts 下载。详见 [浏览器测试说明](../../ruoyi-fastapi-test/README.md)。

## 生产部署

`deploy-intranet.yml` 只允许手动触发，在公司内网带 ruoyi-prod 标签的 Runner 上执行，并使用 intranet-production Environment。普通 push 不触发部署。正式部署的停写、备份、迁移和健康门禁不因测试缓存或取消规则而绕过；部署自身使用独立互斥配置，不取消正在运行的发布。

不要为消除红色状态删除有效断言、隐藏测试失败，或让测试访问生产数据库/NAS。构建、单元测试、浏览器测试分别提供不同证据，不能相互替代。

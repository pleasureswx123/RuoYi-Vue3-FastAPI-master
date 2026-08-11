# Shot Grid 真实基础设施验收套件

该目录复用仓库既有的 `pytest`、`pytest-asyncio` 与 Playwright。测试只面向真实 PostgreSQL、Redis、前后端和 SMB/NAS；不会提供 Mock NAS 降级路径。未设置 `SHOT_GRID_E2E_ENABLED=1` 时，所有 `shot_grid_e2e` 用例会显示明确跳过原因。

## 验收账号与环境

测试环境须预置四个互不相同且已授予对应平台权限的账号：平台管理员、项目总监、制作人员、非项目成员。凭据只通过环境变量传入：

```bash
export SHOT_GRID_E2E_ENABLED=1
export SHOT_GRID_FRONTEND_URL=https://shot-grid.example.test
export SHOT_GRID_BACKEND_URL=https://shot-grid-api.example.test
export SHOT_GRID_E2E_NAS_ROOT_ID=1
export SHOT_GRID_E2E_NAS_MOUNT_PATH=/mnt/shot-grid-acceptance
export SHOT_GRID_E2E_SAMPLE_DIR=/opt/shot-grid-samples
export SHOT_GRID_E2E_ACCOUNTS='{
  "admin":{"username":"sg_admin","password":"...","userId":101},
  "director":{"username":"sg_director","password":"...","userId":102},
  "producer":{"username":"sg_producer","password":"...","userId":103},
  "outsider":{"username":"sg_outsider","password":"...","userId":104}
}'
python -m pytest -v -m shot_grid_e2e shot_grid
```

样本目录至少包含经过 `ffprobe`/图片解码器核验的 `shot-v001.mp4`、`asset-v001.png`、`shots.xlsx` 和 `assets.xlsx`。负向文件门禁另读取 `wrong_mime.bin`、`forged.jpg`、`oversized.bin`。NAS 根必须是后端白名单中健康的真实根，并以只读方式挂载到测试 Runner，以便独立核对物理目录。

`SHOT_GRID_E2E_FAULT_CONTROLLER_URL` 是受控验收环境的故障编排器，不是应用 Mock：它应真实断开 NAS、令发布失败或在测试数据库触发提交失败，并负责恢复。没有该能力时相关用例会单独跳过，不能据此宣称故障恢复验收通过。

## 发布门禁边界

每条浏览器流程最后均回到 API 查询持久化结果；API 并发/幂等测试也会再次读取项目、导入批次、任务或版本。页面成功提示、构建成功和健康检查均不视为 E2E 通过。正式发布工作流 `.github/workflows/shot-grid-e2e.yml` 只允许显式手动/被调用启动，并在运行 pytest 前检查全部基础设施配置。

# 前端 Codex 协作指南

## 1. 适用范围

本文件适用于 `ruoyi-fastapi-frontend/` 及其所有子目录，并补充仓库根目录的 `AGENTS.md`。根目录规则仍然有效；涉及前端代码时，还必须遵循本文件。

## 2. 前端定位

前端是 Vue 3 管理端，不是静态菜单应用。页面访问能力由以下链路共同决定：

```text
登录
  → 保存JWT
  → /getInfo获取角色和权限
  → /getRouters获取后端菜单
  → 转换组件路径
  → 动态注册Vue Router路由
  → 生成侧边栏和顶部导航
```

前端负责用户体验和客户端防护，但后端始终是认证、接口权限和数据权限的最终裁决方。

## 3. 目录职责

```text
src/main.js                 应用装配和全局组件
src/App.vue                 根组件
src/permission.js           全局路由守卫
src/router/                 常量路由和本地动态路由
src/store/                  Pinia状态
src/api/                    HTTP API封装
src/utils/request.js        Axios实例和拦截器
src/utils/transportCrypto.js 传输加密
src/views/                  平台页面
src/components/             通用组件
src/directive/              权限等指令
src/plugins/                前端通用插件
plugins/<id>/               可安装业务插件前端源码
vite/plugins/               Vite插件配置
tests/plugins/              插件解析单测
bin/                        Nginx和Windows脚本
```

不要手工修改：

- `node_modules/`
- `dist/`
- Vite 临时缓存

## 4. 应用装配

全局能力在 `src/main.js` 注册，包括：

- Router；
- Pinia；
- Element Plus；
- 权限指令；
- 下载、字典和工具方法；
- 文件、图片、分页、编辑器等公共组件。

新增全局组件或全局属性前先判断是否真的需要全局注册。仅单个业务页面使用的组件应局部导入，避免扩大首屏依赖和命名冲突。

## 5. 路由和权限

### 5.1 路由分类

- `constantRoutes`：登录、错误页、首页、个人中心等固定路由。
- `dynamicRoutes`：前端定义但按权限过滤的辅助页面。
- 后端菜单路由：由 `/getRouters` 返回并在运行时注册。

新增普通菜单页面时，应优先走后端菜单配置，不要直接塞入 `constantRoutes` 绕过权限系统。

### 5.2 动态组件解析

内置页面通过：

```javascript
import.meta.glob('./../../views/**/*.vue')
```

插件页面通过：

```javascript
import.meta.glob('./../../../plugins/*/views/**/*.vue')
```

后端 `component` 字段必须与文件路径一致：

- 内置页面：如 `system/user/index`
- 插件页面：如 `plugin/ai/model/index`
- 特殊组件：`Layout`、`ParentView`、`InnerLink`

组件不存在时不能静默显示空白页；插件路径应落到明确的 404，并保留诊断日志。

### 5.3 权限使用

- 页面权限由动态路由控制。
- 按钮权限使用现有权限指令或 `auth` 插件。
- 前端权限只控制展示，不能替代后端鉴权。
- 权限码必须与后端 Controller 和 SQL/插件菜单声明完全一致。

修改菜单、路由名称或组件路径时，同时检查：

- `/getRouters` 返回结构；
- `permission.js` 路由守卫；
- Permission Store；
- 面包屑、缓存和页面 `name`；
- 插件路径解析；
- 404 行为。

## 6. 状态管理

- 使用现有 Pinia Store，不要创建重复的全局状态源。
- Token 通过 `utils/auth` 管理。
- 用户、角色、权限由 User Store 维护。
- 动态路由由 Permission Store 维护。
- 锁屏状态由 Lock Store 维护。
- 退出登录时必须清理 Token、角色、权限和相关临时状态。
- 不要把密码、API Key、私钥或完整敏感响应存入 localStorage/sessionStorage。

如果接口缓存或会话缓存存入浏览器，需要明确生命周期和退出清理行为。

## 7. HTTP 请求

所有业务请求统一通过：

```text
src/utils/request.js
```

不得另建裸 Axios 实例绕过：

- Bearer Token；
- 请求加密；
- 响应解密；
- 密钥失效重试；
- 统一业务状态码；
- 登录过期处理；
- 重复提交保护；
- 下载错误处理。

新增 API 文件放在 `src/api/` 或对应插件的 `api/` 中。页面组件不要散落硬编码 URL。

注意：

- GET 参数在拦截器中序列化。
- POST/PUT 默认启用重复提交保护。
- 下载接口通常关闭传输加密并使用 Blob。
- 自定义超时必须基于业务需要，不能用超长超时掩盖后端无响应。
- 401 处理必须避免重复弹窗和重复登出。

## 8. 传输加密

前端会从后端获取：

- 运行策略；
- 当前 `kid`；
- RSA 公钥；
- 缓存 TTL；
- 必须加密和排除路径；
- GET URL 最大长度。

规则：

- 不在前端保存或引入私钥。
- 加密必须发生在 GET 查询参数写入 URL 之前。
- 密钥失效只允许按现有逻辑刷新并重试一次，避免无限循环。
- `required` 路径不能因加密失败自动降级成明文。
- 上传、下载等排除路径遵循后端公开策略。
- 修改信封、AAD、nonce、时间戳或算法字段时，必须与后端中间件同步。

## 9. 页面和组件

- 优先复用现有分页、表格工具栏、字典标签、编辑器、上传和预览组件。
- 表单提交前使用现有校验规则，不只依赖后端报错。
- 列表页保持查询、重置、分页、增删改查和权限按钮的一致交互。
- 异步操作必须提供加载态，并在成功或失败后正确恢复。
- 不使用仅靠颜色表达状态的设计。
- 用户可见文案、校验提示和注释以中文为主。
- 不在模板中复制大段复杂业务表达式；抽到 `computed` 或具名函数。

### 9.1 表格组件契约

- 行列数据使用 `ElTable` / `ElTableColumn`，单对象的键值信息优先使用 `ElDescriptions` / `ElDescriptionsItem`。不得用原生 `table` 或套用 `el-table` 内部 CSS 类来模拟组件。
- 表格必须绑定真实 `data`，列按实际字段设置 `prop` / `label` 或作用域插槽。新增和本次改造的业务表格统一提供稳定业务 `row-key`，不得使用数组序号；官方在树形数据和保留选择场景要求 `row-key`，普通历史表缺少它应区分为一致性改善项。
- 多选使用 `type="selection"` 列、`selection-change` 和按需配置的 `selectable`；程序回显或清除选择使用表格实例 API。不得通过普通列中的自制 Checkbox、独立全选逻辑和手写选中样式绕过 Table 选择模型。需要跨页保留时同时配置稳定 `row-key` 和 `reserve-selection`，并明确筛选切换时的清理规则。
- 树形数据通过 `children` / `tree-props`、展开键和 `expand-change` 表达层级；懒加载按 `lazy` / `load` 契约实现，不得用手工展开行替代已有树表能力。
- 按实际场景落实 loading、空态、错误与重试、排序、分页和禁用状态；分页与筛选刷新不得保留失效的业务选择。无排序、分页或选择需求的只读表格不必虚构相应交互。
- 长文本、最小列宽、溢出提示和横向滚动交由 Table 对应 API 处理；不要依赖内部 DOM 结构或高权重 CSS 重建表头、滚动条及选中行为。
- 验收检查最终组件层级、数据绑定及直接相关行为，不以标签替换、构建或页面可打开代替交互证据。组件数据契约测试不能描述为完整浏览器 E2E。
- 当前 Element Plus 2.14.3 的描述单元格默认跨度在本次真实组件验证中出现无效属性；本次监控页显式提供合法 `span` / `rowspan`，后续升级需通过真实组件渲染验证后再移除兼容配置，不修改依赖源码。

API 依据：[Table 官方文档](https://element-plus.org/zh-CN/component/table.html)、[Descriptions 官方文档](https://element-plus.org/zh-CN/component/descriptions.html)，同时核对当前安装版本的 API。

## 10. 文件上传与下载

### 10.1 组件选择

- 公开图片：`ImageUpload`
- 旧业务公开附件：`FileUpload`
- 简单私有附件：`FileUpload :is-private="true"`
- 正式业务附件：`BusinessFileUpload`

正式业务附件的模型必须保持：

```javascript
[
  {
    fileId: '...',
    name: '...',
    url: '...'
  }
]
```

- 不要从 URL 反向截取 `fileId`。
- 业务保存时提交修改后的完整文件 ID 列表。
- 受保护文件使用现有鉴权下载方法，不使用普通 `<a>` 直接访问。
- 不破坏 Range 分段下载和失败续传逻辑。
- 文件删除成功前不要先从业务模型永久移除，失败时应保留可重试状态。

## 11. 插件前端

插件代码位于：

```text
plugins/<plugin-id>/
```

插件修改应与后端 `plugin.yaml` 同步：

- `frontend.basePath`
- `frontend.pluginId`
- `frontend.viewsPath`
- `frontend.apiPath`
- 菜单 `component`
- `routeName`
- 权限码
- npm/npmDev 依赖

规则：

- 插件页面不能静态硬编码到平台主路由中。
- 插件停用或缺失时应提供明确的不可用/404 行为。
- 公共平台组件可复用，但不要让平台核心代码反向依赖某个具体插件。
- 修改插件路径解析后必须运行 `test:plugin`。

## 12. 样式与 UI 库

项目同时包含 Element Plus 和部分 Ant Design Vue 能力。

- 现有平台管理页面优先保持 Element Plus 风格。
- 不要在同一个简单页面无必要地混用两套组件库。
- 公共样式放入现有样式体系；局部页面优先使用 scoped 样式。
- 避免通过高权重全局选择器覆盖第三方组件。
- 深色模式下检查文字、边框、表格和弹窗可读性。
- 响应式变更至少检查常用桌面宽度和较窄窗口。

## 13. 性能和构建

当前生产构建包含 Monaco、Shiki、Mermaid、KaTeX、AI Markdown 等重型依赖，产物和部分 Chunk 较大。

- 重型能力优先通过动态 import 按页面加载。
- 不要把所有语言高亮包、主题或 Monaco Worker 引入普通管理页。
- 使用 `manualChunks` 前先确认不会破坏插件动态加载。
- 不要仅提高 `chunkSizeWarningLimit` 来隐藏警告。
- 不要无理由开启 source map 到生产环境。
- 图片、字体和大型静态资源应评估缓存和体积。

生产构建：

```powershell
npm.cmd run build:prod
```

构建成功只证明可打包，不证明登录、权限、API 和浏览器流程正确。

## 14. 依赖管理

- 当前项目使用 npm。
- 不要无说明地切换 pnpm/yarn。
- `package-lock.json` 当前被 `.gitignore` 排除，依赖并未形成可提交的可复现锁定。
- 涉及依赖新增或升级时，应明确记录：
  - 变更原因；
  - 版本范围；
  - 生产包或开发包；
  - 包体影响；
  - 浏览器兼容性；
  - 是否需要后端插件清单同步。
- Docker 当前使用 `npm install`；未修复锁文件策略前，不得声称 Docker 构建完全可复现。
- 不直接编辑 `node_modules` 解决问题。

## 15. 环境和代理

环境文件：

- `.env.development`：`/dev-api`
- `.env.production`：`/prod-api`
- `.env.staging`：`/stage-api`
- `.env.docker`：`/docker-api`

修改 API 前缀时同步检查：

- Vite 开发代理；
- Nginx Docker 配置；
- 后端 `APP_ROOT_PATH`；
- Swagger/ReDoc 路径；
- 传输加密路径匹配。

不得把后端密钥或 Provider Key放进 `VITE_*`；所有 Vite 环境变量都会进入浏览器可读构建产物。

## 16. 前端验证

当前可用脚本：

```powershell
npm.cmd run dev
npm.cmd run test:plugin
npm.cmd run build:prod
npm.cmd run build:stage
npm.cmd run build:docker
npm.cmd run preview
```

最小验证：

```powershell
npm.cmd run test:plugin
npm.cmd run build:prod
```

当前 `package.json` 没有正式的 lint、typecheck 或完整组件测试脚本。涉及核心交互时，除构建外还应通过独立 E2E 工程验证真实浏览器流程。

监控信息及 Cron 表格的定向数据契约测试复用现有 Vue 编译器、Element Plus 和 Node 测试运行器，不增加依赖：

```powershell
node --test tests/components/monitorTableContracts.test.js
```

该测试验证真实组件的数据、描述渲染、失败恢复和 Cron 输出，不覆盖浏览器布局、鼠标悬浮提示或完整端到端流程；日常局部改动按根目录第 13.0 节选择最小检查，不默认重复执行全量构建。

端到端测试位于仓库根目录的：

```text
ruoyi-fastapi-test/
```

涉及以下内容时必须优先补充或执行浏览器测试：

- 登录和退出；
- 动态菜单；
- 权限按钮；
- CRUD；
- 文件上传、下载；
- 插件启停；
- AI 流式响应；
- 401 和后端不可用恢复。

## 17. 完成标准

前端改动完成前确认：

1. API 请求仍统一经过请求拦截器。
2. 页面、菜单、组件路径和权限码一致。
3. 登录过期和错误路径有正确反馈。
4. 插件和内置页面均能正确解析。
5. 文件组件选择符合公开/私有/业务附件边界。
6. 未向浏览器暴露密钥或敏感响应。
7. 没有明显扩大首屏包或重复引入重型依赖。
8. 插件测试、生产构建及必要 E2E 已真实执行。

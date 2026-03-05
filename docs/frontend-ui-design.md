# Orion 前端 UI 设计（简洁清晰版）

## 1. 设计目标

- 面向“发布执行者”与“运维人员”，优先保证任务可完成性。
- 以“少步骤、低误操作、强反馈”为第一原则。
- 所有关键动作都可追踪到构建记录、部署记录、日志记录。
- 风格保持简洁、专业、可读，避免花哨干扰。

## 2. 目标用户与核心任务

- 发布执行者：创建应用、发起构建、查看构建日志、发起部署。
- 运维人员：维护环境、执行预检查、排查部署失败、回滚历史版本。
- 管理者：查看最近构建成功率、部署成功率、失败原因聚合。

核心任务链路：

1. 创建应用与环境。
2. 预检查本地和远端环境。
3. 发起构建并实时查看日志。
4. 选择构建产物进行部署。
5. 在日志中心定位问题并重试或回滚。

## 3. 信息架构（IA）

一级导航建议如下：

1. 仪表盘
2. 应用管理
3. 环境管理
4. 构建中心
5. 部署中心
6. 日志中心
7. 系统设置

路由建议：

- `/dashboard`
- `/apps`
- `/environments`
- `/builds`
- `/builds/:id`
- `/deployments`
- `/deployments/:id`
- `/logs`
- `/settings`

## 4. 全局布局

布局结构：

- 顶部栏：系统名、全局搜索、通知入口、用户菜单。
- 左侧导航：一级导航，固定宽度，支持折叠。
- 主内容区：页面标题区 + 操作区 + 内容区。
- 右侧抽屉：查看任务详情、日志详情、失败原因。

页面模板：

```text
+--------------------------------------------------------------+
| Topbar: Orion | Search | Alerts | User                      |
+-----------+--------------------------------------------------+
| Sidebar   | Page Header: Title + Actions                    |
|           +--------------------------------------------------+
|           | Filters / Tabs                                  |
|           +--------------------------------------------------+
|           | Main Content (Table / Cards / Forms / Logs)     |
|           +--------------------------------------------------+
```

## 5. 页面级 UI 设计

### 5.1 仪表盘 `/dashboard`

目标：10 秒内掌握当前发布健康度。

模块：

- 今日概览卡片：构建总数、构建成功率、部署总数、部署成功率。
- 最近任务时间线：最近 10 条构建/部署事件。
- 失败聚合面板：按错误类型统计。
- 快捷操作区：新建构建、新建部署、执行预检查。

交互：

- 点击卡片跳转对应筛选页。
- 时间线项点击打开右侧详情抽屉。

### 5.2 应用管理 `/apps`

目标：维护应用基础信息与工作目录绑定。

布局：

- 左侧为应用列表表格（名称、描述、创建时间、最近构建状态）。
- 右侧为应用详情面板（最近构建、最近部署、快捷操作）。

操作：

- 新建应用（弹窗表单：`name`、`description`）。
- 编辑应用（名称、描述；名称不允许空格）。
- 删除应用（带二次确认和风险提示）。
- 快捷发起构建（跳到构建中心并预填 `app_id`）。

### 5.3 环境管理 `/environments`

目标：集中管理 SSH 目标环境并可一键预检查。

布局：

- 环境表格：名称、主机、端口、用户、认证方式（用户名+密码）、最近检查状态。
- 详情抽屉：展示最近检查结果明细。

操作：

- 新建环境（`name`、`host`、`port`、`username`、`password`）。
- 提交前“测试连接”按钮，调用连接测试接口并展示 `ok/detail`。
- 环境列表行内“测试”按钮，验证已保存环境的 SSH 连通性。
- 执行远程预检查。
- 展示连接失败原因（认证失败、超时、网络不可达）。

### 5.4 构建中心 `/builds`

目标：快速发起构建并追踪状态。

布局：

- 顶部操作区：新建构建按钮、筛选器（应用、状态、时间）。
- 左侧：构建参数表单 + 配置保存操作。
- 右侧：构建配置列表（加载、运行、删除）。
- 主区左侧：构建任务表格（ID、App、Tag、状态、时间、耗时）。
- 主区右侧：构建详情卡（镜像摘要、错误信息、查看日志按钮）。

新建构建弹窗：

- App 下拉选择（`app_id`）。
- 镜像 Tag 输入（`image_tag`）。
- 构建上下文（默认 `~/Orion/workspace/{app_name}`）。
- Dockerfile 来源切换：仓库默认 / 在线编辑。
- Build Args 动态键值对输入。
- 超时秒数输入。
- 保存配置：将当前表单参数保存为可复用模板。
- 更新配置：更新当前选中配置。
- 一键构建：基于选中配置直接触发构建任务。

### 5.5 构建详情 `/builds/:id`

目标：构建过程可视、可诊断。

布局：

- 上方状态条：`queued/running/success/failed`。
- 中部日志流面板：WebSocket 实时滚动。
- 右侧信息栏：构建参数、镜像 tag、digest、错误消息。

日志体验：

- 支持自动滚动与暂停滚动。
- 支持关键词过滤。
- 支持“复制最后 200 行”。

### 5.6 部署中心 `/deployments`

目标：按 run/compose 两种模式稳定部署。

布局：

- 顶部操作区：新建部署按钮、筛选器（应用、环境、状态、模式）。
- 列表表格：ID、App、Env、模式、状态、镜像、时间。
- 详情抽屉：执行命令摘要、失败原因、重试入口。

新建部署弹窗：

- App、Environment 下拉。
- 模式切换：`run` / `compose`。
- 镜像来源切换：`build_id` / `image_ref`。
- run 模式字段：`container_name`、`ports[]`、`env_vars{}`。
- compose 模式字段：`compose_content`、`remote_dir`。

互斥提示：

- 同 app+env 存在运行中部署时，按钮置灰并提示原因。

### 5.7 部署详情 `/deployments/:id`

目标：定位部署失败原因并支持回滚动作。

布局：

- 状态头部 + 错误摘要。
- 实时/历史日志面板。
- 回滚卡片：选择历史 digest 或历史 compose 版本。

动作：

- 重新部署（使用当前参数）。
- 回滚部署（使用历史版本）。

### 5.8 日志中心 `/logs`

目标：统一检索构建和部署日志。

布局：

- 日志类型切换：Build / Deploy。
- 检索区：按任务 ID、应用、日期、关键词筛选。
- 日志结果区：时间线式展示，支持下载文本。

## 6. 关键组件设计

组件清单：

- `StatusBadge`：统一状态色与文案。
- `TaskTable`：支持排序、筛选、分页、行操作。
- `LogViewer`：实时流 + 关键字高亮 + 自动滚动。
- `KeyValueEditor`：编辑 `build_args` 与 `env_vars`。
- `ModeSwitchForm`：run/compose 动态表单。
- `PrecheckPanel`：检查项清单 + 失败详情展开。

状态色规范：

- queued：灰蓝
- running：信息蓝
- success：绿色
- failed：红色

## 7. 视觉与品牌规范

字体建议：

- 主字体：`IBM Plex Sans`
- 等宽字体：`JetBrains Mono`

配色建议：

- 主色：`#0B3C5D`（深海军蓝）
- 强调色：`#1F9D8B`（青绿）
- 警告色：`#E67E22`
- 危险色：`#C0392B`
- 背景色：`#F7F9FB`
- 文本主色：`#1E2A32`

设计原则：

- 卡片和表格边界清晰，阴影极轻。
- 单页最多一个主按钮，其他动作使用次级按钮。
- 高风险动作一律红色并二次确认。

## 8. 交互与反馈规范

提交反馈：

- 表单提交后按钮进入 loading。
- 成功提示包含任务 ID，可点击跳详情。
- 失败提示显示可读错误，提供“查看日志”入口。

空状态：

- 没有应用时提示先创建应用。
- 没有环境时提示先配置环境。
- 没有构建记录时展示“发起首次构建”入口。

错误状态：

- API 异常统一 toast + 页面级错误条。
- 网络中断时日志面板提示重连，并自动重试。

## 9. 响应式与可用性

桌面端（>=1200px）：

- 三段式布局（导航 + 主区 + 详情侧栏）。

平板端（768-1199px）：

- 侧栏可折叠，详情抽屉覆盖式。

移动端（<768px）：

- 单列卡片流。
- 日志页只保留核心操作（过滤、复制、暂停滚动）。

## 10. 前端与后端 API 映射

核心映射：

- 应用管理：`POST/GET /api/apps`
- 环境管理：`POST/GET /api/environments`、`PUT/DELETE /api/environments/{id}`
- 连接测试：`POST /api/environments/test-connection`、`POST /api/environments/{id}/test-connection`
- 预检查：`GET /api/precheck/local`、`GET /api/precheck/remote/{env_id}`
- 构建任务：`POST /api/builds`、`GET /api/builds/{id}`、`GET /api/builds/{id}/logs`
- 构建日志流：`WS /api/builds/ws/{id}/logs`
- 构建配置：`GET/POST /api/build-configs`、`GET/PUT/DELETE /api/build-configs/{id}`、`POST /api/build-configs/{id}/run`
- 部署任务：`POST /api/deploy`、`GET /api/deploy`、`GET /api/deploy/{id}`、`GET /api/deploy/{id}/logs`
- 部署配置：`GET/POST /api/deploy-configs`、`GET/PUT/DELETE /api/deploy-configs/{id}`、`POST /api/deploy-configs/{id}/run`
- 镜像仓库：`GET /api/image-repo/images?page=1&page_size=10`、`POST /api/image-repo/deploy`
- AI 快速构建：`GET/POST /api/model-configs`、`PUT/DELETE /api/model-configs/{id}`、`POST /api/model-configs/{id}/test-connection`、`POST /api/ai/generate-dockerfile`

## 11. 推荐实现优先级（MVP）

第 1 阶段：

1. 登录外壳页（可先无鉴权）
2. 应用管理
3. 环境管理
4. 构建中心 + 构建详情日志页

第 2 阶段：

1. 部署中心 + 部署详情
2. 预检查可视化
3. 仪表盘统计

第 3 阶段：

1. 日志中心高级检索
2. 回滚界面
3. 失败原因聚合分析

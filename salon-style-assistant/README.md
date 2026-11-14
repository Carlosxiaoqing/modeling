# 青禾 · 沙龙 AI 发型设计助手

当前首发为**不保存图片的轻量试用版**：选照片 → 模型预览 → 发型师审核 → 用户下载。Cloudflare 仅使用 Workers + D1 保存账号及本轮元数据，不需要 R2、OSS、COS 或图片仓库。浏览器关闭/刷新后未保存图片会丢失。参见 [轻量试用说明](docs/BROWSER_TRIAL.md)。


面向发型师的平板/手机网页。当前交付是**可运行演示开发基线**，支持咨询 → 授权 → 照片 → 点选条件 → 双模式结构方案 → 调整重做 → 审核 → 受限顾客展示 → 顾客选择。

演示不会调用模型，图片是结构示意、评分是模拟数据。新建咨询可明确选择真实模式，使用 Qwen3-VL-Plus 与 Seedream 5.0 Flash。两家 SDK 的真实冒烟已通过，完整顾客换发流程和专业效果仍待获授权照片验证。

## 本地启动

需要 Python 3.12+、uv、Node 22+、npm。每个云任务已有独立工作区，使用现有仓库，不需要创建 Git worktree。

```bash
cd /workspace/modeling/salon-style-assistant
bash scripts/install.sh
bash scripts/start.sh
```

脚本冻结 Python/npm 锁文件、升级迁移、构建前端；API 同时提供构建后的网页。默认端口 8000。演示账号 `demo@salon.local`，密码 `SalonDemo2026!`，仅用于本地演示。前端开发可在 `apps/web` 执行 `npm run dev`，后端需允许开发页面的明确 Origin，默认建议直接使用构建后的同源页面。

数据默认在 `.runtime/`，依赖和运行数据均忽略提交；仅使用合成测试图片，禁止把顾客照片、密钥、签名 URL 提交到 Git。

## 验证

```bash
cd backend
UV_CACHE_DIR=/tmp/salon-uv-cache uv run pytest -q
cd ../apps/web
npm run build
# 先运行 API；使用本环境已有的 Chromium，避免额外下载浏览器。
CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

端到端测试使用合成图片，分别跑桌面、820px 平板与 390px 手机视口，实际点击上传、确认、生成、审核、展示、选择，检查刷新恢复与工作区会话隔离。测试咨询会出现在本地演示数据库中，可在工作台删除。

## 模型与真实模式

复制 `.env.example` 为 `.env` 并安全配置。真实调用需要两家 API 密钥与可用的 Flash 模型；新建咨询选择真实生成即可。部署时应设置独立管理员账号，金额保护为选填。云环境应通过安全环境设置提供密钥，不能发送到聊天或提交文件。

默认按图片数量控制：两类各 3 款、交付最多 9 张、每次咨询累计最多 18 次图像尝试。无需填写金额预算；API 费用由模型平台按实际调用收取。管理员可以选配金额上限和预留价格，未知费用保持 null。真实失败不会降级为演示成功；真实模式先分析照片，再确认条件。

当前实例的专属 Qwen 端点与 Flash 型号放在忽略提交的 `.runtime/provider.env`，启动脚本会加载它；不含密钥。新环境可通过 VISION_ENDPOINT 等非秘密变量重新配置。SDK 使用 OpenAI Python SDK 与官方 volcengine-ark-runtime，关闭隐式重试。

演示与真实应使用不同的 `DATA_DIR` / 数据库，以免复用演示默认账号。真实 HTTPS 环境设置 `COOKIE_SECURE=true`。仅配置变量不会证明模型权限、计费和图片质量已经验证。

## 后台任务与持久化

默认单 API 进程内启动一个持久任务 Worker。独立 Worker：API 设置 `EMBEDDED_WORKER=false`，在 backend 执行 `uv run python -m app.worker`，使用相同数据库和资产目录。SQLite 写事务使用 BEGIN IMMEDIATE；PostgreSQL 用行锁和任务领取，但尚未实测。

页面关闭不取消任务。取消停止后续步骤，不能撤销外部已开始的调用。超过十分钟未更新心跳的任务进入结果未知，需人工核对，不自动重发。现阶段没有 Redis/Celery 或对象存储运行依赖。

## 权限与数据

- HttpOnly 会话、SameSite Cookie、CSRF 校验、单进程登录限流；管理员可通过 `/api/v1/admin/users` 创建本店账号。
- 所有业务资源经过门店校验。客户展示另建只读会话，并销毁当前工作区会话；返回需要重新登录。
- 审核绑定档案与候选确切版本；改照片/条件/重做会阻断旧候选再次发布。
- 完整展示每个选中模式至少三款，单版本最多九张；不足可发阶段预览。演示发布要求显式 demo，禁止混入真实交付。
- 删除撤销访问并清理当前本地资产；没有外部对象存储与备份自动删除保证。
- `/api/v1/admin/metrics` 包含失败任务与候选。`/api/v1/consultations/{id}/feedback` 保存发型师实际效果反馈，顾客选择单独存储。

## 文档

- [原始需求](docs/SPEC_v0.1.md)
- [已确认变更、工程选择与未完成项](docs/DECISIONS.md)
- [运行与排障](docs/OPERATIONS.md)
- [本次验证记录](docs/VALIDATION.md)

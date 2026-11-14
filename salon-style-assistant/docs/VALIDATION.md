# 验证记录

## 轻量首发（图片不保存）

17 项原生单元测试通过；桌面/平板/手机共 6 项浏览器测试通过，包括选照片→演示生成→逐张审核→受限展示→六张 ZIP 下载，以及刷新后图片消失、LocalStorage/SessionStorage/IndexedDB 为空。D1 本地三轮咨询的 inline_images=0、image_urls=0。

真实 URL 处理链冒烟通过：Flash 生成一张无真实顾客的假人图，临时 URL 官方主机为 ark-acg-cn-beijing.tos-cn-beijing.volces.com；Qwen 成功读取该 URL 并返回结构化确认。没有将图片或临时 URL 写入磁盘。

Cloudflare 发布已成功，远端 D1 迁移、管理员初始化、加密配置主密钥与服务绑定通过控制面确认。公网回访被云环境目的地主机策略拦截，尚未完成公网浏览器或真实顾客验证。模型密钥需由管理员在已部署网页的模型设置中填写，未复制云代理占位值。

## 阿里云 OSS 适配

2026-11-11：按用户决定取消生产 R2 依赖。13 项原生规则/OSS 测试通过，3 种视口的本地端到端流程通过，前端构建与 Workers dry-run 通过。OSS 的 PUT、带中文路径 GET、带 STS token DELETE 签名与官方 oss2 2.19.1 生成的合成向量完全一致；校验了私有对象生命周期、拒绝危险端点/路径、禁止重定向、错误信息脱敏、删除失败留存重试。生成参考签名未使用真实凭据。

本地完整流程使用本地存储模拟。缺少实际 OSS Bucket 与授权，因此没有做真实 OSS 上传/读取/删除、费用或跨境连通性验证，也没有发布空壳网页。该外部前提补齐后仍需远端验证。

## Cloudflare 原生运行时适配

2026-11-11：`infra/cloudflare-native` 的 5 项规则/图片测试与本地 Cloudflare 运行时上的 3 项桌面/平板/手机端到端测试通过；原生版 Workers 发布 dry-run 通过。接口使用 D1 状态、私有 R2 和分阶段 Queue，演示自动测试没有调用模型。

Cloudflare 授权已实测可用，R2 远端被 10042（尚未启用）阻断。没有把本地测试当成远端验收，没有创建远端资源或发布空壳前端。Cloudflare 原生版的真实顾客图像、远端持久化、并发压力与供应商用量仍需后续验证。

## Flash 与取消金额必填后的验证

2026-11-11：31 项后端测试通过，桌面/平板/手机 3 项端到端测试通过，前端构建通过。新增覆盖：无需金额配置即可排队真实任务、显式选择真实与演示、专属 Qwen 端点、SDK 关闭自动重试、默认 Flash 型号。自动化流程仍使用演示与合成图片，不会批量调用付费 API。

实际远端检查：两家只读模型列表均 HTTP 200；一次 Qwen 非思考 JSON 调用成功；一次 Seedream 5.0 Flash 无真实顾客的假人图片生成成功，2496×1664，可解码且返回用量。未验证真实顾客换发和费用账单，没有将未知费用计为零。测试输出在被忽略的 `.runtime/flash-sdk-smoke.*`。

当前环境 `ccarenv_b64_Y2NhcmVudl80NjdkNjljZjlmMWM4MTkxODM2OTY5ZmUzMTI1ZjljYw` 的桌面能力 declared enabled、state unknown，但本轮无 desktop js / open_in_codex 工具，不能替用户打开共享预览。网页进程已在环境端口 8000 启动并经端到端请求验证，没有发布环境或外网网站。

日期：2026-11-11（Asia/Shanghai）。在本次云环境执行；未发布生产服务、未调用付费模型。

## 已执行

- `uv sync`，生成并使用 `backend/uv.lock`。
- `npm install`，生成并使用 `apps/web/package-lock.json`。
- `bash scripts/install.sh` 两次完成：冻结安装、Alembic 升级和前端构建，可重复执行。
- `uv run alembic upgrade head`：SQLite 初始迁移通过；本地已有 records 表的兼容迁移也通过。
- `uv run pytest -q`：28 passed；包括长度与时间、null 评分、服务条件、去重、接口合同、端点限制、超时不确定状态、演示隔离、门店隔离、幂等、审核版本、调整重做、并发预算、18 次尝试上限、原图解码、授权与删除、账号角色和反馈。
- `npm run build`：TypeScript 检查和 Vite 生产构建成功。
- `npm run test:e2e`：3 passed。Chromium 桌面 1440×1000、平板 820×1180、手机 390×844；每种视口完整操作合成照片上传→点选确认→六款演示方案→刷新恢复→逐款查看审核→受限展示→选择反馈→退出重新登录。工作台与审核页无水平溢出，无 pageerror。
- 页面实际截图检查，涵盖桌面工作台和手机审核页面。浏览器测试截图写入被忽略的 `apps/web/test-results/`。

## 调查与修正

- uv 默认缓存目录只读：使用 `/tmp/salon-uv-cache`，未更改系统权限。
- Playwright 浏览器下载域名被网络策略拒绝：改用已有 `/usr/bin/chromium`，端到端测试成功；未降低 TLS 校验或新增网络授权。
- 首次浏览器测试发现授权复选框异步回弹，已修复并在三种视口重测通过。
- 新增化学处理条件检查后，更新了过时的精确数量断言，改为验证具体阻断原因；28 项重测通过。
- 测试依赖有一条 Starlette 关于 httpx TestClient 的弃用提示；测试实际运行并完成，不影响当前通过结果。

## 尚未验证

真实 Qwen/Seedream 请求和响应参数、图像效果/成本/性能指标；PostgreSQL；Docker 部署；iOS Safari/微信与实体相机；多实例负载；门店专业审核和顾客试点。完整未完成项见 DECISIONS.md。

## 云配置保存

云环境配置草稿读取连续返回 INVALID_ARGUMENT；安装脚本与启动说明的保存调用也返回无法确认保存。仓库内脚本与文档已经落盘并验证，但平台配置持久化未确认，也没有发布环境版本。

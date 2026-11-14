# Cloudflare 部署进展

## 最新决定：Cloudflare + 阿里云 OSS

用户没有 Visa 卡，并明确选择阿里云图片存储。生产版本已移除 R2 绑定与开通检查：Workers/D1/Queues 仍在 Cloudflare，图片改用阿里云 OSS 私有 Bucket。无需创建新的 Cloudflare token，也不再要求开通 R2。

`src/storage.mjs` 实现 OSS V4 签名的私有上传、读取与删除；端点只能按桶名和地域组成阿里云官方 HTTPS 域名，禁止重定向和路径穿越。未上传任何真实照片或密钥。访问撤销立即生效，物理删除失败留在 D1 待清理列表，Cron 重试；旧照片删除失败不会删掉新照片。

验证：13 项原生规则/OSS 测试通过，包括与官方 oss2 2.19.1 SDK 的 3 组签名对比；桌面/平板/手机 3 项本地完整流程通过；生产配置 dry-run 通过且没有 R2 绑定。完整流程的存储是本地模拟，远端 OSS 尚未实测。

当前缺少 OSS Bucket、地域及 RAM 访问授权，未发布远端可用网址。下一步见 [阿里云 OSS 设置](ALIYUN_OSS_SETUP.md)。以下涉及 R2 阻断的内容均为历史记录，不再要求用户启用 R2。

## 最新状态：原生后端已适配，等待启用 R2

当前环境已确认 `CLOUDFLARE_API_TOKEN` 为 ready，账号发现、Workers 子域名、D1 和 Queues 只读访问成功。R2 返回 HTTP 403 / 10042：`Please enable R2 through the Cloudflare Dashboard.`。套餐查询权限不在当前 token 范围内，不因此要求额外权限；不代购或启用付费服务。

新增 `infra/cloudflare-native/`，以 Workers + D1 + 私有 R2 + Queues + Cron 运行完整业务接口。D1 使用版本条件更新防并发覆盖，队列每条消息只运行一个外部阶段，调用前持久领取；未知结果不自动重试。浏览器转 JPEG 并清除元数据，服务端检查尺寸/格式并删除残留元数据。

本地 Miniflare 验证：原生规则/照片 5 项测试通过，桌面/平板/手机 3 项完整端到端测试通过，覆盖上传→确认→六款演示→刷新恢复→审核→顾客展示→选择。Wrangler 原生版 dry-run 通过。首次浏览器测试发现审计 INSERT 参数数量错误，已修正后完整重测通过。

新增 `scripts/deploy-cloudflare.py`：先检查 R2，再创建独立名称的 D1/R2/Queue、迁移并发布 Worker、设置随机管理员凭据。它不复制模型代理密钥，不覆盖其他项目，不接受付费协议。R2 未启用时在任何资源创建前停止。

**本轮没有创建远端资源、没有发布网址、没有做远端完整验收。** 仍需用户在 Cloudflare 控制台启用 R2 后继续发布；发布后的模型密钥需要安全配置到远端 Secrets。以下为之前迭代的历史记录，关于原生后端尚未适配的描述由本节取代。

## 当前用户选择

用户已授权部署，并明确只提供 Cloudflare 授权，不另提供服务器。目标应是 Cloudflare 自身承载网页、业务数据、私有图片与后台任务，可使用默认 workers.dev 域名，不要求另外购买域名。

现有 Python + 本地 SQLite/文件 + 后台线程不能直接上传到 Pages 或普通 Workers。`infra/cloudflare` 目前是已通过 dry-run 的网页与 API 网关；`infra/Dockerfile` 是已构建的后端容器，**这两件本身还不构成全 Cloudflare 托管部署**。下一步需依据账号已开通服务，适配 Workers + D1/R2 + Queues 或相应托管运行时；不得发布没有可用后端的空壳来冒充完成。

## 已验证

- Cloudflare 官方 Workers static assets 配置已核对，Wrangler dry-run 成功，未上传。
- 网关 5 项测试通过：静态资产、安全响应、缺少后端明确失败、私有源站与 CSRF/Cookie 转发、不跟随源站重定向。
- 后端 Docker 构建成功，冻结锁文件，代理 CA 只在 BuildKit secret 挂载，未写入镜像。
- 容器冒烟：无源站令牌 403、有令牌健康检查 200、错误站点登录 403、正确站点登录 200、Cookie Secure/HttpOnly。仅用合成管理员与独立 Docker 测试数据。
- 31 项后端测试通过。
- `wrangler whoami` 确认未登录；当前环境没有 Cloudflare token、账号 ID 或已有 OAuth 配置。

## 需要的授权

在 https://dash.cloudflare.com/profile/api-tokens 创建仅限目标账号的 API Token。后续全托管方案通常需要 Workers Scripts 编辑、D1 编辑、Workers R2 Storage 编辑、Queues 编辑，以及用于发现账号的账号设置读取权限。实际部署前根据采用的服务核实权限，避免使用 Global API Key。

将 token 安全配置为本云环境的 `CLOUDFLARE_API_TOKEN`，允许目标 `api.cloudflare.com`。不要在聊天中粘贴 token。账号 ID 可在获得相应读取权限后从 API 获取，不要求用户额外提供。

Cloudflare API 网络域名还需放行 `api.cloudflare.com`。部署后的 workers.dev 具体域名确定后再添加为验证目的地；不要替换未知网络允许列表。尝试添加凭据要求的配置草稿接口仍返回 INVALID_ARGUMENT，持久化未确认，不能声称平台已保存。

## 远端密钥

现有 `ARK_API_KEY` 和 `DASHSCOPE_API_KEY` 为当前云环境的代理绑定。**不得把进程中的代理占位值上传到 Cloudflare，当作真正的远端模型密钥。** 部署后需要通过 Cloudflare Worker 的安全 Secrets 设置真实厂商密钥，或使用有明确支持的凭据注入方案；不在聊天、Git、静态前端或构建产物中保存密钥。

## 尚未完成

Cloudflare 账号能力与套餐核实、全托管后端适配、远端持久化和任务验证、正式资源创建与发布、远端管理员与模型 Secrets 配置、真实访问网址及完整验收。不能把本地容器构建、dry-run 或临时穿透称为这些步骤已完成。

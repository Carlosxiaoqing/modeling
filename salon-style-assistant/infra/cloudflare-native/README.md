# Cloudflare 轻量试用部署

当前生产配置为 WORKFLOW_MODE=browser。图片只在当前浏览器会话中处理，审核后由用户保存；不创建存储桶或后台队列。服务器保留账号、加密模型设置和本轮业务元数据。

完整说明与验证：[BROWSER_TRIAL.md](../../docs/BROWSER_TRIAL.md)。

## 发布

在项目根目录执行 `backend/.venv/bin/python scripts/deploy-cloudflare.py`。需要已有 Cloudflare API 授权，账号 ID 自动发现。脚本创建 Worker + D1、通过官方 query API 升级迁移、设置随机管理员密码与配置加密主密钥。不会购买套餐或上传平台模型代理占位值。私有登录信息保存在忽略提交的 `.runtime/cloudflare-login.txt`。

## 本地测试

使用 `wrangler.browser.local.jsonc`；本地 .dev.vars 仅设置演示管理员和合成 CONFIG_ENCRYPTION_KEY，不能提交。迁移按 migrations/ 中的 SQL 顺序执行到本地 D1。

```bash
npm test
WRANGLER_SEND_METRICS=false XDG_CONFIG_HOME=../../.runtime/cloudflare-config npx wrangler dev --config wrangler.browser.local.jsonc --port 8791 --persist-to ../../.runtime/browser-tests
# 另一个终端，位于 apps/web：
npx playwright test --config playwright.browser.config.ts
```

历史对象存储版、OSS 适配与 Queue 逻辑保留作后续升级参考，生产 browser 路由不会调用它们。不要把历史 R2/OSS 的开通要求继续当作当前前置条件。

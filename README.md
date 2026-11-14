# Modeling / 沙龙 AI 发型设计助手

项目位于 [salon-style-assistant](salon-style-assistant/README.md)。

当前首发实现为轻量网页：选择照片 → 模型预览 → 发型师审核 → 用户自行下载。原图和效果图仅在网页会话及请求处理中临时使用，不保存到服务器或图片仓库。

- [当前试用版说明](salon-style-assistant/docs/BROWSER_TRIAL.md)
- [网页前端](salon-style-assistant/apps/web/src/BrowserStudio.tsx)
- [Cloudflare 后端与部署](salon-style-assistant/infra/cloudflare-native/README.md)

真实模型使用 Qwen3-VL-Plus 与 Seedream 5.0 Flash，密钥由管理员在网页中安全配置。演示模式与真实模式明确区分。

本仓库不包含密钥、私有登录信息或顾客照片。Python 后端和历史存储适配保留作本地原型及后续升级参考。

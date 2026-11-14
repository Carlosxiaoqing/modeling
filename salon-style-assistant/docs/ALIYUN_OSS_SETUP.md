# 阿里云 OSS 图片存储

用户已明确改用阿里云 OSS，不再启用 Cloudflare R2。Cloudflare 继续运行网页、D1 和后台 Queues；不需要另外提供 Python 服务器。

## 先创建 Bucket

在 https://oss.console.aliyun.com/ 开通 OSS，并创建：

- 名称：自定义、全球唯一的小写英文/数字/连字符。
- 地域：默认华北 2（北京），配置值 `cn-beijing`。
- 存储类型：标准存储。
- 读写权限：私有，保持“阻止公共访问”开启。
- 按量付费即可，不需要为了本项目先买资源包。
- 无需绑定自定义域名，无需开启公共读，也无需配置浏览器跨域规则；浏览器只访问本项目的受控接口。

桶名和地域不是密钥，可以告诉开发助手。将 `infra/oss-settings.example.json` 的实际内容保存在忽略提交的 `.runtime/oss-settings.json`，或由部署进程提供同名环境变量。

OSS 的存储、读写和下载流量由阿里云按实际用量计费，不宣称永久免费。账号开通、实名和付款以阿里云控制台实际要求为准。

## RAM 授权

Qwen 的 DASHSCOPE_API_KEY 不能访问 OSS。创建仅用于本项目的 RAM 程序访问用户，按 `infra/oss-ram-policy.example.json` 限定到实际 Bucket 的 `salon-style/*` 前缀，授予 GetObject、PutObject、DeleteObject、PutObjectAcl。最后一项用于确保每个对象显式为 private，不授予账号级管理权限。

正式部署的 Worker Secrets：

| 名称 | 内容 |
|---|---|
| OSS_ACCESS_KEY_ID | RAM 用户的 AccessKey ID |
| OSS_ACCESS_KEY_SECRET | RAM 用户的 AccessKey Secret |
| OSS_SECURITY_TOKEN | 仅使用临时 STS 凭据时填写 |

非秘密变量：OSS_BUCKET、OSS_REGION。端点由代码根据这两项生成固定的阿里云官方 HTTPS 地址，不接受任意自定义端点。

密钥直接在 Cloudflare Worker 的 Settings → Variables and Secrets 中安全输入，不发到聊天、不写入 Git、不上传到前端。不要将当前云环境里的代理占位值当成可移植的 OSS 签名密钥：V4 签名在后端计算 HMAC，需要远端运行时可用的真实密钥或受支持的临时凭据。

## 已实现与验证

- Cloudflare 生产配置和发布脚本不再访问、创建或绑定 R2。
- 私有 OSS 的 PUT / GET / DELETE 通过统一存储接口使用；HTTPS、V4 签名、不跟随重定向、不生成公开图片链接。
- 对象固定保存在 `salon-style/` 前缀，PUT 显式 private；上传照片、生成图、评审读取、顾客受控查看和删除均走 OSS。
- 失败的物理删除持久化为待清理任务，每 5 分钟重试；访问撤销即时生效。替换旧照片时，旧对象清理失败不会删除已经成功保存的新照片。
- 签名已与阿里云官方 oss2 2.19.1 SDK 生成的三组合成测试向量逐字对比（PUT、带中文路径 GET、带 STS token DELETE），不含真实密钥。
- 本地完整流程使用明确标注的本地存储模拟；它不能证明远端 OSS 权限、费用或跨网络连通性已经验证。

## 尚待外部配置

当前未检测到 OSS Bucket、地域和 OSS 授权。拿到桶名和地域后可继续准备发布；远端 OSS Secrets 配好后，需要使用合成图片做实际上传→读取→删除验证，再做获授权顾客照片测试。任何一步未通过，都不能声称网页的真实存储已上线可用。

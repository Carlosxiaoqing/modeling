# 沙龙 AI 发型设计助手：MVP 开发规格

版本：v0.1  
编制日期：2026-11-11（Asia/Shanghai）  
适用对象：接手开发的 AI、产品设计、开发、测试、试点发型师  
文档性质：产品需求、技术设计、实施任务与验收依据。尚未实现；模型效果、性能、成本和业务指标均需实测。

## 0. 给接手开发 AI 的说明

本文件可以独立使用，不需要读取原始聊天记录。目标是实现可以在真实门店试用的完整 MVP，而不只是静态页面。

### 0.1 用户已明确的需求

1. 服务中国大陆综合沙龙，男女发型都支持。
2. 发型师操作、审核后交给顾客，不做自动向顾客交付。
3. 发型师确认条件以选项、图片卡、开关、长度档位为主，避免打字。
4. 使用 Qwen3-VL-Plus＋Seedream 5.0 作为原型基线；不同模型优劣留到实测后判断。
5. 提供“现在可做”和“留长后可做”两类方案。
6. 正常情况下至少 3 款合格造型，最多 9 张交付效果图，评分、排序并避免高度重复。
7. 长期方案说明目标条件和留发时间；不能把密度不足伪装成等待即可解决。
8. 先完成可测试版本，再根据门店反馈迭代。

### 0.2 为开发启动采用的默认决定

以下是实施默认值，不是经过实验验证的结论：

- 首版为平板优先的响应式网页，兼容手机、电脑。
- 默认两类各 3 款，共 6 款主图。
- 同一个顾客展示版本最多 9 张生成图片，侧面图也占额度；内部失败和重试另计成本。
- Seedream 5.0 子版本先固定 Pro；接入前检查账号可用性，不静默换模型。
- 发型模板库目标 30～50 个经发型师确认的模板。
- 每次咨询默认最多 18 次图像生成尝试，另有金额预算，两者先到者生效。
- 试点数据保留周期建议 30 天，可配置，使用前明确告知。
- 所有评分权重、增长参数、耗时和质量目标均为初始配置。

### 0.3 开发执行要求

- 先检查工作区 AGENTS.md、README 和现有代码；不要覆盖、重构无关项目。
- 没有合适现有项目时，创建独立目录 salon-style-assistant/。
- 按本文阶段推进，合理、可逆的实现细节自行决定并记录，不反复询问已确定需求。
- 没有密钥时完成明确标识的演示模式、真实适配器和测试；不得把模拟图、模拟分数称为真实结果。
- 演示与真实数据显式区分，演示结果不能进入真实咨询交付。
- 不提交密钥、原始顾客照片、签名链接到 Git。
- 不声称 AI 能准确测量照片中的发长、真实密度、医学状况或客观颜值。
- 未获用户授权，不购买服务、不发布生产服务、不把顾客照片发送给新增厂商。
- 最终交付可运行代码、配置示例、数据库迁移、测试证据、运行说明和已知限制。

## 1. 产品定位与形态

工作名称：沙龙 AI 发型设计助手。

核心价值：帮助发型师把顾客条件转化为可讨论、可审核、可执行的方案，减少沟通不确定性。

第一轮验证：

1. 效果图是否保持顾客原貌。
2. 发型师是否认为推荐适合且可实现。
3. 点选条件是否足够快速。
4. 顾客是否更容易理解和选择。
5. 一次完整咨询的耗时、成本、重试量是否可接受。

产品使用“推荐”“根据当前条件估算”，不使用“客观最美”“保证剪成这样”“准确预测长发日期”。

| 形态 | 当前决定 | 理由 |
|---|---|---|
| 响应式网页 | 首版采用 | 方便试用和迭代，适合平板上对比与审核 |
| 微信小程序 | 后续按需求增加 | 适合顾客到店前上传、保存方案和复访 |
| 原生 App | 首版不做 | 当前业务价值未验证，不增加多端维护负担 |

网页相机需要安全上下文和授权，始终保留相册上传兜底。微信内置浏览器、iOS Safari、Android Chrome 的实际表现需要测试，不假定完全一致。

## 2. 范围

### 2.1 必须实现

- 门店、发型师账号与权限隔离。
- 咨询创建、照片处理授权、拍照和上传。
- 正面、侧面和可选补充角度的输入与质量检查。
- AI 建议＋发型师点选确认。
- 两类方案、模板筛选、生成、质检、评分、去重。
- 留发时间范围和过渡期建议。
- 点选修改、重新生成、版本管理。
- 审核后展示、顾客选择、反馈记录。
- 后台任务、恢复、幂等、有限重试、预算与成本记录。
- 数据删除、基础审计和试点指标。

### 2.2 首版不做

- 顾客完全自助推荐和自动交付。
- 小程序、原生 App、实时 AR、三维重建。
- 脱发或头皮疾病诊断、医疗建议。
- 接发、发片、植发等增量手段的自动推荐。
- 专用模型训练或默认使用顾客照片训练。
- 预约、支付、会员、营销、公开案例社区。
- 通过性别、年龄、职业推断替代顾客主动表达的风格偏好。

## 3. 两类方案与数量口径

| 模式 | 约束 | 输出 |
|---|---|---|
| current：现在可做 | 当前发长、密度、发质、发际线和接受的项目 | 效果图、推荐理由、所需服务、打理要求 |
| grow_out：留长后可做 | 保留密度、发质、发际线，允许增加发长 | 效果图、目标长度、时间区间、过渡期说明 |

自然留长可以增加长度，不能默认增加密度。当前方案如果依赖烫发，必须得到明确接受并展示依赖条件。首版默认保持原发色。

数量规则：

1. 默认两种模式开启，各目标 3 款；只选一个模式时默认 3 款。
2. 两类方案分别排名，不混用两套权重计算出的分数。
3. 候选充足时最多展示 9 款，但单个发布版本全部生成图片总数最多 9 张。
4. 默认 6 张主图，可为选中的方案补最多 3 张侧面图。
5. 选择 9 张主图后，补侧面必须移除其他交付图片。
6. 一款可有多个视角；款式数与图片数分别统计。
7. 原始照片不占生成图额度；内部重试、旧版本不向顾客展示，但计入成本。
8. 不通过拼接未计数图片绕过上限。
9. 不足 3 款时标记“结果不足”，提示补充、重试或调整条件，不能硬凑不合格方案。
10. 如需提前讨论，可以发布已审核的“阶段预览”，但不可标为完整交付，也不计为完整交付成功。
11. 超出额度时按模式目标和去重后排序预选，发型师可调整交付集合，保留系统排名与人工选择记录。

## 4. 角色、权限与顾客展示

| 角色 | 权限 |
|---|---|
| 门店管理员 | 管理本店账号、预算、配置、模板范围和指标 |
| 发型师 | 创建咨询、确认条件、生成、审核、交付、反馈 |
| 顾客展示会话 | 仅查看某个已发布快照的必要内容 |

- 服务端执行门店归属和资源授权，不能只靠前端隐藏。
- 首版管理员创建账号，不做公开注册。
- 顾客展示采用专用只读会话，不携带工作区权限；切回发型师工作区需要重新验证。
- 推荐 HttpOnly、Secure Cookie、适当 SameSite、CSRF 防护及登录限流。
- 客户端传入 salon_id 不能作为授权依据。
- 顾客展示接口不返回内部备注、提示词、失败图或未审核候选。

## 5. 用户流程与页面

~~~mermaid
flowchart LR
    A[新建咨询与照片使用确认] --> B[拍照或上传]
    B --> C[AI分析与点选确认]
    C --> D[后台生成与检查]
    D --> E[发型师审核调整]
    E --> F[顾客展示与选择]
    F --> G[记录反馈和实际效果]
~~~

| 页面 | 内容 | 操作 |
|---|---|---|
| 咨询列表 | 进行中、待审核、已交付、失败 | 新建、继续、筛选 |
| 照片采集 | 各角度占位、拍摄提示、授权状态 | 拍照、相册上传、重拍 |
| 条件确认 | 建议值、偏好、头发参数、未知项 | 点选修正、确认生成 |
| 生成工作区 | 阶段进度、逐张就绪结果 | 查看、取消后续任务 |
| 审核工作区 | 原图对比、评分、限制、问题 | 通过、调整、拒绝 |
| 顾客展示 | 已审核方案、理由、打理和时间 | 对比、喜欢、选定 |
| 结果反馈 | 最终选择、执行说明、实际效果 | 保存、补充反馈 |
| 管理设置 | 账号、预算、配置状态、指标 | 管理和查看 |

交互规则：

- 平板使用大按钮、图片卡；手机使用纵向布局，不依赖悬停。
- 自动保存选择；离开未确认修改时提醒。
- 拒绝相机权限后可上传相册照片。
- 刷新或关闭页面不取消后台任务，再次进入可恢复。
- 进度显示真实阶段和完成数量，不伪造倒计时。
- 顾客页只显示有助于选择的信息，不暴露模型参数和内部错误。
- 不设置默认美颜功能。

## 6. 照片与质量检查

最低要求：正面一张＋任一侧面一张。推荐补充左右侧面、后面和头顶。

拍摄要求：单人、头部完整、光线均匀、无强滤镜，尽量干发、避免大量造型产品。必要时补拍发际线或局部。

产品初始限制（不是厂商极限）：

- 最多 5 张主要角度照片。
- 单张原图默认不超过 15 MB；限制解码像素总量，例如 40 MP。
- 支持 JPEG、PNG、WebP；HEIC/HEIF 服务端转码，不支持时明确提示改用 JPEG。
- 校验真实文件内容、解码安全和对象归属。
- 校正 EXIF 方向，移除 EXIF，生成标准化副本和缩略图。
- 模型输入按适配器限制处理，原始资产不被无记录覆盖。

质量检查：模糊、过暗、多人、裁切、遮挡、疑似角度错误。严重问题阻断；轻微问题标记后可继续。发型师可以修正角度标签。

湿发或造型产品影响观察时标记限制，不生成虚假确定的密度结论。

## 7. 点选确认表单

### 7.1 顾客偏好

| 字段 | 控件 | 选项 | 规则 |
|---|---|---|---|
| modes | 多选 | current / grow_out | 默认都选 |
| style_preferences | 图片卡多选 | 自然、利落、柔和、成熟、时尚、个性等 | 最多 3 项，可无偏好 |
| cut_tolerance | 单选 | 仅修整 / 适度剪短 / 可明显改变 | 主动确认 |
| fringe_preference | 单选 | 保留 / 可改变 / 不要刘海 / 无偏好 | 作为约束 |
| tie_back_need | 单选 | 必须 / 偶尔 / 不需要 | 必须能扎为硬约束 |
| daily_styling_time | 单选 | 基本不打理 / 5 分钟内 / 5～15 分钟 / 更久 | 不推断生活方式 |
| perm_acceptance | 单选 | 不接受 / 可讨论 / 接受 | 可讨论不等于已接受 |
| waiting_horizon | 单选 | 3 个月内 / 半年内 / 一年内 / 不限制 | 长期模式显示 |

### 7.2 当前条件

| 字段 | 控件 | 选项 |
|---|---|---|
| curl_pattern | 图示单选 | 直 / 微卷 / 明显卷 / 不确定 |
| strand_thickness | 单选 | 细软 / 中等 / 粗硬 / 不确定 |
| density | 单选 | 偏少 / 中等 / 偏多 / 不确定 |
| local_conditions | 多选＋区域示意 | 两侧易翘 / 发旋明显 / 局部稀疏等 |
| photo_hair_state | 单选 | 干发 / 湿发 / 较多造型产品 |
| treatment_history | 多选 | 无 / 烫过 / 染过 / 漂过 / 不确定 |
| damage_observation | 单选 | 无明显问题 / 有受损表现 / 需判断 |

规则：

- 备注选填，正常流程不需要键盘。
- 不确定为合法值，不自动转成正常、中等或接受。
- AI 仅建议可观察项，source=ai_suggestion；确认后独立记录人工值、操作者和时间。
- 顾客偏好不由 AI 擅自预填。
- 一键确认只适用于明确展示的建议，不隐藏偏好默认值。
- 化学处理依赖和受损情况不清楚时，方案标记条件待确认，不自动提供药水配方或安全结论。

### 7.3 发长档位

分区：fringe、top、sides、back。可选 <1、1～3、3～5、5～8、8～12、12～20、>20 cm、不确定。

实现中统一为非重叠档位并定义边界，保存上下界而不是中点。长发可以显示齐肩、锁骨等图示，但不能直接当成固定厘米。

精确入口使用数字滚轮，保存 measurement_type=measured。必要时左右两侧分开记录；卷发拉直长度与视觉长度分开。

~~~json
{
  "zone": "fringe",
  "length_cm": {"min": 3, "max": 5},
  "measurement_type": "range_selection",
  "source": "stylist",
  "confirmed": true
}
~~~

没有可靠长度时，依赖长度的 current 方案不能自动确认可实现；grow_out 可以提供条件性预览，但时间为 null。

## 8. 发型模板库

按长度、轮廓、刘海、分缝、层次、纹理、维护需求组织。男女标签只用于浏览，不作硬性过滤。

每个模板包含：

- ID、版本、名称、结构族。
- 分区目标长度、最低长度要求。
- 刘海、分缝、顶部高度、两侧体积、耳周及后区轮廓。
- 层次、纹理、密度、发质和发旋条件。
- 必需项目、可选项目、打理要求。
- 扎发能力、过渡期提示。
- 参考素材、授权来源、发型师审核状态。

示例仅说明结构，长度不能直接作为专业标准：

~~~json
{
  "style_id": "style_example",
  "version": 1,
  "name": "示例发型",
  "family": "medium_layered",
  "target_lengths_cm": {
    "fringe": {"min": 8, "max": 12},
    "top": {"min": 10, "max": 15},
    "sides": {"min": 8, "max": 12},
    "back": {"min": 10, "max": 16}
  },
  "silhouette": {
    "fringe": "side_swept",
    "parting": "side",
    "side_volume": "controlled",
    "layering": "medium"
  },
  "required_services": [],
  "conditional_requirements": [],
  "maintenance_level": "medium",
  "tie_back_supported": false,
  "reference_asset_ids": [],
  "review_status": "draft"
}
~~~

首版可使用版本化 JSON/YAML 与导入校验，不必做复杂编辑器。开发种子标为 draft；真实推荐只使用 stylist_verified 模板，禁止伪造人工审核。30～50 个模板由专业人员逐步确认。

## 9. 推荐与生成流水线

1. 校验授权、照片、档案版本、模型配置和预算。
2. Qwen 提取可观察条件与未知项。
3. 发型师点选确认，冻结本轮 profile_revision。
4. 代码按硬约束过滤已审核模板。
5. Qwen 对白名单模板规划候选结构与理由。
6. 代码复核 ID、长度、所需服务和偏好。
7. 按结构去重，优先为有希望的候选出图。
8. Seedream 每个候选、每个视角单独生成。
9. 转存资产，质检与分项评分。
10. 有限修复或补选，达到目标或预算上限后停止。
11. 分模式排名，进入发型师审核。
12. 发布确定版本的顾客展示快照。

“可讨论烫发”只能生成条件性候选，交付为可执行方案前必须明确确认依赖条件。

只有正面效果图时不能声称完成多角度验证。需要侧面验证时标记限制，补图或由发型师基于实物进行明确确认。

多视角共用同一份结构说明，不独立随意设计另一种发型。

## 10. 模型接入

### 10.1 初始配置

~~~dotenv
MODEL_MODE=real
VISION_PROVIDER=dashscope
VISION_MODEL=qwen3-vl-plus
IMAGE_PROVIDER=volcengine
IMAGE_MODEL=doubao-seedream-5-0-pro-260628
IMAGE_SIZE=2K
DASHSCOPE_API_KEY=
ARK_API_KEY=
~~~

具体端点、区域、Model ID、账号权限在接入前核实。示例不保证每个账号已开通。不可用时显示配置错误，不静默切换模型。

### 10.2 Qwen

- 初始采用非思考模式＋JSON Object；根据当前接口设置 enable_thinking=false、response_format.type=json_object，提示中明确要求 JSON。
- JSON 格式正确不等于满足业务 Schema，服务端执行解析、Pydantic/Schema、枚举范围和引用 ID 校验。
- analysis、planning、evaluation 分开调用和提示词。
- 相同模型规划和评审不构成独立专家验证，人工审核仍然必要。
- 不输出无依据的厘米数、医学判断、颜值评分。
- 结构错误最多修复一次，失败则明确报错。
- 模型返回的 URL、ID、操作指令均不可直接信任。

### 10.3 Seedream

- 固定 5.0 Pro，多参考输入、单图输出。
- Pro、Flash、Lite 的参数能力不同，不能混用组图或流式参数。
- 输入顾客原图、角度标签、已确认条件、目标结构和允许变化范围。
- 保持脸部、肤质、发际线、发色、姿态、光线；必要的头发遮挡变化另行检查。
- 长发可能覆盖背景和肩部，短发可能露出原遮挡区域，不能假设只替换旧头发像素。
- 指令编辑不能保证锁脸，生成后必须质检；不假定存在精确蒙版接口。
- 重做默认从原图和最新版结构生成，必要时加上版辅助参考，避免累积漂移。
- 返回临时 URL 必须及时转存，不能当永久资产链接。
- 保留供应商要求的标识策略，顾客界面注明 AI 效果预览。

### 10.4 适配器接口

~~~text
VisionProvider.analyze(images, context, schema_version) -> AnalysisResult
VisionProvider.plan(profile, verified_templates, mode) -> CandidatePlan[]
VisionProvider.evaluate(originals, generated, profile, plan, rubric) -> EvaluationResult
ImageProvider.generate(originals, plan, view, parameters) -> GeneratedAsset
~~~

统一记录 request_id、provider、model、usage、duration_ms、error_code、retryable、result。厂商未返回的用量保存 null，不假装已核实实际费用。

## 11. 提示词与输出合同

提示词版本化，记录版本和摘要；不要记录不必要的个人信息和图片 Base64。

### 11.1 分析

输入：带角度标签的照片、已确认条件。输出：

~~~json
{
  "observations": [
    {
      "field": "side_volume",
      "value": "example",
      "asset_id": "asset_example",
      "evidence": "可见依据"
    }
  ],
  "suggested_fields": [],
  "unknown_fields": [],
  "photo_issues": [],
  "blocking_issues": []
}
~~~

不从照片猜测个性、职业或消费能力；不覆盖人工已确认值。

### 11.2 规划

输入：确认档案、模式、白名单模板和偏好。输出模板 ID、目标结构、依赖条件、推荐理由、待确认项。所有 ID 必须存在于白名单。

### 11.3 生成骨架

~~~text
为参考照片中的同一位顾客制作发型效果预览。
参考图角色：{images_with_view_roles}
当前条件：{confirmed_profile}
模式与允许变化：{mode_and_constraints}
目标结构：{style_spec}
目标视角：{view}
保留顾客原有脸部、肤质、发际线、发色和自然外观。
不得瘦脸、调整五官、磨皮或增加不符合条件的密度。
只输出一张无说明文字的效果图，评分和标签由应用渲染。
~~~

提示词不是质量保证，必须检查输出。

### 11.4 评审

~~~json
{
  "gate_status": "review_required",
  "issues": [
    {
      "code": "IDENTITY_DRIFT_SUSPECTED",
      "severity": "blocking",
      "evidence": "具体可见依据"
    }
  ],
  "dimensions": {
    "visual_balance": {"score": 4, "evidence": "示例依据"},
    "feasibility": {"score": null, "evidence": "条件待确认"},
    "preference_match": {"score": 4, "evidence": "示例依据"},
    "maintenance_match": {"score": 3, "evidence": "示例依据"},
    "transition_ease": {"score": 3, "evidence": "示例依据"}
  },
  "unknown_fields": ["example_field"]
}
~~~

总分由代码计算；证据应简短、可观察，不要求或保存内部思维过程。

## 12. 质检、评分与排名

### 12.1 合格检查先于评分

不合格或需要解决的问题：

- 明显改变脸部、肤质、发际线或原貌。
- current 模式增加不现实的长度或密度。
- 依赖顾客拒绝的服务。
- 结构与已确认条件冲突。
- 图像伪影或视角结构矛盾。
- 缺少决定可实现性的关键条件。

生成失败与发型不适合分别记录。图像失败优先有限重做，不直接作为“该发型不适合”的标签。

人工可以确认模型误报，记录理由；不能绕过真实的未授权、拒绝服务、过期版本、图片上限、超预算等代码约束。

### 12.2 分数

| 维度 | current 权重 | grow_out 权重 |
|---|---:|---:|
| 轮廓与比例协调 visual_balance | 30 | 35 |
| 现实可实现 feasibility | 30 | 20 |
| 偏好匹配 preference_match | 20 | 20 |
| 维护匹配 maintenance_match | 15 | 15 |
| 实现过程友好 transition_ease | 5 | 10 |

0～5：5 充分匹配；4 轻微取舍；3 明确取舍；2 较大限制；1 明显不匹配；0 不满足；null 信息不足。

~~~text
总分 = Σ（分项分数 / 5 × 权重）
~~~

必需维度为 null 时总分也为 null，不按平均值或零补齐，不进入正式排名。显示整数，避免虚假精确性。

初始相近分数阈值可设为 3 分以内，作为并列展示或人工复核提示，不表示统计显著。

“证据充分程度”由照片完整性、测量和人工确认组成，不用模型自报的百分比成功率。

### 12.3 去重和人工排序

按长度类别、刘海、分缝、轮廓、层次、纹理聚类。高度相似方案保留最高分，再排序；阈值配置化。

显示“去重后的推荐排名”，不宣称是未经约束的全部图片 Top 9。

分别保存 system_rank、stylist_preferred、delivery_order。人工首推不能改写原模型分数。

后续可加入两两比较，固定条件、交换展示顺序并允许平局；首版不强制引入第二家评审模型。

## 13. 留发时间计算

平均每月约 1 cm 仅为一般背景；初始情景参数 0.8～1.2 cm/月，不代表个人测量或承诺。

某区当前长度 [Lmin,Lmax]，目标最低长度 T：

~~~text
t_min = max(0, T - Lmax) / 1.2
t_max = max(0, T - Lmin) / 0.8
整体下界 = max(所有必要区域 t_min)
整体上界 = max(所有必要区域 t_max)
~~~

月份向外取整，下界向下、上界向上。0 表示长度条件可能满足，不表示其他条件自动满足。缺 6 cm 的示例约 5～8 个月，不计未来修剪。

特殊处理：

- 关键区域未知或缺少有效边界：补充测量，不输出确定时间。
- 密度不满足：不能用更长等待时间掩盖。
- 卷发区分视觉长度与拉直测量。
- 首版不自动推算断发或修剪损耗，明确未计入。
- 复访实测保存为时间序列，数据足够后再建立个人估算。

字段：zone_gaps、month_min、month_max、assumptions、blocking_conditions、transition_notes、stylist_confirmed。

## 14. 审核、调整和发布

主要按钮：通过／调整后重做／不适合。

原因多选：脸变了、肤质变化、发际线变化、长度不足、密度不足、发质不支持、刘海问题、顶部过高、两侧过宽、后区问题、打理复杂、顾客不喜欢、图像错误、视角不一致。备注选填。

调整项：

- 刘海更长、更短、更薄、露额。
- 两侧更贴合、保留体积、露耳。
- 顶部降低蓬松、增加纹理。
- 后区更短、保留长度、调整轮廓。
- 整体更自然、更利落、减少变化。

版本与审核规则：

1. 改图或改结构生成新 candidate_revision。
2. 新版重新检查、评分和审核。
3. 审核绑定确切候选版本和 profile_revision。
4. 改照片或关键条件，旧结果标记 stale，不用于新发布。
5. 发布事务检查授权、版本、审核、硬约束、图片总数。
6. 发布生成不可变快照，后续变更创建新发布版本。
7. 旧快照访问可撤销，删除请求优先于保留审计图片。
8. 批量通过只适用于已查看且无未解决问题的候选。

顾客卡片：效果图、模式、理由、所需服务、打理要求、留发范围、AI 预览标识。分数放详情并说明为适配分，不是颜值分。

## 15. 技术架构

推荐：React＋TypeScript＋Vite；FastAPI＋Pydantic；PostgreSQL；Celery＋Redis；国内私有对象存储；容器化＋HTTPS。

~~~mermaid
flowchart TD
    A[网页] --> B[业务API]
    B --> C[(PostgreSQL)]
    B --> D[任务队列]
    D --> E[Worker]
    E --> F[Qwen适配器]
    E --> G[Seedream适配器]
    E --> H[(私有对象存储)]
    A --> I[受控资产访问]
    I --> H
~~~

- 浏览器不持有模型密钥。
- 长任务在 Worker，持久状态存 PostgreSQL，Redis 不是唯一结果库。
- 首版轮询即可，停止轮询不等于取消任务。
- 私有图片使用短期授权或代理访问，不开放公共桶。
- 下载供应商结果校验协议、域名、重定向，禁止任意内网访问。
- 不需要微服务、独立向量库或自部署模型。
- PWA 安装能力可选，不自动缓存顾客照片为离线数据。

~~~text
salon-style-assistant/
  apps/web/
  backend/app/api/
  backend/app/models/
  backend/app/schemas/
  backend/app/services/
  backend/app/providers/
  backend/app/workers/
  backend/app/rules/
  backend/migrations/
  catalog/styles/
  prompts/analysis/
  prompts/planning/
  prompts/generation/
  prompts/evaluation/
  tests/unit/
  tests/integration/
  tests/e2e/
  docs/
  infra/
  .env.example
  README.md
~~~

## 16. 数据模型

时间按 UTC 存储，门店显示 Asia/Shanghai；适用实体包含门店归属、创建更新时间。

| 实体 | 核心字段 |
|---|---|
| salons | id、name、settings、budget_policy |
| users | id、salon_id、role、login_identity、status |
| consultations | id、salon_id、stylist_id、customer_code、status、current_profile_revision |
| consents | consultation_id、purpose、status、text_version、confirmed_at、operator_id |
| assets | id、salon_id、consultation_id、kind、view、storage_key、hash、width、height、status |
| profile_revisions | consultation_id、revision、fields、sources、confirmed_by、confirmed_at |
| style_templates | id、version、spec、references、review_status |
| candidates | id、consultation_id、mode、template_id、template_version |
| candidate_revisions | candidate_id、revision、profile_revision、style_spec、asset_ids、status |
| evaluations | candidate_revision_id、rubric_version、gate_status、dimensions、total_score、evidence |
| reviews | candidate_revision_id、reviewer_id、decision、reason_codes、notes |
| jobs | id、consultation_id、type、stage、status、input_revision、attempt、error、heartbeat |
| model_calls | job_id、provider、model、prompt_version、request_id、duration、usage、cost_status |
| budget_reservations | consultation_id、call_id、reserved_amount、settled_amount、status |
| deliveries | consultation_id、version、type、snapshot、asset_ids、status、published_by |
| feedback | consultation_id、candidate_revision_id、type、values、operator_id |
| audit_events | actor、action、resource、timestamp、sanitized_metadata |

规则：建议与确认值分开；审核绑定版本；唯一约束防重复；事务保护预算与发布；日志不保存 Base64、密钥、完整临时地址；不把人工选择覆盖成模型原始分数。

## 17. 业务 API

接口前缀 /api/v1。下表是业务接口，不是厂商接口。

| 方法与路径 | 功能 |
|---|---|
| POST /auth/login | 登录 |
| POST /auth/logout | 退出 |
| POST /consultations | 新建咨询 |
| GET /consultations | 咨询列表 |
| GET /consultations/{id} | 咨询详情 |
| POST /consultations/{id}/consents | 保存用途确认 |
| POST /consultations/{id}/uploads | 创建受控上传 |
| POST /consultations/{id}/assets/complete | 验证对象并登记 |
| POST /consultations/{id}/analysis-jobs | 照片分析 |
| PUT /consultations/{id}/profile | 条件确认和新版本 |
| POST /consultations/{id}/generation-jobs | 规划生成 |
| GET /jobs/{id} | 阶段与结果 |
| POST /jobs/{id}/cancel | 取消后续任务 |
| GET /consultations/{id}/candidates | 候选与版本 |
| POST /candidates/{id}/revision-jobs | 点选调整重做 |
| POST /candidates/{id}/view-jobs | 补视角 |
| POST /candidates/{id}/reviews | 审核指定版本 |
| POST /consultations/{id}/deliveries | 发布快照 |
| POST /deliveries/{id}/presentation-session | 创建受限展示会话 |
| GET /presentation | 展示会话读取快照 |
| POST /consultations/{id}/feedback | 保存反馈 |
| DELETE /consultations/{id} | 发起删除 |

生成请求：

~~~json
{
  "profile_revision": 3,
  "modes": ["current", "grow_out"],
  "target_style_counts": {"current": 3, "grow_out": 3},
  "max_delivery_images": 9
}
~~~

异步返回 202：

~~~json
{
  "job_id": "job_example",
  "status": "queued",
  "profile_revision": 3
}
~~~

审核提交 candidate_revision、profile_revision、decision、reason_codes。条件保存使用 expected_revision 做乐观锁。

幂等：生成、重做、补视角、发布支持 Idempotency-Key，范围包含门店、咨询或操作者、操作类型。相同键和相同内容返回原结果，相同键不同内容返回 409。

~~~json
{
  "error": {
    "code": "PROFILE_REVISION_CONFLICT",
    "message": "顾客条件已更新，请刷新后重试。",
    "retryable": false,
    "request_id": "request_example"
  }
}
~~~

必要错误码：

PHOTO_QUALITY_BLOCKED、CONSENT_REQUIRED、PROFILE_INCOMPLETE、PROFILE_REVISION_CONFLICT、MODEL_NOT_CONFIGURED、MODEL_UNAVAILABLE、SCHEMA_INVALID、PROVIDER_RATE_LIMITED、PROVIDER_RESULT_UNKNOWN、BUDGET_EXCEEDED、INSUFFICIENT_CANDIDATES、REVIEW_REQUIRED、DELIVERY_IMAGE_LIMIT、ASSET_DELETED。

适当使用 401/403/404/409/422/429/503，不把所有失败返回 200。跨门店资源可以统一 404 避免枚举。

## 18. 状态、并发和恢复

咨询：

~~~text
draft → collecting → ready → generating → review_ready → delivered → closed
                              ↓
                         partial / failed
可删除状态 → deleting → deleted
~~~

已发布咨询重新编辑形成新工作版本，原发布快照独立存在。阶段预览用 delivery_type=preview。

任务：

~~~text
queued → running → succeeded
                 → partial
                 → failed
                 → cancelled
                 → provider_result_unknown
~~~

- Worker 具备租约、心跳、重入检查，不能假定队列天然 exactly-once。
- 本地事务和外部调用不能组成同一事务，记录 submitted、request_id 和不确定结果。
- 旧版本任务完成可归档，但不能覆盖当前候选或发布。
- 取消只停止未开始步骤，不能保证撤销供应商调用或计费。
- 并发度按限流、预算和容量配置，先保守运行后实测调整。

## 19. 重试与成本

| 情况 | 处理 |
|---|---|
| 非法 JSON/Schema | 最多一次修复 |
| 明确限流或可重试错误 | 有限退避重试，遵循 Retry-After |
| 无权限、缺密钥、模型不存在 | 不重试，配置错误 |
| 图像质检失败 | 最多一次自动修复生成 |
| 超时但可能已执行 | 标记 unknown，核对结果，不无限重发 |
| 厂商图下载失败 | 有效期内重试下载，不直接重新生图 |
| 条件版本变化 | 旧结果过期，不继续无意义消耗 |

预算：

- 默认 18 次图像尝试，包含侧面、失败、人工重做。
- 同时配置金额上限，没有价格和预算配置时禁用真实付费生成。
- 调用前原子预留金额与尝试额度，结束后按可核实计费结算。
- 未知费用保留预留或待核对，不按免费处理。
- 并发预留不能超过余额；追加预算需明确点击与权限。
- 厂商实际计费和应用估算分开，账单核对后更新。

~~~text
完整咨询成本 =
分析规划 + 全部生成尝试 + 质检评分 + 存储传输
~~~

同时展示咨询成本、合格方案成本、重试率、阶段耗时和未核对费用。

## 20. 数据使用和安全

本节是工程要求，不替代正式上线时对适用规则和供应商条款的核实。

- 顾客代号足够，不强制姓名、手机号。
- 本次设计、长期保存、改进模型、公开案例分别确认。
- 告知使用 Qwen 与 Seedream，不默认增加处理方。
- 不建立跨顾客人脸识别库，不搜索身份。
- 不抓取未授权的人像补全资料。
- 私有存储、加密传输、短期授权；校验上传对象归属。
- 删除立即撤销访问，后台清理原图、副本、缩略图、效果图和交付资产。
- 备份周期、厂商保留政策单独记录，不承诺外部系统随本地删除立即清除。
- 展示会话超时、退出、撤销后不可继续访问。
- 图片文字、外部素材中的指令都视为数据，不得覆盖系统约束。
- 日志不记录密钥、原始图片和不必要的个人内容。

## 21. 指标与反馈

事件：

consultation_created、consent_confirmed、photos_ready、profile_confirmed、generation_started、candidate_ready、candidate_rejected、candidate_approved、delivery_published、customer_selected、actual_result_added、consultation_deleted。

记录必要 ID、时间、版本、原因枚举，不向分析服务发送照片或完整个人资料。

仪表盘：

- 条件确认、首张可审图、整组图片的耗时。
- 生成失败率、重试率、原貌问题率。
- 直接通过率、修改后通过率和拒绝原因。
- 顾客选择、沟通耗时、实际效果反馈。
- 完整咨询成本、合格方案成本、模型调用分布。

分母保留全部进入对应阶段的咨询和候选，不删除失败样本再计算。

反馈记录可做性、调整、顾客喜欢程度、是否执行、实际偏差。AI 评价、发型师评价、顾客选择分别保存。

后续模型对比固定输入和方案结构，一次改变一个主要因素；盲评隐藏厂商和模型名称。

## 22. 验收标准

### 22.1 功能和工程硬性标准

| 编号 | 验收 | 预期 |
|---|---|---|
| AC01 | 点选主流程 | 正常操作无需文字输入 |
| AC02 | 双模式 | 各自生成和排名 |
| AC03 | 完整交付 | 至少 3 款，默认两类各 3，数量不足明确提示 |
| AC04 | 图片数量 | 发布事务强制 ≤9，包含侧面 |
| AC05 | 审核隔离 | 顾客接口无法获取未审核或拒绝资产 |
| AC06 | 条件更新 | 旧候选过期，旧任务不覆盖新版 |
| AC07 | 重生成 | 新版必须重新审核 |
| AC08 | 项目约束 | 拒绝烫发时不交付依赖烫发的方案 |
| AC09 | 时间估算 | 未知长度、密度不足不产生虚假时间 |
| AC10 | 幂等 | 重发不重复创建同一业务任务 |
| AC11 | 恢复 | 刷新后恢复进度和结果 |
| AC12 | 并发预算 | 不因并发申请超预算 |
| AC13 | 门店隔离 | 无法访问其他门店资源 |
| AC14 | 删除 | 立即不可访问，后台完成清理 |
| AC15 | 演示区分 | 模拟结果不能进入真实交付 |
| AC16 | 异常 | 配置错误、结果未知有明确状态，无无限重试 |

### 22.2 待实测的初始目标

| 指标 | 目标 |
|---|---|
| 主要条件确认 | 中位数 ≤60 秒 |
| 首张机器质检后可审图 | P50 ≤90 秒 |
| 默认六张主图生成与机器检查 | P50 ≤3 分钟，P95 ≤6 分钟 |
| 发型师直接接受率 | 首轮争取 ≥70% |
| 最终交付明显改变原貌 | 审核阻断，目标零 |

生成时间从提交起算，包含排队、检查和必要重试，不包含人工审核。小样本应报告数量和原始分布，不把不稳定 P95 当成熟服务承诺。

先完成 10～15 次咨询验证流程，再完成约 40～60 次覆盖不同长度、发质、密度的测试，并保留部分样本复测。该规模不证明普遍适用。

## 23. 测试计划

### 单元测试

- 长度边界、未知和开放区间、单位、负数。
- 留发关键区域、向外取整、零等待。
- 权重和为 100、分数范围、null 传播、不同模式。
- 硬约束、条件性服务、去重、图片计数。
- 不支持的供应商参数不发送。

### 集成测试

- 迁移、乐观锁、幂等键冲突。
- 并发预算预留、未知费用、补偿。
- Worker 重入、断线、取消、旧结果。
- 审核发布事务、资产归属、跨门店和删除。

### 端到端测试

- 模拟供应商跑通上传→选择→生成→审核→展示→反馈。
- 拒绝、重做、改条件、刷新、超预算分支。
- 手机、平板、桌面，以及拒绝相机后的兜底。
- 少量已授权照片做真实 API 冒烟，记录版本和费用；照片不进测试仓库。
- 生产不得因供应商失败自动降级为模拟成功。

## 24. 开发阶段与交付物

| 阶段 | 内容 | 完成依据 |
|---|---|---|
| M0 | Schema、枚举、状态机、配置、模板格式 | 合同可校验 |
| M1 | 登录、咨询、授权、上传、点选、演示 | 演示端到端且标识清晰 |
| M2 | Qwen、模板规划、Seedream、存储、队列 | 授权照片产生真实结果 |
| M3 | 评分、留发、去重、调整、审核、发布 | 审核和版本边界生效 |
| M4 | 幂等、预算、权限、异常、删除、监控 | 硬性验收通过 |
| M5 | 门店试点、反馈、实际效果、修复 | 完成首轮报告 |

按一名熟悉技术栈的全栈开发、兼职产品/设计和持续参与的发型师，可先按 4～6 周安排试点版；这是规划估算，依赖账号、模板和反馈准备情况。

交付必须包括：

1. 前后端源码、依赖锁文件。
2. 不含密钥的环境变量示例。
3. 迁移、演示种子、模板导入校验。
4. 提示词、评分、增长参数及版本。
5. 可重复的运行方式，例如 Docker。
6. 本地运行、真实模式、备份恢复、删除、排障说明。
7. 自动测试结果、真实冒烟记录和未验证项。
8. 门店试点操作说明和反馈表。
9. 已知限制，不把未验证效果写成已完成能力。

## 25. 后续扩展触发条件

- 顾客反复需要到店前上传、带走方案和复访更新时，增加微信小程序，复用后端。
- 有固定评测集、可靠发型师反馈和授权数据后，再比较模型或定制。
- 业务规模、成本和质量支持后，再评估自部署。
- 不先扩展预约支付等周边功能来掩盖核心效果不稳定。

## 26. 官方依据与接入前核实

以下用于核实能力和背景；工作流、权重和阈值是本项目设计，不是厂商保证。资料核对日期为 2026-11-11，实际接入以当前官方文档和账号权限为准。

- [Qwen3-VL-Plus 模型](https://help.aliyun.com/zh/model-studio/qwen3-vl-plus)：输入输出和区域能力。
- [Qwen 结构化输出](https://help.aliyun.com/en/model-studio/qwen-structured-output)：JSON Object、Schema 和适用模式。
- [Seedream 图片生成 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)：子版本参数、多图输入、尺寸和返回值。
- [Seedream 生成教程](https://docs.volcengine.com/docs/ark/image-generation-tutorial?lang=zh)：系列版本和调用方式。
- [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)：安全上下文和相机授权。
- [CDC/ATSDR Hair Analysis Panel Discussion](https://atsdr.cdc.gov/HAC/hair_analysis/hair_analysis.pdf)：生长速度一般背景，不构成个人预测。

开工前核实：模型账号与区域、具体版本可调用、参数支持、价格预算、私有存储、模板素材授权、真实照片授权和发型师参与。缺失项明确记录，可独立完成的工作继续推进。

## 27. 可直接复制给开发 AI 的任务指令

> 请阅读本文件，在独立项目目录实现沙龙 AI 发型设计助手 MVP。先检查工作区规则和现有代码，不修改无关项目。遵循发型师点选确认、审核后交付、Qwen3-VL-Plus＋固定 Seedream 5.0 基线、双模式、版本化审核、最多 9 张交付图片的要求。按 M0～M5 推进，先给简短实施安排后直接开发，合理可逆的细节自行决定。没有密钥时完成清晰标识的演示模式、真实适配器和测试，不伪造真实调用。每阶段运行对应测试并修复问题。最终提供可运行代码、启动方式、测试证据、未验证项和试点步骤，不要只给方案或静态页面就宣称完成。

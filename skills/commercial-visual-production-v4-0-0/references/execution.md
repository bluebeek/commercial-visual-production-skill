# V4 生图执行与最小修改

## 零调用准备

1. `workflow.py init --project <目录> --project-id <标识>` 建立 V4 项目，默认调用额度为 0。正式提交 R0–R2、来源、要求和真实蓝图决定；使用 `stage_context.py` 恢复上下文。
2. `doctor.py --host codex|claude-code|cursor|chatgpt|claude-chat|gemini-chat` 只盘点环境和密钥是否存在，不输出密钥。宿主技能发现和完整运行仍须独立实测。
3. `model_catalog.py refresh --provider openai|google --catalog <项目>/model_catalog.json` 实际下载官方日期发布记录，不调用生图。`resolve` 依据发布日期解析最新型号；默认质量档，可选 speed。源文档和校验值随快照保存。
4. 模型目录有效期 30 分钟。每次真正 API 执行还会再次抓取官方记录；型号或能力变化须重新准备。未知新代不继承旧代参数，不自动回退。

## prepare／execute／finish

`production.py <动作> --project <目录> --input <助理整理的 JSON 文件>`。

prepare 保留 id、kind（background／asset／whole／local-edit）、goal、spec、notes、transparent_background、baseline、change_request、feather、input_images 等含义。新增 provider（默认 openai）、catalog（默认 model_catalog.json）、model_profile（默认 quality）、quality（OpenAI 默认 medium；Google standard）、maximum_cost_usd 和 cost_quote。

input_images 按实际顺序列 path／role／description。局部编辑第一张必须是已选的工作基准。蓝图、锁、尺寸、原件和当前要求沿用原校验。参数不得为适配模型而偷偷缩放、去底或删附件。

每个任务保存平台无关 request.json、输入及要求哈希、独立 model_catalog 快照与 source 文档、工具清单 tool_args.json。瞬时 HTTP 请求体由官方适配器生成；OpenAI 文生图走 Images generations，多图编辑走 Images edits；Google 走原生 Interactions。首版只收单张最终 PNG，不开启搜索、流式预览或额外生成工具。

execute 输入 job_id、inspected_images（实际已查看图片的顺序哈希）、intent_review（covered_requirement_ids、unresolved 空数组、具体观察）。执行器检查环境凭据和 latest、编译请求、begin、预算预留，随后仅发起一次请求。OpenAI 读取 OPENAI_API_KEY，Google 读取 GEMINI_API_KEY；不自建私有桥接或要求在云端上传密钥。

prepare 与 begin 不证明服务已处理；成功返回也须独立解码、核对尺寸、真实 Alpha、请求与输出哈希、模型信息以及 receipt，再进入 generated。响应没给实际型号就记 NOT_EXPOSED。generated 只是未审核产物，后续仍须 materialize、revision 和 R4–R6。

## 费用与未知结果

开发、模拟测试和模型解析均不消耗生图额度。真实调用是独立的可选验证活动；16 次／10 美元只作为历史讨论的可选上限，不是开发费用或默认付款授权。

预算在项目外建立：`budget.py init --ledger <路径> --calls <明确上限> --usd <明确上限>`，默认 0／0。`bind --project <目录> --ledger <原共享账本>` 建立单一执行资格。所有验证项目共同计数。不得因复制、分支或移交重置账本。每次请求最大费用为正数，已返回但费用未知时仍占预留，不记 0。

production prepare 的 cost_quote 是项目内保守上界文件，字段 kind=operator_conservative_bound，model、size、quality、alpha、input_hashes 必须与任务一致；另含 maximum_usd、pricing_source（官方网址）、basis（具体估算依据，至少 20 字符）。它是执行者有来源的费用判断，不是服务商账单或自动精确报价。实际价格或上界无法合理核对时不执行；凭据、额度和费用规则需在真实验证前落实。

transport 超时和 HTTP 5xx／408 保持 result_unknown。未知请求不得直接再次 execute；账本不退款、不自动释放。读取服务端请求／账单证据后，用 recover 输入 job_id、evidence_file、response_file（保存的状态码及原始响应 JSON），或 failed=true 明确恢复失败。恢复不发网络请求；保留原次数并重新核验产物。无法恢复时继续保留阻断。

测试项目可使用明确的 fixture 目录和注入 transport，不能调用真实服务。生产项目禁止注入模拟 transport。模拟通过不记作真实模型验证。

## 原件、局部保护与审核

`prepare-source`、`prepare-compose` 继续用于源层替换和已有产物的合成修正，不加生图次数。`prepare-editor/begin-editor/finish-editor` 的 PhotoCraft 独立预算与原始输出保护规则保留。原件、准确文字、已有补丁和工作基准不能因为换供应商而丢失。

materialize 保留原图、采用图、区域和栅格补丁来源。检查修改目标、接缝、非目标区和历史分别通过；任何一项失败都不得用其他项的通过掩盖。R4 检查、R5 修复复核、候选接受、冻结与 R6 交付仍分别登记。

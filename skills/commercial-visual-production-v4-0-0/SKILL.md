---
name: commercial-visual-production-v4-0-0
description: 商业视觉生产候选：参考解析、品牌转译、蓝图、最新模型生图接入、受控局部修改、PhotoCraft 分层验收及 PNG/ORA 交付。支持平台能力检查和项目移交；只有实际通过的宿主与接口才声明兼容。
metadata:
  version: "4.0.0-rc.1"
  language: zh-CN
  validation_scope: "candidate-script-and-simulated-provider-contracts; see validation report"
  environment: "Python 3.10+, Pillow, NumPy; optional API credentials/network; PhotoCraft MCP for full acceptance"
---

# 商业视觉生产 V4 候选

R0 参考观察 → R1 采用／改写／舍弃 → R2 创意与蓝图 → R3 制作 → R4 核验 → R5 最小修复与冻结 → R6 交付。沿用现有九模块边界、源层合成、硬锁与审核机制。不要把候选接入、模拟接口或可上传的包说成全平台已验证。

## 按当前任务读取

- R0–R2：`references/stages.md`。单项输入先记草稿；正式 R0 仍须九模块完整。R0 不做品牌采用，R1 不生成布局。
- 生图与连续修改：`references/execution.md`。V4 默认 `model_policy=latest`；用官方发布记录解析型号，助理无需让用户逐次填型号。
- 平台运行与移交：`references/platforms.md`。先盘点能力；目录存在、CLI 版本或脚本通过均不能代替实际宿主调用。
- PhotoCraft 编辑／验收：`references/photocraft.md`。只使用公开 MCP；首版编辑范围仍为已有像素层的限定矩形填色。
- R4–R6：`references/review-delivery.md`。保留机器检查、视觉判断、候选接受、冻结和交付验收的独立记录。

## 共同规则

- `workflow_state.json` 是权威状态，V4 使用 `cvisual.workflow.v4`。从完整 `stage_context.py` 上下文恢复要求、来源、有效蓝图和具体基准；关键未知和陈旧来源不得放行。
- 准确文字、产品、身份和 Logo 优先使用有来源的真实原件与文字栅格层。错字走源层替换，接缝先调整合成；需要视觉重建才请求生图，布局变化返回 R2。
- 生图通过 `production.py prepare/execute/finish`；准备不是生成。任务按原始素材顺序与哈希、当前要求、基准、区域、适配器及 latest 证据绑定。所有参考图须先实际查看，助理核对语义覆盖后执行。
- 开发默认调用额度 0。真实 API 需账户凭据、任务对应的保守费用依据，以及项目外共享预算账本。先检查是否会新增支出；内置套餐额度与 API 费用分别记录，不把试验上限当必付金额。凭据只在执行端环境变量中读取，不能写入项目、日志或上传包。
- 最新型号不满足任务能力、接口尚未适配、权限未知或预算不足时阻断，不降级旧代。内置生图未暴露型号时记 `NOT_VERIFIABLE`，不能用它证明 latest。新模型不会自动开放 SVG、动画或其他未验收路径。
- 官方 API 执行器只有一次 POST，不自动重试。超时或服务端处理结果不明时保留未知和费用预留；先用真实服务记录恢复，不盲目重放。模拟任务不能访问真实生图服务。
- 真实原图和采用图分别留存。用 `materialize.py` 执行原件合成和局部硬锁，保留已有补丁、历史和分支。区外 RGBA 零差异不等于修改目标或接缝通过；补丁不能冒充源层重建。
- PhotoCraft 缺失时，完整验收继续阻断；可准备草稿或移交项目，不改用 Krita／Affinity。机器通过不等于用户接受；助理意见不得冒充用户决定。
- 新候选待审核，P0／P1、关键未知、过期机器证据均阻断冻结。只有明确当前候选接受、有效冻结和未变化交付文件，才能登记交付验收。
- 迁移与移交保留旧文件和证据身份。V3 使用只读查看或导入新目录，历史批准不成为新候选批准；移交不复制执行资格或剩余预算。不要修改现有全局 V3.1 安装副本。

用户无需手写内部 JSON。由助理根据已有信息登记任务与证据，只询问缺失且影响实际执行的信息。报告实际完成范围、阻断和产物位置，不把未测能力写成已实现或已通过。

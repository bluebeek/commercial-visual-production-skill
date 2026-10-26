---
name: commercial-visual-production-v3-1-0
description: 商业视觉生产V3：九模块参考解析、品牌转译、文字或草图蓝图、受控生图、连续局部修改及PNG/ORA验收；PhotoCraft受控编辑与引擎验收；通过项目文件继承当前要求和版本。
metadata:
  version: "3.1.0"
  supersedes: "commercial-visual-production-v3-0-0"
  validation_scope: "versioned-script-and-photocraft-engine-evidence"
  language: zh-CN
---

# 商业视觉生产 V3.1.0

用户流程：R0参考解析 → R1品牌转译 → R2创意/草图与蓝图 → R3视觉生产 → R4核验 → R5最小修复与冻结 → R6交付。R4→R5→R3→R4形成返工闭环。根据项目选择整图或分层；严格产品/人物/Logo保真及准确文字使用真实原件合成。默认仅在蓝图、候选接受和交付验收取得用户决定；明确的新修改已经授权其作用范围，不重复询问。

## 按需读取

- R0–R2首次读 references/stages.md。R0九模块只分析参考，R1采用/改写/舍弃，R2才形成项目蓝图。
- R3及返图读 references/execution.md。实际AI入口仅内置image_gen.imagegen；用户称Image 2.5，工具未公开具体后端model，不自造参数。
- PhotoCraft确定性编辑或分层验收读 references/photocraft.md。生图仍用独立image_gen入口，PhotoCraft操作不占生图预算。
- R4–R6、旧项目迁移读 references/review-delivery.md。
- 不每轮读全包；compat/v2仅用于旧项目诊断及原70项回归，不能混用旧阶段编号或复制批准。

## 贯穿执行

- workflow_state.json是唯一权威项目记录；scripts/workflow.py登记来源、规则、阶段、版本、问题及决定。阶段摘要和提示由它生成。每条必须继承的素材说明、准确文案、保护项、海报注意事项都整理为带来源和作用范围的要求；notes只放本轮补充，不把长期要求藏在临时备注中。
- 先构建stage_context.py上下文。只有本轮仍持有完整旧上下文才能使用--since；恢复会话从完整上下文读取。文件/规则过期先更新受影响输入，关键UNKNOWN不能放行。字符软预算不截断文案和关键要求。
- 生成任务的提示必须经过production.py prepare及begin：校验有效R1/R2、真实蓝图决定、基准、附件顺序、当前要求覆盖和助理语义核对；每次实际prompt自动带相关禁止事项。用户要求的颗粒/笔触等优先保留，避免无依据审美禁令。编译或排队均不代表生图完成。
- 助理读取已保存的tool_args.json，先查看全部本地输入图，然后按相同参数调用内置image_gen。记录真实结果；实际尺寸/透明不符即失败，不偷偷缩放。相同失败不无限重试，项目调用预算包含失败。
- 文字/源图层或合成参数问题优先用prepare-source/prepare-compose的原生路径，不增加生图调用。生成后materialize.py将原件/文字层与生成素材合成；局部修改执行真实硬锁并形成可追溯补丁。revision登记实际产物后进入核验。补丁是栅格补丁，不能声称重建了完整背景或原生文字层。
- 连续返图始终选择明确基准，继承当前有效要求和此前成果，只加入本轮差异。新候选保持待接受；通过与用户接受分别记录。发现指代多版歧义才补问。范围外RGBA相同只证明像素保护，仍要检查修改目标、接缝和以前改过的内容。
- checks.py run真正运行检测；助理基于实图记录语义观察。修复提交只待复核，P0/P1和关键未知阻断冻结；P2只能接受当前版的明确非关键问题。测试项目只记录测试决定。
- PhotoCraft编辑由prepare-editor/begin-editor/finish-editor绑定实际文档、图层、矩形及工具记录；先检查原始输出无越界，再生成限定范围栅格补丁。工具不可用时阻断，不切换Krita/Affinity。
- 新项目须完成checks.py verify-editor的PhotoCraft机器验收；导入警告、逐层内容、回存与证据时效都要检查，人工及P2例外不能覆盖此项。
- R6从有效批准母版导出PNG/ORA，并实际重读、重组对比；PhotoCraft引擎通过与桌面GUI未测分别报告。ORA是栅格分层；PSD、活文字、印刷和目标编辑软件打开性仅报告实际验证范围。

向用户报告实际结果、问题、下一动作和产物位置。完整历史和证据留在项目，不复述全部分析。不要让用户手填内部JSON；由助理根据已提供信息建立记录，只询问缺失且影响执行的内容。

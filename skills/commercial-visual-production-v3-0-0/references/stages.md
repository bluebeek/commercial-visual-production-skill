# R0–R2输入、来源和蓝图

Python 3.10+，Pillow、NumPy。所有项目资料放在独立项目目录。命令以scripts/下的文件为入口；先workflow.py init --project <目录> --project-id <稳定编号> --call-budget <本批上限>。测试另加--test-mode；不能把测试决定转成商业批准。

所有写动作使用workflow.py <action> --project <目录> --input <项目内JSON>。数据契约如下；助理整理文件，用户只提供设计资料。

## R0 九模块

stage输入为stage=R0、data={references:[{path,role}],observations:[{id,module,text,certainty,evidence_file}]}，可带evidence_files。module覆盖1–9；certainty为observed/estimated/unknown。实际观察必须指向已登记的真实参考图。可记录可见位置、估计比例与未知字体，但不把观察变成项目布局。

1. 视觉风格：媒介、调性、表现语言和复杂度。
2. 设计排版：焦点、层级、对齐、留白、尺度和阅读路径。
3. 素材处理：可见抠图、剪切、拼贴、变形和边缘；看不见的制作过程保持推测。
4. 色彩系统：面积、明暗、饱和度与对比；视觉估计不冒充官方色值。
5. 字体与文字：字形、字重、间距、层级；看不清的字体家族保持未知。
6. 光影与材质：光源、阴影、反射、质感和焦点贡献。
7. 空间关系：前后、遮挡、透视和动势。
8. 图形与装饰：纹理、符号、线条、节奏及功能；不自动推导全部禁令。
9. 视觉机制综合：解释以上特征如何协作，只总结参考本身。

## R1 品牌转译与规则

先用asset登记每个真实素材：id/path/role/description/description_source(user或observed)，must_keep、allowed_changes均为文本数组。观察得到的描述不能冒充用户授权。文件和素材ID不可覆盖；更新素材使用新版本ID。

stage R1 data只包含purpose、asset_roles(素材ID数组)、decisions、notes。decisions对每个R0观察各列observation_id、decision(adopt/adapt/reject)、reason。品牌文件/用户用途和规范列入evidence_files。此阶段不创建布局。

requirement动作保存有效项目要求：

| 字段 | 意义 |
|---|---|
| id、scope、property | 稳定要求ID、对象ID或project/canvas、属性名 |
| text、verification | 完整制作要求和验证方法；准确文案原样保存。verification=geometry时必须另有真实观察的几何检测 |
| source | kind=user/brand/translation，quote原话；translation还带observation_id |
| evidence_files | 实际来源文件；对话中的要求可由助理如实摘录为项目来源文件 |
| method | prompt/composite/both，对应生图说明、原件/排版或二者 |
| status、critical | active/rejected/unknown；critical默认true |
| supersedes | 替换的旧要求ID数组，只能替换同对象同属性的有效项 |
| impact_stage | R1/R2/R3；默认R3。品牌基础或布局变化分别使R1/R2需要更新 |

参考只有R1采用/改写后才能作为translation要求。新要求与旧要求冲突时，明确替换对应ID；外部brand规则冲突需要具体更新依据。语义去重和新旧要求解释由助理核对，程序不声称能理解所有自然语言矛盾。项目特殊负面要求也作为当前有效要求存储，进入实际提示；不只放旁边的负面词文件。

## R2 创意/草图与规划

stage R2 data={creative_input:{kind:text/sketch/mixed,text,path},spec,preview,planned_assets,notes}。text/mixed需要原始创意文字，sketch/mixed需要实际草图。spec与preview为项目内路径。蓝图JSON兼容已有canvas/elements/constraints/editable_regions/protected_regions/color_checks字段；box=[x,y,w,h]，区域rect=[x0,y0,x1,y1]，支持polygon。轴对齐之外的变换不自动支持。

R2可列待生成素材ID，但受保护的真实原件不能靠占位图通过。运行blueprint.py --spec <文件> --out <目录> --mode draft得到结构预览；此时尚未生成的背景不形成循环前置条件。正式生产素材完整性在materialize/版本登记时再次检查。样式和项目意图写入requirement，避免同时在蓝图style_rules中保存相冲突的副本。

展示结构预览与当前要求，用户确认后执行confirm-blueprint，数据为actor=user、reason和evidence_files。程序自动绑定当前蓝图与预览。用户明确要求修改已有布局时，更新相关规则/R2，并用真实新要求记录其范围的确认依据，不再重复索取相同授权。不能用旧批准自动确认未涉及的新设计。

stage_context.py build --project <目录> --stage R3返回完整有效要求、R1/R2、基准和缺口，不发送原始R0全部观察。--since <context_id>只用于仍持有完整旧上下文的同一执行环境；新会话省略。未知关键项、来源变更和阶段过期均须处理，缓存永远不是批准。

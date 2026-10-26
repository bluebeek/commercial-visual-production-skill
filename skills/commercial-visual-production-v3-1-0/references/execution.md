# R3生成与连续返图

production.py的prepare/begin/finish均通过--project和--input读写项目。网页登记任务只排队，当前对话助理才有内置image_gen能力。

## prepare

输入id、kind(background/asset/whole/local-edit)、goal；可带spec(默认批准R2)、notes、transparent_background、input_images。input_images按真实传入顺序列path/role/description。需要图片条件时只引用实际可传入的图。背景/独立素材/整图均记录其真实交付角色；不要把含字候选误套背景禁字规则。

局部编辑可用feather指定0–200像素的区域内羽化，默认0；精确选区保存在composition_plan.json，多边形在模型提示中仅显示紧凑的位置说明。局部编辑另带baseline、change_request、与基准同结构但拥有明确editable_regions的spec。第一张图role=baseline，内容必须是所选工作版本。先workflow.py select明确工作基准；restore_requirements默认true，将其有效要求恢复，接受指针不会自动改变。后续新要求通过supersedes加入。局部修复spec通常复制基准spec，仅修改编辑区和允许过渡区；不要丢掉已有补丁层。明确要求的整体调整可设置allow_global_adjustment=true替换禁止整体调色的局部默认约束；范围和保护核验仍适用。

长期注意事项、用户禁令和准确文案必须整理为requirement；notes只描述本轮临时补充。素材说明复用asset记录，只追问未提供/不明确部分。

编译顺序：任务/用途 → 实际图像角色 → 几何与层级 → 当前有效要求 → 原件说明 → 本轮变化和以前成果 → 注意事项 → 内置负面约束 → 输出。不要把全部聊天、过期提示、R0未采用特征或内部补丁ID当视觉对象发送。基础约束禁止非预期新增内容和伪影，保留明确颗粒/笔触等设计效果。精确坐标是制作目标，实际结果仍需检查。

## begin与实际调用

prepare产出production/<job-id>/tool_args.json和prompt.txt。助理检查源意图到提示/合成再到核验的coverage；核对角色、文案和新旧要求没有语义冲突。若只凭程序结构检查还无法判定，先补问具体缺失，不制造新审美限制。

先用view_image查看所有本地输入图片，再begin：{job_id,tool_args:<原文件内容>,inspected_images:[按顺序的图片SHA256],intent_review:{covered_requirement_ids:[本轮coverage全部ID],unresolved:[],observation:<实际核对说明>}}。begin核对参数和文件后计入调用预算。只在实际准备调用时begin；如果中断，先核对实际工具记录，不能无记录地重放running任务。

助理直接将begin的args传给内置image_gen.imagegen。实际接口只有prompt、图片引用及transparent_background等公开字段，不编造model/negative_prompt/seed/steps/CFG/mask。禁止事项必须在prompt内。没有图片的新生成省略图片引用；编辑本地图片使用referenced_image_paths。工具未公开后台型号，因此不能验证所谓Image 2.5的具体版本。

工具成功后将真实原图复制进项目，finish记录{job_id,output,tool_metadata}；缺少工具ID时留空，不自造。失败记录{job_id,error}，调用计数不退回。失败或尺寸/透明不符不能冒充成功；同一job只能begin一次。每次实际图像调用都消耗项目预算，不能为通过测试悄悄追加预算。

## 原件、局部保护与版本

materialize.py --project <目录> --job <ID> [--target-element <ID>]从真实产物完成原件层合成。背景/whole默认填入唯一背景槽；whole的该层是整张候选栅格，不声称语义背景分离。asset需选择对应的非保护元素槽。需要与原构图不同的独立素材画布时先为该任务建立对应蓝图，不能假装任意尺寸已受支持。

局部materialize调用locked_edit.py，保证编辑区外RGBA与基准相同，并建立独立全画布透明补丁层。已有层保留，补丁有原图、区域及任务来源。当前补丁策略要能精确重组硬锁结果，无法重组的透明混合会阻断，而不是把平面图冒充独立图层。

materialize返回image/spec/parent/layer_updates/materialization/job_id，加入唯一id后交workflow.py revision。登记检查真实调用、来源、父版本、完整素材和合成记录。候选不可覆盖；母版接受独立记录。明确选择旧版继续会保留其他分支。

每轮交给R4：实际原图、采用图、输入及输出哈希、提示/附件/规则版本、层更新、本轮差异和此前成果核验。用户看到的最终采用图必须与审核/导出绑定的图一致；图像工具的原始候选可能包含范围外漂移，须通过硬锁及原件合成后再交付。

## 原生最小修改（不增加图像调用）

prepare-compose复用已有局部生成结果来修复合成参数：输入id、baseline(当前候选)、source_job(产生该候选的真实生成任务)、goal、application_regions(原授权区的子集)、feather。后续materialize会从原生成基准恢复背景并仅贴入较小区域，登记新版本；保留坏版和缺陷，不假装重新生图。

prepare-source用于准确文字/原件层的确定性替换：先保存新的真实源文件与对应用户要求，更新受影响R1/R2及其真实决定；输入id、baseline、spec、goal、layer_updates(实际替换元素ID)、intent_review(当前要求ID覆盖、unresolved空数组和实际核对说明)。只允许同尺寸、同布局的原件层替换，保护对象需要明确子区域授权证据。materialize真正重组并拒绝范围外变化，随后正常登记/核验；不增加AI调用。当前不会自行创建原生PSD文字层。

cancel仅取消未执行的waiting_execution任务，须带job_id/reason；工具未调用时不计入预算。running任务中断后先核对真实工具记录再finish，不能盲目重放。

## V3.1 PhotoCraft通路

确定性矩形编辑和外部引擎验收按 [PhotoCraft契约](photocraft.md) 执行。生成与编辑分开计数；新项目必须有当前editor机器检查。ORA支持平面裁切层的画布内偏移，逐层内容和合成结果均须一致；引擎通过不扩展为桌面GUI兼容。

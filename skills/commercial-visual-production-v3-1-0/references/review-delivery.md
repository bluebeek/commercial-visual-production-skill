# R4核验、R5缺陷闭环与R6交付

本包版本3.1.0，权威工作流状态为cvisual.workflow.v3；复用的像素/几何/图层工具保留cvisual.audit.v2及tool_version=2.2.0协议标识，协议号独立于安装包号，不是误装旧版。

所有路径必须在项目内。使用workflow.py status读取简报；export读取完整状态。source文件和用户决定是真实记录；本地声明不提供认证签名。测试项目的actor只能test，商业项目的确认actor只能user。

## 真实核验

checks.py run --project <目录> --input <JSON>，JSON为{revision[,observed]}。会执行图片读取、PNG层导出、ORA重读和当前候选精确重组；局部版本另做编辑区外/保护区RGBA比对和差异图。蓝图有color_checks时运行pixel_audit；提供实际observed时运行layout_audit。几何标注必须绑定实际图像SHA，不能复制计划框当观察。RGB纯色样本不是印刷/Pantone证明。

workflow.py review记录revision/check_id/status(PASS/FAIL/UNKNOWN)/actor(agent或user)/observation/evidence_files。文件中须包含实际当前候选。人工项为design、target、history、seams和req:<要求ID>；机器项files/layers/non_target/geometry/color不能由人工按钮覆盖。检查本轮目标、以前改动、接缝和当前每项有效要求。技术通过、助理观察和用户接受分别保存。

关键要求覆盖必须完整。UNKNOWN不能当通过。目标区没有实际修改不算成功；编辑区外不变不证明目标正确。观察不到身份、包装、字形等内容时保留未知。文字应与原件/文案逐字核对；只有实际执行OCR才可报告OCR结果。

## 缺陷与修复

issue输入id/revision/check_id/severity(P0/P1/P2)/expected/actual/scope。R4发现问题后根据原因选择：补证据、改参数/文字层、换源素材、单层处理、限定区域生成；总体布局改变才回R2。

repair关联issue_id/job_id/baseline，使问题进入fixing。先prepare对应局部生产任务，范围及成功条件由助理根据实际问题整理；明确的原请求即该范围的授权。生成与materialize后登记新revision，submit-repair使问题ready_for_review。重新运行检测、记录实图观察，再close-issue。状态verified_closed只对应具体版；后续版需对相关问题完成回归并更新闭合证据。

当用户新要求明确替换了缺陷所对应的旧要求时，可用supersede-issue关联issue_id/replacement_requirement结束旧问题；记录superseded并保留历史，不能谎称已修复。新要求仍须正常核验。

P0/P1、关键未知或必要证据不足阻断冻结。accept-exception只允许具体版本、具体非关键P2，需真实user决定；它不是fixed。换版后例外不能自动沿用，不得借此绕过文件、分层、像素保护或关键品牌标准。

accept需QC通过并附用户决定{revision,actor:user,reason,evidence_files}；freeze需当前接受版与全部有效核验。没有缺陷时直接冻结，不强制生成修复轮次。select选择工作版不改变接受版；revoke可撤销kind=blueprint/candidate与subject对应的决定。

## PNG/ORA

checks.py export输入{id,revision}，从有效批准母版导出，重新读取PNG和ORA stack.xml中的真实图层，核对层序、透明、重组与母版。输出包含源图层、merged_preview.png、layout_layers.ora、报告；用项目状态中的文件哈希核对。accept-delivery输入delivery、actor/user决定信息完成验收。导出后偷偷改图或素材会使结论失效。

本轮支持栅格PNG/ORA，不承诺PSD/活文字。准确文字内容及来源保存，但栅格字不是原生文字层。ORA读取器验证本工具生成的平面src-over栈；目标设计软件的实际打开性单独列NOT_TESTED，未做印刷打样或真实人物/包装生成保真测试不得改称已验证。

## 工作台

start_review.py --project <目录> --port 8765，浏览本地地址。运行检查会实际执行检测；查看报告只读。生产按钮只登记waiting_execution，需当前对话助理执行内置图像工具。不会伪装网页有生图后台。版本对比、要求来源、问题、修复提交、例外、冻结和交付均绑定当前版本。网页以本地用户点击记录声明式决定，测试项目醒目标注test。

## 旧版迁移

migrate_v2.py --source <旧项目> --project <全新目录> 默认只预演；--apply归档旧状态和已绑定证据到新目录，创建未绑定V3项目，原目录不改。映射：旧R0.roles及R1→新R0；旧R0.assets/scope→新R1；旧R2/R3.preview→新R2；旧R3/R4→新R3/R5；旧R5及质量项→新R4；旧图层/文件检查→新R6。

旧approved不导入为新批准；旧resolved实际表示已提交修复，映射ready_for_review。孤立问题、缺失文件和原始记录保留在migration清单，待助理依据真实内容重新建立新阶段及核验。compat/v2保留原脚本/测试/界面作诊断，正常V3执行不加载它。

## V3.1 PhotoCraft通路

确定性矩形编辑和外部引擎验收按 [PhotoCraft契约](photocraft.md) 执行。生成与编辑分开计数；新项目必须有当前editor机器检查。ORA支持平面裁切层的画布内偏移，逐层内容和合成结果均须一致；引擎通过不扩展为桌面GUI兼容。

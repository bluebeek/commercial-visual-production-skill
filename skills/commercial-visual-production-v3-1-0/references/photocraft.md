# PhotoCraft：确定性编辑与引擎验收

PhotoCraft MCP是外部编辑通路，真实生图仍由image_gen独立执行。当前版本正式覆盖平面像素层的矩形填色和PNG/ORA回存；不承诺复杂混合、活文字、生成式填充或桌面GUI。Python脚本只准备任务、保存状态和独立核验，实际MCP调用由当前对话助理完成。

## 准备与执行

1. 明确用户目标、当前工作基准、目标源层ID、整数像素框[x,y,width,height]和#RRGGBB。修改框须在已授权区内且不侵犯保护区；布局变化返回R2。
2. production.py prepare-editor输入id/baseline/goal/operation。operation为{type:rectangle_fill,layer:<规格中的元素ID>,rect:[x,y,w,h],color:#RRGGBB}。可同时提供intent_review；网页排队可暂缺语义核对，但begin-editor前必须由助理补足当前coverage、unresolved空列表和实际核对说明。
3. 按返回editor_plan.input调用doc_open；使用返回index执行doc_select及doc_inspect。确认实际路径、尺寸、层名/层序、Pixel/Normal/opacity=1，记录当前ID映射，不沿用旧会话的索引或图层ID。
4. 把真实返回保存为不可覆盖的开始receipt，调用begin-editor。只执行其返回commands；每次命令前重新doc_select并doc_inspect。首版命令为layer.select、select.rect和edit.fill。工具不可用、文档变化或命令失败即停止。
5. 最后检查文档，按plan.outputs的新路径导出PNG及ORA。保存完整执行receipt，再finish-editor；只有JSON status=EDITOR_READY才能materialize及登记revision。退出码0不等同资格通过。生图calls_used不增加。
6. 原始编辑输出的区外和非目标源层必须不变；矩形在合成图中也必须达到计划颜色，被上层遮挡的填色不能记成功。先检查目标层是否可见地承担该区域，不凭图层名称推断；接收后按精确修改框形成栅格补丁。问题仅submit-repair为待复核，重新检查和观察后才能close-issue。候选接受仍需具体用户决定。

## 实际调用记录

receipt的schema为cvisual.photocraft.receipt.v1，backend=photocraft，mode=engine，calls按实际顺序保存{tool,args,result,isError}。tool使用doc_open/doc_select/doc_inspect/command_run/command_batch/doc_export/doc_save等短名；result是MCP文本JSON的原值，不手造工具结果或ID。非JSON错误保留原文和isError。

fixture=true仅用于显式测试模拟，非测试项目拒绝。测试项目中的真实PhotoCraft调用也应fixture=false。服务未暴露版本时写NOT_EXPOSED，不推测后台版本。输入图、命令、开始记录、结束记录和输出均保存文件哈希；本地记录不提供认证签名。

未知导入警告、缺源和丢层必须阻断。PNG导出的明确扁平化警告可按格式目标记录；这不允许忽略ORA丢层。command_batch不是原子事务，先前成功步骤不会自动回滚。失败或未知结果先核对会话和产物，保留部分结果，再以新任务恢复；不得重放running/failed任务。

## 绑定候选的机器验收

先checks.py run，再从当前layers报告取得已绑定的layout_layers.ora；不拿其他版本或重建的输入冒充该文件。

在独立文档直接打开此ORA，逐层隐藏、检查、导出观察图、恢复；所有层恢复后导出PNG与ORA。所有原文档操作先完成，随后保存.pcraft副本；原生保存会改变文档文件绑定，因此再打开回存ORA及原生副本检查，不能沿用旧路径。原生副本重开后另导PNG及ORA用于逐层核验。

checks.py verify-editor输入revision/input/ora/png/receipt；提供native时同时提供native_png/native_ora。记录须包含实际重开、逐层隐藏恢复及导出证据。检查器比较每层展开至全画布后的RGBA、层名与顺序、最终重组及PNG；原生副本用重开后的ORA逐层验证。缺失canvas即使被背景遮住、预览相同，仍不合格。

新项目的editor机器项是必过项；人工review与P2例外均不能覆盖。机器结果绑定具体文件、规则和检查实现。图像、receipt或输出变化后必须复检。PASS表示本次引擎接口验证通过；GUI保持NOT_TESTED。文件通过、助理目标/历史/接缝观察、用户接受、冻结与交付决定分别记录。

## 格式与兼容

ORA限平面、可见、src-over、整体opacity=1的栅格层；支持画布内非负整数偏移及裁切源图，保留逐像素透明度。嵌套、越界、其他混合和缺失成员明确失败。PNG/ORA是正式交付格式，.pcraft是补充工作副本；不承诺跨会话撤销历史。

旧cvisual.workflow.v3记录可读取。旧项目缺少editor_backend时仍按历史范围显示；一旦执行PhotoCraft编辑或验收便绑定该后端，不能把旧报告当作新增引擎验收。新项目默认要求PhotoCraft。测试里的editor_backend=None只用于显式旧行为夹具，非测试新项目禁止绕过。

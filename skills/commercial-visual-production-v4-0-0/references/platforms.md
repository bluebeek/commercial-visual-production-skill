# 平台、安装和移交

共享 SKILL.md 与脚本维护一份，不复制平台专属生产规则。平台包只改变安装前缀；核心文件必须逐项哈希相同。

| 入口 | 包／目录 | 实际验收 |
|---|---|---|
| Codex | 项目 .agents/skills/commercial-visual-production-v4-0-0 | 技能发现、调用、文件及脚本、工具实际可用性分别记录 |
| Claude Code | 项目 .claude/skills/commercial-visual-production-v4-0-0 | 同上；CLI 存在不等于已加载技能 |
| Cursor | 项目 .cursor/skills/commercial-visual-production-v4-0-0 | 同上，注意会兼容发现其他目录，避免重复安装 |
| ChatGPT／Claude 聊天 | native ZIP 中单个技能根目录含 SKILL.md | 包结构检查不是账户上传成功；网络、执行和凭据按实际账户核验 |
| Gemini 聊天 | 同一 native 核心，按实际 Skills 入口导入 | 注意 Gems 迁移与账户类型差异；不能预设脚本可执行 |

只有具备持久文件、所需依赖与执行工具，才能正式登记阶段和版本。无执行环境时整理草稿和待执行文件，不声称正式 R0／R1／R2 完成。完整生产验收继续要求 PhotoCraft MCP；缺少时保留阻断，移交到已验证执行端。不得把本地 127.0.0.1 工作台公开成云站点来绕过限制。

## V3 读取与副本迁移

`portable.py inspect --project <旧目录>` 只读概览。

`portable.py migrate-v3 --project <V3目录> --destination <新目录>` 默认 dry-run，带 --apply 才创建 V4。旧项目全部可携文件归档至 legacy/v3，生成对象数量及哈希映射。新活动状态不继承旧批准、阶段或接受，调用额度 0；需重新绑定来源、要求与 R0–R2，再确认蓝图。旧测试项目始终保持 test_mode，不能变成生产批准。迁移不是旧任务的继续调用。

V2 继续由原 V3.1 的隔离兼容区处理。V4 未打包另一份 V2，避免重复维护；旧状态不写回。

## V4 项目移交

`portable.py export --project <目录> --archive <项目外新 ZIP>`：检查没有 running／result_unknown，必要时 release 原预算执行资格，再打包全部项目文件与逐项清单。拒绝凭据、环境文件和符号链接；不携带外部预算文件。输出目录不能位于项目内。

`portable.py import --archive <ZIP> --destination <新目录>`：校验成员、路径、重复项、解包大小和 SHA256；只在完整校验后发布新目录。保留要求、来源、版本、补丁、分支与已花次数。未尝试任务取消并注明重编译；历史已执行参数作为证据保留。原状态归档至.portable-import，当前检查清空、冻结解除，要求在新宿主重验；同一候选的真实用户决定保留，不复制给新候选。导入不会取得执行资格。

新端使用同一个原预算账本 bind，重新运行 doctor、refresh 和 prepare。本版只支持可访问同一账本的单执行端接管；无法访问原账本的远程聊天环境仅能读取资料，不能新建账本重置余额。没有分布式离线额度或自动云桥接。

每个平台的加载／脚本／模型调用／PhotoCraft／完整交付分别给 PASS、FAIL、BLOCKED 或 NOT_TESTED。不把单次真实 API 成功扩展到所有宿主，也不以操作系统 CI 代替宿主实测。

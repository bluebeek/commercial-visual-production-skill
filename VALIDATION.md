# 验证范围 / Validation scope

版本 / Version: **3.0.0** · 验证日期 / Validation date: **2026-10-23**

> 下述 2026-10-23 记录保留为发布历史。2026-10-26 开发候选的零调用验证、修复、65 文件清单及未完成项见 [第二轮报告](validation/round2/REPORT.md)。原 ZIP 校验值不适用于开发候选。

## 自动测试 / Automated checks

| 项目 / Check | 结果 / Result |
| --- | --- |
| V3 workflow and integration suite | 54 passed, 20.263 s |
| Isolated V2 compatibility suite | 70 passed, 9.438 s |
| Total | 124 passed; the 70 legacy tests are not 70 additional V3 semantic tests |
| Skill format | Passed |
| Installed / staging / original ZIP | 64 source files with matching SHA-256 hashes |
| Installed smoke check | Actual controlled test project loaded; QC PASS, delivery accepted in test mode, 4 image invocations |

发布副本另已重跑：V3 54 项通过（20.260 秒），兼容区 70 项通过（9.811 秒），64 个技能文件与安装版逐项一致。将来 GitHub CI 运行应以该次日志为准。新增根目录说明、依赖清单与 CI 配置不是原技能 ZIP 的组成部分。

The publication copy was also rerun: 54 V3 tests passed (20.260 s), and 70 compatibility tests passed (9.811 s). All 64 Skill files matched the installed version. Future GitHub CI results must be read from the actual run. Repository-level documentation, dependency declarations, and CI configuration are additions outside the original Skill ZIP.

## 四次真实调用 / Four real image invocations

内置 `image_gen.imagegen`，一个受控的虚构 NOVA 品牌分层海报。产品、Logo 和准确标题为独立绘制的原件层，不是真实摄影身份保真测试。所有批准均为测试决定。

The built-in `image_gen.imagegen` tool was used for one controlled layered poster under a fictional NOVA brand. Product, logo, and exact title were separately rendered source layers, not photographic identity-fidelity tests. All approvals were test-only decisions.

| Round | Objective / 目标 | Observed handling / 实际处理 |
| --- | --- | --- |
| 1 | Initial teal grain background, orange torus, white arc / 首图 | Arc placement differed from plan; candidate not accepted / 弧线位置偏差，首版未接受 |
| 2 | Delete white arc / 删除弧线 | Raw result also changed product/texture. Hard lock restored non-target areas; a visible compositing seam was repaired using the same generated output with a smaller mask and inner feather / 原始返图有额外变化，硬锁与缩小选区、内羽化修复接缝 |
| 3 | Change torus to golden yellow / 圆环改金黄 | Annular selection preserved its hole and background; original deletion and source layers retained / 环形选区保留中空背景、删除成果及原件 |
| 4 | Reduce local highlight / 缩小局部高光 | Restricted patch and inner feather; checked earlier deletion, gold color, and sources / 局部补丁与内羽化，复核此前成果 |

共 4 次真实调用，没有为最终构建再追加一组实图测试。测试发生在开发迭代中，发现问题后修复并继续；最终构建重新运行了程序回归与安装核验。两次复用已有图像的原生合成修复不增加图像调用；一个未调用的长提示任务已取消并重编译，不算第 5 次。

Exactly four real invocations were used. Testing occurred during development, with fixes applied before continuing. The final build reran program regression and installation checks, without another four-image run. Two native recomposition repairs reused existing output without another image invocation. A queued but unattempted long-prompt task was canceled/recompiled and was not a fifth invocation.

## 最终测量 / Final measurements

- Last edit: RGBA changes outside the edit mask = **0 pixels**.
- Protected product, logo, and title versus the first candidate = **0 changed pixels**.
- Deleted-arc region since the deletion repair = **0 changed pixels**.
- Selected unedited golden region since recoloring = **0 changed pixels**.
- Eight raster layers independently reread from PNG/ORA recomposed identically to the accepted test master.
- In the final target area, encoded luminance proxy pixels above 230 decreased from 5,240 to 3,108 (~40.7%). This is a threshold proxy, not semantic recognition or physical photometry.
- The final local prompt decreased from 4,694 to 1,320 characters (~71.9%). This is character reduction, not measured billing-token or image-credit savings.

以上零差异描述的是实际采用图及指定测量区域，不代表模型原始输出没有漂移，也不能取代目标达成和接缝视觉检查。

Zero differences refer to the adopted composite and specified measured regions. They do not imply drift-free raw model output or replace goal/seam review.

## 未验证 / Not verified

- Live whole-poster generation containing exact Chinese copy; real-person identity generation; real photographed packaging reconstruction; complex multi-asset stability; broad style coverage.
- Opening the ORA in a target design application. The independent reader verified the generated flat src-over stack only.
- Editable PSD, native text/vector layers, print proofing, CMYK or Pantone accuracy.
- Automatic OCR, facial identification, or universal semantic image understanding.
- Authenticated user signatures or tamperproof approval records.
- A backend model specifically identified as “ChatGPT Image 2.5”; the public tool does not expose that selection.
- All supported Python versions and operating systems. Windows was the observed validation environment.

上述项目必须标为未做实测，不能从本案例推断普遍可靠性。

These remain untested; the controlled case is not evidence of universal reliability.

## 原始技能包 / Original Skill archive

Filename: `commercial-visual-production-v3-0-0.zip`

Size: 160,464 bytes

SHA-256: `fb0e1514b060544c55b34a4aea68ff7bfbb771243cbf3c4cb701d1b41538e490`

该 ZIP 只包含已验证的 64 个技能文件；仓库根目录说明另行提供。

This ZIP contains only the 64 verified Skill files. Repository-root documentation is supplied separately.

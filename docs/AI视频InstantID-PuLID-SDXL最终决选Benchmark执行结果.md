# AI Video Studio InstantID + PuLID SDXL 最终决选 Benchmark 执行结果

## 1. 一页结论

**最终架构决策：`REPLACE_CHARACTER_GENERATION_ARCHITECTURE`**

InstantID 和 PuLID 都能在 RTX 4070 12GB 上真实通过 ComfyUI `/prompt` 完成 SDXL 采样，但两者都没有通过 Stage B 的 30% DualPass 预筛：InstantID 为 0/6，PuLID 为 1/6（16.67%）。按冻结停止规则，两者均不进入 Stage C；本轮没有 >=50% 或 >=70% 方法。因此下一代人物资产生成不应继续沿用当前 SDXL Identity Control 主路线，进入 Character Generation Architecture Replacement 研究。

这不是 12GB 硬件阻塞：两种方法 Stage A 都真实出图且无 OOM。它是“能运行，但人物身份与视角联合通过率不足”的质量结论。

## 2. 当前架构决策

本轮 benchmark 侧部署已完成：SDXL、InstantID adapter/ControlNet、PuLID adapter/EVA、antelopev2 均完成校验；InstantID 与 PuLID 的 Stage A/B 均通过真实 `/prompt`。生产路由未接入新架构，也没有修改主 API 生产行为。

## 3. 环境

- GPU: `cuda:0 NVIDIA GeForce RTX 4070 : cudaMallocAsync`；总显存 `12281 MiB`
- ComfyUI: `0.31.0`；Python `3.13.2 (tags/v3.13.2:4f8bb39, Feb  4 2025, 15:23:48) [MSC v.1942 64 bit (AMD64)]`；PyTorch `2.11.0+cu130`
- 主 API: `http://127.0.0.1:18080/api/health`；Identity Worker: `http://127.0.0.1:18084/health`，保持 loopback-only
- C 盘: 可用 `135.59 GiB`
- 固定配置: 512×768、24 steps、CFG 5、DPM++ 2M/Karras、统一 master/prompt/negative、raw cosine >=0.5、Front <15°、30° [12°,40°)、45° [27°,62°)

## 4. Workspace

- Branch: `main`
- HEAD: `d6ec38d076a8b0336d349c36df5c123f2c941ac8`
- Dirty count: `148`
- 既有 dirty work 保留；未执行 reset、clean、checkout、删除模型/QA/workflow/角色图。

## 5. Asset State Before / Resume

`03-asset-resume-and-validation.json` 保存了恢复前的 partial/range 状态。完整且 hash 正确的 InstantID adapter、PuLID adapter、antelopev2 均为 `SKIP_DOWNLOAD`；SDXL、InstantID ControlNet 使用保留分片/`.recovered` sidecar 恢复；EVA 只下载 PuLID 节点实际要求的一个变体。

- SDXL base: PARTIAL_RESUMABLE 556630016 bytes → COMPLETE_VALIDATED 6938078334 bytes; target净增 6381448318 bytes; sidecar保留 2086481022 bytes; SHA `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`
- InstantID adapter: COMPLETE_VALIDATED 1691134141 bytes → COMPLETE_VALIDATED 1691134141 bytes; target净增 0 bytes; sidecar保留 0 bytes; SHA `02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1`
- InstantID ControlNet: PARTIAL_RESUMABLE 741240832 bytes → COMPLETE_VALIDATED 2502139136 bytes; target净增 1760898304 bytes; sidecar保留 687156480 bytes; SHA `c8127be9f174101ebdafee9964d856b49b634435cf6daa396d3f593cf0bbbb05`
- PuLID adapter: COMPLETE_VALIDATED 791372856 bytes → COMPLETE_VALIDATED 791372856 bytes; target净增 0 bytes; sidecar保留 0 bytes; SHA `b258a5cd2c0c7d35f4d3e59909d7648498686afae4d0c74917e9c47d7704fbf5`
- antelopev2 archive: COMPLETE_VALIDATED 360662982 bytes → COMPLETE_VALIDATED 360662982 bytes; target净增 0 bytes; sidecar保留 0 bytes; SHA `8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5`
- PuLID EVA02 CLIP L 336: MISSING 0 bytes → COMPLETE_VALIDATED 856461210 bytes; target净增 856461210 bytes; sidecar保留 856461210 bytes; SHA `84c3a17a228c567a155259b2245b0b59072bf7da510260a0a02ec54de6d50b05`

- 所有最终资产: **True / COMPLETE_VALIDATED**。
- 目标文件净新增: `8998807832` bytes；保留 recovered sidecar: `3630098712` bytes；本轮模型文件实际新增（含保留 sidecar）: `12628906544` bytes。

## 6. Stage A：真实采样与显存

| 方法 | 状态 | 采样 | 单图耗时 | Peak VRAM | 最低余量 | OOM | 输出 |
|---|---|---:|---:|---:|---:|---:|---|
| InstantID | PASS | 1/1 | 19242.0 ms | 10988.0 MiB | 1023.0 MiB | False | `C:\install\AI\ComfyUI\output\sdxl_final_benchmark_20260818\instantid_stage_a_front_410001_00001_.png` |
| PuLID | PASS | 1/1 | 93469.6 ms | 10610.0 MiB | 1401.0 MiB | False | `C:\install\AI\ComfyUI\output\sdxl_final_benchmark_20260818\pulid_stage_a_front_410001_00001_.png` |

第一次 InstantID A 请求曾因 benchmark ComfyUI 未用中央 models directory 而触发 `FAIL_WORKFLOW`（模型列表为空），不是显存错误；使用进程级 `--models-directory C:\install\AI\Models` 修正后重新通过，原失败 manifest 保留。

## 7. InstantID Stage B

总体：0/6 Dual，端到端 0.00%，技术成功 6/6，Identity 0/6，View 3/6，HardReject 6。`METHOD_REJECTED_STAGE_B`。

逐视角：front: Dual 0/2, Identity 0/2, View 1/2, yaw=[12.433, None]；left30: Dual 0/2, Identity 0/2, View 1/2, yaw=[5.791, -15.756]；left45: Dual 0/2, Identity 0/2, View 1/2, yaw=[9.504, -59.713]。

- Median cosine: `0.24825968`
- Median yaw error: `14.713000000000001°`；P95 `54.504°`
- 视角趋势: `NO_MONOTONIC_VIEW_CONTROL=True`

## 8. PuLID Stage B

总体：1/6 Dual，端到端 16.67%，技术成功 6/6，Identity 3/6，View 1/6，HardReject 5。`METHOD_REJECTED_STAGE_B`。

逐视角：front: Dual 1/2, Identity 1/2, View 1/2, yaw=[5.276, None]；left30: Dual 0/2, Identity 1/2, View 0/2, yaw=[7.052, None]；left45: Dual 0/2, Identity 1/2, View 0/2, yaw=[2.973, None]。

- Median cosine: `0.64855647`
- Median yaw error: `37.052°`；P95 `47.973°`
- 视角趋势: `NO_MONOTONIC_VIEW_CONTROL=True`

## 9. Stage B Gate / Stage C

- InstantID: 0/6 <30%，停止，不进入 C。
- PuLID: 1/6 =16.67% <30%，停止，不进入 C。
- InstantID Stage C: `NOT_RUN`，不是 0/15。
- PuLID Stage C: `NOT_RUN`，不是 0/15。
- 因此左右 30°/45°完整双侧稳定性、Stage C 5 视角覆盖、Half/Full、Golden Candidates 均为 `NOT_RUN`/`UNVERIFIED`，不从未执行数据推断质量。

## 10. Identity / View / Dual Comparison

| 指标 | InstantID | PuLID |
|---|---:|---:|
| Stage A | PASS 1/1 | PASS 1/1 |
| Stage B Technical | 6/6 | 6/6 |
| Stage B IdentityPass | 0/6 | 3/6 |
| Stage B ViewPass | 3/6 | 1/6 |
| Stage B DualPass | 0/6 = 0.00% | 1/6 = 16.67% |
| Stage B Median cosine | 0.24825968 | 0.64855647 |
| Stage B Median yaw error | 14.713000000000001° | 37.052° |
| Stage B HardReject | 6/6 | 5/6 |
| Stage C | NOT_RUN | NOT_RUN |

PuLID 的 B 阶段身份指标高于 InstantID，但它仍然只有 1/6 Dual，主要失败在目标视角；因此“身份分数较高”不能替代身份+视角联合通过。

## 11. VRAM / Performance / Local Viability

- InstantID Stage A: Peak `10988.0 MiB`，约 `10.73 GiB`；`19242.0 ms`；OOM `false`。
- PuLID Stage A: Peak `10610.0 MiB`，约 `10.36 GiB`；`93469.6 ms`；OOM `false`。
- Stage B generation P50/P95（按该阶段原始 manifest）: InstantID `7148.9 ms / 14706.4 ms`；PuLID `6108.7 ms / 15795.9 ms`。如果 QA JSON 没有重复该字段，以 Stage A 采样监控为准；没有用理论值替代。
- ComfyUI 进程启用了 async weight offloading；本轮没有 OOM，也没有单张超过 5 分钟，Gate F 为 PASS。

## 12. Half / Full / Golden Candidates

均未执行。原因是两条方法均未通过 Stage B，严格遵守不扩大样本、不伪造 C/Golden 结果的停止规则。`READY_FOR_CHARACTER_LORA_POC=false`。

## 13. Dependency Complexity

- InstantID: SDXL Base + InstantID adapter + antelopev2/InsightFace + InstantID ControlNet；需要显式的 pose/control image。
- PuLID: SDXL Base + PuLID adapter + antelopev2/InsightFace + EVA02 CLIP L 336；本轮 workflow 没有独立 ControlNet pose 分支，视角依赖 prompt，因此不能把它的方向失败归因成缺少已执行的控制分支之外的能力。
- 两者共享同一个 SDXL Base 和同一套 QA Worker，比较结果主要反映身份控制路线差异，而不是 checkpoint 差异。

## 14. Blocked / Unverified

- InstantID Stage B rejected: 0/6 DualPass (0.00%), below 30% gate.
- PuLID Stage B rejected: 1/6 DualPass (16.67%), below 30% gate.
- Stage C not run for either method by the frozen Stage B stop rule.
- No >=50% method; no >=70% method; no Golden Candidates, Half or Full tests.
- Human aesthetic review is not a substitute for the frozen automated gates.

左右方向稳定性：本轮 Stage B 只按提示词执行 Front/Left30/Left45，未执行右侧；两种方法左侧趋势均为 `NO_MONOTONIC_VIEW_CONTROL=true`，右侧方向不能宣称通过。

## 15. 最终排名

按 DualPass → Core View Coverage → IdentityPass → Median Yaw Error → HardReject → VRAM → Generation Time → Dependency Complexity 排名：

1. PuLID — best B Dual 16.67%; REJECTED_STAGE_B
2. InstantID — best B Dual 0.00%; REJECTED_STAGE_B

该排名仅是“已执行 Stage B 的相对排序”，不是生产选择；由于最高也只有 16.67%，最终没有 selected method。

## 16. 构建与自动回归

- python-compile: PASS (exit 0)
- asset-validation: PASS (exit 0)
- resume-manifest: PASS (exit 0)
- vram-probe-parsing: PASS (exit 0)
- server-build: PASS (exit 0)
- quality-harness-build: PASS (exit 0)
- quality-harness-self-test: PASS (exit 0)
- git-diff-check: PASS (exit 0)

所有本轮新增 Python 工具已执行 compile check；`git diff --check` 结果也在 `12-build-regression.json`。本轮没有改动主 API/Worker/ModelRouter/TTS/FFmpeg 生产代码。

## 17. QA / Benchmark 文件

- [01-environment.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\01-environment.json)
- [02-existing-assets.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\02-existing-assets.json)
- [03-asset-resume-and-validation.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\03-asset-resume-and-validation.json)
- [04-instantid-vram-probe.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\04-instantid-vram-probe.json)
- [05-pulid-vram-probe.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\05-pulid-vram-probe.json)
- [06-instantid-stage-b.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\06-instantid-stage-b.json)
- [07-pulid-stage-b.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\07-pulid-stage-b.json)
- [08-instantid-stage-c.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\08-instantid-stage-c.json) — `NOT_RUN`
- [09-pulid-stage-c.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\09-pulid-stage-c.json) — `NOT_RUN`
- [10-method-comparison.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\10-method-comparison.json)
- [11-final-candidate-ranking.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\11-final-candidate-ranking.json)
- [12-build-regression.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\12-build-regression.json)
- [13-final-acceptance.json](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\13-final-acceptance.json)

## 18. 人工审核 HTML

- [01-instantid-stage-b.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\01-instantid-stage-b.html)
- [02-pulid-stage-b.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\02-pulid-stage-b.html)
- [03-instantid-stage-c.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\03-instantid-stage-c.html) — 未生成，Stage C `NOT_RUN`
- [04-pulid-stage-c.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\04-pulid-stage-c.html) — 未生成，Stage C `NOT_RUN`
- [05-instantid-vs-pulid.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\05-instantid-vs-pulid.html)
- [06-final-golden-candidates.html](C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\html\06-final-golden-candidates.html) — 状态页，无 Golden 样本

HTML 只展示实际生成的 Stage B 图片与指标，不把未执行的 Stage C/Golden 伪装成样本。最终审美签字仍由用户完成：同一人物、发型/年龄/衣服稳定性、左右 30°/45°自然度、五官失真均需人工复核。

## 19. 本轮代码 / workflow 修改

- 新增 `VideoStudio/tools/sdxl_final_benchmark/` 下的资产恢复、资产清单、环境采集、真实 `/prompt` runner、QA evaluator、汇总/报告/HTML 工具。
- 新增版本化 workflow：`C:\install\AI\Workflows\23_sdxl_instantid_final_benchmark_v1_api.json`、`24_sdxl_pulid_final_benchmark_v1_api.json`；没有覆盖 21/22。
- QA evaluator 增加 worker allow-list 内的哈希证据副本，保留 ComfyUI 原始输出。
- ComfyUI 仅为本轮验证以进程级 `--models-directory` 与 `HF_HUB_CACHE` 启动；主 API、Identity Worker 保持运行边界。

## 20. 最终架构决策与下一轮唯一推荐方向

**正式结论：`REPLACE_CHARACTER_GENERATION_ARCHITECTURE`。**

本轮不再建议继续调 SD1.5 FaceID、SDXL FaceID、InstantID 或 PuLID，也不降低阈值、不扩大 seed。下一轮唯一推荐方向是：**评估一种新的原生 reference-conditioned / multi-view Character Generation Architecture**，优先做小规模选型与真实多视角联合 DualPass 验证；本轮不执行该替换、不训练 LoRA、不进入视频动作或 TTS。

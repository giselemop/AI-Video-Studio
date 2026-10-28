# AI Video Studio 多视角人物生成攻坚执行结果

执行日期：2026-08-17\
项目：`C:\install\AI\VideoStudio`\
本次证据根目录：`C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01`\
Git：`main` / `d6ec38d076a8b0336d349c36df5c123f2c941ac8`

## 一、最终结论

最终状态：**NO_GO_MULTIVIEW**。

本次严格验收静态多视角人物生成，不把视频、动作片、TTS、SRT、LoRA、Wan2.2 或 HunyuanVideo-1.5 混入结论。现有 SD1.5 FaceID、FaceID+HeadPose 和 Img2Img 路线均完成真实出图与身份/视角 QA；InstantID、PuLID 已部署并完成节点/模型加载探测，但由于完整 SDXL/ControlNet/EVA 前置资产未在本次运行窗口内就绪，没有伪造生成样本。

| 验收门 | 结果 | 关键证据 |
|---|---|---|
| FaceID 失败分析 A-I | PASS | `faceid-failure-analysis.json` |
| FaceID+HeadPose 15 样本 | FAIL_LOW_YIELD | 15/15 技术成功，Dual 2/15 = 13.33%，低于 30% 继续门槛 |
| Img2Img A/B/C/D | FAIL_ZERO_VIEW_DUAL | 24/24 技术成功，View 0/24，Dual 0/24 |
| InstantID | BLOCKED_PREGENERATION_INCOMPLETE_ASSETS | 节点和 adapter loader 可加载，SDXL/InstantID ControlNet 不完整 |
| PuLID | BLOCKED_PREGENERATION_EVA_AND_SDXL | 节点、PuLID adapter、InsightFace 可加载，EVA/SDXL 不完整 |
| Golden Reference v3 | FAIL | 仍为 3 个，核心非正面视角为 0 |
| Selector | FAIL | Direct 3/7 = 42.86%，低于 80% |
| Character LoRA PoC | NOT_ALLOWED | 没有达到候选/Golden 门槛 |
| 构建回归 | PASS | Server、QualityHarness、自测、Python 编译、diff check 均通过 |

因此本轮不进入 Character LoRA PoC，不放宽身份阈值 `0.5`、正面 yaw `±15°`、30°范围 `[12°,40°]` 或 45°范围 `[27°,62°]`，也不把未通过样本标为可生产。

## 二、工作区与运行环境

- 未执行 reset、clean、checkout；已有未提交改动全部保留。最终工作区 dirty count 为 147。
- ComfyUI `0.31.0`，Python `3.13.2`，PyTorch `2.11.0+cu130`，监听 `127.0.0.1:8188`。
- 主 API `127.0.0.1:18080`、Identity Worker `127.0.0.1:18084` 健康检查均可用。
- GPU：NVIDIA GeForce RTX 4070；`nvidia-smi` 在阻塞证据采集时为总显存 12282 MiB、已用 5201 MiB、空闲 6810 MiB；ComfyUI 记录的空闲显存约 6866 MiB。
- C 盘可用空间：149.01 GiB。
- 已增加但未升级 Torch 的运行依赖：`facexlib 0.3.0`、`ftfy 6.3.1`、`timm 1.0.28`、`wcwidth 0.8.2`。

### SDXL / 适配器硬件阻塞边界

阻塞证据：`18-sdxl-hardware-blocker.json`。

| 资产 | 当前文件 | 目标大小 | 状态 |
|---|---:|---:|---|
| SDXL base | 556,630,016 B | 6,938,078,334 B | 不完整；40 个分片保留 |
| InstantID adapter | 1,691,134,141 B | 1,691,134,141 B | 完整；SHA-256 `02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1` |
| InstantID ControlNet | 741,240,832 B | 2,502,139,136 B | 不完整；12 个分片保留 |
| PuLID adapter | 791,372,856 B | 791,372,856 B | 完整；SHA-256 `b258a5cd2c0c7d35f4d3e59909d7648498686afae4d0c74917e9c47d7704fbf5` |
| antelopev2 | 360,662,982 B | 360,662,982 B | 完整；SHA-256 `8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5` |
| EVA02 CLIP | 未下载 | 约 856 MiB | 受控探测明确跳过自动下载 |

已知资产大小加 EVA 估算约 12.28 GiB，这是磁盘资产总量，不等同于显存峰值。对 SDXL 文件做了真实 HTTP Range 探测，返回 `206`、`1,048,576` 字节；但未完成完整 checkpoint 和 ControlNet，所以没有启动有效 SDXL 工作流。

**重要边界：本次没有观察到 CUDA OOM，也不能把“未能在本次窗口完成资产下载”写成“12GB 已实测跑不了”。SDXL 峰值显存仍为未测量；当前结论是 `BLOCKED_PREGENERATION_INCOMPLETE_SDXL_OR_INSTANTID_ASSETS`。** 已启动的下载进程已停止，前缀和分片均保留，可继续恢复。

## 三、FaceID 失败分析

来源：上一轮已完成的 21 个 FaceID 样本，继续使用冻结阈值，不重新标注历史样本。

| 分类 | 命中次数 | 说明 |
|---|---:|---|
| A 身份失败、角度正确 | 6 |
| B 身份正确、角度失败 | 1 |
| C 身份和角度均失败 | 11 |
| D 镜像/左右方向异常 | 4 |
| E 缺失/未生成 | 0 |
| F 过于正面 | 9 |
| G 过于侧面 | 0 |
| H 遮挡/发型/服饰问题 | 未量化，保留人工复核 |
| I 裁剪/身体覆盖问题 | 未量化，保留人工复核 |

A-I 分类可能重叠，不能按列求和。总体结论是身份失败更频繁；非正面视角的 yaw 控制也呈系统性不足。没有通过调阈值把这些样本改成通过。

## 四、HeadPose 控制与 FaceID Benchmark

### 控制资产

已生成并修正多视角头部模板：Front、±15°、±30°、±45° 的几何检查通过；±60°保留为研究/人工复核模板。右侧模板完成语义五点左右交换，避免左右方向误用。OpenPose/face landmark 采用官方 ControlNet OpenPose 约定；参考：[ControlNet v1.1 OpenPose README](https://github.com/lllyasviel/ControlNet-v1-1-nightly/blob/main/README.md?plain=1)。

### 15 个真实样本

- 配置：FaceID + OpenPose + HeadPose，5 个视角（Front、30L、30R、45L、45R）× 3 seeds。
- 技术成功：15/15。
- 身份通过：5/15。
- 视角通过：4/15。
- Dual：2/15 = **13.33%**。
- Hard Reject：13/15。
- Gate：`LOW_YIELD`；`expansionAllowed=false`。

| 请求视角 | 样本 | 身份通过 | 视角通过 | Dual | 实际 yaw |
|---|---:|---:|---:|---:|---|
| Front | 3 | 2 | 3 | 2 | 1.639、4.489、2.442 |
| 30L | 3 | 1 | 0 | 0 | -10.315、-11.532、-9.896 |
| 30R | 3 | 2 | 0 | 0 | 9.497、8.377、6.968 |
| 45L | 3 | 0 | 0 | 0 | -22.304、-24.997、-20.143 |
| 45R | 3 | 0 | 1 | 0 | 12.254、29.782、12.083 |

2 个 Front Dual 样本只作为复核候选，未晋升为多视角生产候选：

- `headpose_generated\head_front\FaceID_HeadPose_head_front_310101.png`
- `headpose_generated\head_front\FaceID_HeadPose_head_front_310103.png`

## 五、Img2Img Benchmark

真实运行 24 个样本：A/B/C/D × 30L、45R × denoise `0.35/0.55/0.75`，固定 512×768、ControlNet 权重 0.85。

| 方法 | 样本 | 技术成功 | 身份通过 | 视角通过 | Dual |
|---|---:|---:|---:|---:|---:|
| A Img2Img + Pose | 6 | 6 | 2 | 0 | 0 |
| B Img2Img + FaceID + Pose | 6 | 6 | 6 | 0 | 0 |
| C Img2Img + HeadPose | 6 | 6 | 2 | 0 | 0 |
| D Img2Img + FaceID + HeadPose | 6 | 6 | 6 | 0 | 0 |

总计技术成功 24/24、身份通过 16/24、视角通过 0/24、Dual 0/24、Hard Reject 24/24，Gate 为 `LOW_YIELD`。B/D 的身份保持达到 6/6，但输出 yaw 仍接近正面，没有兑现 30L/45R 目标，因此不能称为动作/视角控制成功。

| denoise | 样本 | 身份通过 | 视角通过 | 典型 yaw 现象 |
|---:|---:|---:|---:|---|
| 0.35 | 8 | 8 | 0 | identity 最稳，但仍接近正面 |
| 0.55 | 8 | 4 | 0 | identity 下降，视角仍未形成 |
| 0.75 | 8 | 4 | 0 | identity 进一步不稳，视角仍未形成 |

## 六、InstantID 部署与 Benchmark

已采用官方/可信路线：SDXL、`antelopev2`、InstantID adapter、InstantID ControlNet。参考：[InstantID 官方仓库](https://github.com/instantx-research/instantid)、[ComfyUI InstantID 节点](https://github.com/cubiq/ComfyUI_InstantID)。

- 活跃节点目录：`C:\install\AI\ComfyUI\custom_nodes\ComfyUI_InstantID_20260817`
- staging commit：`72495e806bc2ab9c41581e15ccaa1bcf83c477e8`
- `/object_info` 已注册 `InstantIDModelLoader`、`InstantIDFaceAnalysis`、`ApplyInstantID`、`ApplyInstantIDAdvanced`、`ApplyInstantIDControlNet`。
- InstantID adapter loader：PASS，约 1692.0 ms。
- `InstantIDFaceAnalysis + antelopev2 + CPU`：PASS，约 1732.9 ms。
- **生成 Benchmark：0/0，未计样本。**
- 当前状态：`DEPLOYED_NODE_BLOCKED_INCOMPLETE_ASSETS` / `BLOCKED_PREGENERATION_INCOMPLETE_ASSETS`。
- 阻塞原因：完整 SDXL checkpoint 和 InstantID ControlNet 未通过大小/SHA 校验；没有完整工作流就不启动生成，也不把 loader PASS 当作身份/视角质量 PASS。

## 七、PuLID 部署与 Benchmark

已采用官方/原生 ComfyUI 路线：参考：[PuLID 官方仓库](https://github.com/ToTheBeginning/PuLID)、[PuLID ComfyUI 节点](https://github.com/cubiq/PuLID_ComfyUI)。

- 活跃节点目录：`C:\install\AI\ComfyUI\custom_nodes\PuLID_ComfyUI_20260817`
- staging commit：`93e0c4c226b87b23c0009d671978bad0e77289ff`
- `/object_info` 已注册 `PulidModelLoader`、`PulidInsightFaceLoader`、`PulidEvaClipLoader`、`ApplyPulid`、`ApplyPulidAdvanced`。
- PuLID adapter loader：PASS，约 1156.5 ms。
- `PulidInsightFaceLoader + antelopev2 + CPU`：PASS，约 1459.5 ms。
- EVA CLIP：受控探测跳过，原生节点会请求约 856 MiB 的 `EVA02_CLIP_L_336_psz14_s6B.pt`；没有把自动下载当作完成。
- **生成 Benchmark：0/0，未计样本。**
- 当前状态：`DEPLOYED_MODEL_LOADER_PASS_EVA_BLOCKED` / `BLOCKED_PREGENERATION_EVA_AND_SDXL`。

## 八、统一方法比较、候选、Golden 与 Selector

### 方法排名

| 排名 | 方法 | 技术成功 | 身份 | 视角 | Dual | Dual 率 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | FaceID（旧基线） | 21/21 | 4 | 9 | 3 | 14.29% |
| 2 | FaceID+HeadPose | 15/15 | 5 | 4 | 2 | 13.33% |
| 3 | Baseline | 21/21 | 0 | 9 | 0 | 0% |
| 4 | B Img2Img+FaceID+Pose | 6/6 | 6 | 0 | 0 | 0% |
| 5 | D Img2Img+FaceID+HeadPose | 6/6 | 6 | 0 | 0 | 0% |
| 6 | A Img2Img+Pose | 6/6 | 2 | 0 | 0 | 0% |
| 7 | C Img2Img+HeadPose | 6/6 | 2 | 0 | 0 | 0% |
| 8 | InstantID | 未生成 | — | — | — | 阻塞 |
| 9 | PuLID | 未生成 | — | — | — | 阻塞 |

当前“最高已测方法”是旧 FaceID（Dual 14.29%）；“最高新增控制路线”是 FaceID+HeadPose（13.33%）。两者均低于 30% 继续门槛，所以不存在可扩展的 Top Production Method；B/D 只是身份保持路线，不是多视角生产路线。

### Golden Reference v3

沿用 v2 的 3 个 Golden，没有新的非正面 Dual 样本可以晋升。目标为 10–20 个，建议 14 个；当前 `loRAAllowed=false`。

| 视角 | Golden 数量 |
|---|---:|
| front | 1 |
| front_left_30 | 0 |
| front_right_30 | 0 |
| left_45 | 0 |
| right_45 | 0 |
| half_body_front | 1 |
| full_body_front | 1 |

### Selector

7 个核心参考视角中 Direct 3 个、Fallback 4 个，Direct Qualified Reference Rate 为 **42.86%**，低于 80% 门槛；`14-selector-validation.json` 为 FAIL。

## 九、性能

- HeadPose：生成 P50 4061 ms、P95 8127 ms；身份 QA P50 937.621 ms；测得最低空闲显存约 6898 MiB。
- Img2Img：生成 P50 4225 ms、P95 8339 ms；身份 QA P50 1095.144 ms；测得最低空闲显存约 6866 MiB。
- InstantID loader：1692.0 ms；FaceAnalysis：1732.9 ms。
- PuLID loader：1156.5 ms；InsightFace loader：1459.5 ms。
- InstantID/PuLID 的 SDXL 生成峰值显存未测量，不能从 SD1.5 结果推断 12GB 可行或不可行。

## 十、构建回归

`16-build-regression.json` 最终状态为 PASS：

- `dotnet build server\VideoStudio.Server.csproj --nologo`：PASS，0 警告、0 错误。
- `dotnet build tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj --nologo`：PASS，0 警告、0 错误。
- `dotnet run --project tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj --no-build -- --self-test`：PASS。
- 多视角工具 Python 编译：PASS。
- `git diff --check`：PASS；日志中只有既有的 LF/CRLF 转换提示，没有 diff 错误。

## 十一、本轮新增/调整的代码、工作流和证据工具

新增或维护的主要文件：

- `C:\install\AI\VideoStudio\scripts\analyze_faceid_failure_20260817.ps1`
- `C:\install\AI\VideoStudio\scripts\run_faceid_headpose_probe_20260817.ps1`
- `C:\install\AI\VideoStudio\scripts\run_img2img_probe_20260817.ps1`
- `C:\install\AI\VideoStudio\scripts\run_multiview_build_regression_20260817.ps1`
- `C:\install\AI\VideoStudio\scripts\capture_sdxl_hardware_blocker_20260817.ps1`
- `C:\install\AI\VideoStudio\tools\head_pose_templates\create_head_pose_templates.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\evaluate_headpose_probe.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\evaluate_img2img_probe.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\write_multiview_environment_20260817.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\probe_instantid_pulid_assets_20260817.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\write_adapter_benchmarks_20260817.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\parallel_download_asset.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\finalize_multiview_evidence_20260817.py`
- `C:\install\AI\VideoStudio\tools\multiview_generation\build_multiview_html_20260817.py`
- `C:\install\AI\Workflows\19_sd15_faceid_headpose_openpose_v1_api.json`
- `C:\install\AI\Workflows\21_sdxl_instantid_multiview_probe_v1_api.json`
- `C:\install\AI\Workflows\22_sdxl_pulid_multiview_probe_v1_api.json`

InstantID 和 PuLID 节点以新增目录方式部署，没有覆盖原有节点：

- `C:\install\AI\ComfyUI\custom_nodes\ComfyUI_InstantID_20260817`
- `C:\install\AI\ComfyUI\custom_nodes\PuLID_ComfyUI_20260817`

## 十二、完整证据清单

JSON：

`01-environment.json`、`02-baseline-summary.json`、`03-head-pose-control.json`、`04-faceid-headpose-benchmark.json`、`05-instantid-deployment.json`、`06-instantid-benchmark.json`、`07-pulid-deployment.json`、`08-pulid-benchmark.json`、`09-img2img-benchmark.json`、`10-method-comparison.json`、`11-top-method-controlled-candidates.json`、`12-character-qa-results.json`、`13-golden-reference-pack-v3.json`、`14-selector-validation.json`、`15-performance.json`、`16-build-regression.json`、`17-final-acceptance.json`、`18-sdxl-hardware-blocker.json`、`adapter-asset-probe.json`。

以上文件均位于：

`C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01\`

HTML：

- `01-faceid-failure-analysis.html`
- `02-headpose-comparison.html`
- `03-instantid-comparison.html`
- `04-pulid-comparison.html`
- `05-img2img-comparison.html`
- `06-all-methods-comparison.html`
- `07-golden-reference-v3.html`

构建日志位于该 run 的 `logs` 目录。生成图、模板、manifest 和失败分析原始数据也保留在同一 run 目录中。

## 十三、下一步建议

不要继续在当前 SD1.5 基础模型上扩大样本，也不要放宽 QA 阈值。优先更换具备原生多视角/姿态控制能力的基础模型或控制路线；新路线准备好后，先重复 5 视角 × 3 seeds 的 15 样本 HeadPose Gate，只有 Dual 达到 30% 才扩展，达到 50% 才进入候选，达到 70% 且 Golden 达标才允许生产候选/LoRA PoC。

如需继续验证 InstantID/PuLID，应先对保留分片完成组装和 SHA 校验，补齐 SDXL、InstantID ControlNet、PuLID EVA，然后仅运行工作流 `21`、`22` 的最小探针；任何 loader PASS 都不能替代真实生成和人物身份/视角 Dual QA。

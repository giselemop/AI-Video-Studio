# AI Video Studio 人物身份基础能力修复执行结果

执行日期：2026-08-16（Asia/Shanghai）\
项目：`C:\install\AI\VideoStudio`\
本轮证据根目录：`C:\install\AI\Data\QA\identity_foundation_20260816\run_02`\
最终状态：**`NO_GO_IDENTITY_FOUNDATION`**

## 1. 结论先行

本轮已经具备真实的人物身份识别基础能力：InsightFace/ArcFace `buffalo_l/w600k_r50.onnx` 在本机独立 Worker 中实际加载并运行；真实检测、人脸数量、5/106 点 landmarks、Yaw/Pitch/Roll、512 维 embedding、余弦相似度比较，以及 HTTP API 契约均已通过验证。

但“同一人物稳定生成不同角度”尚未通过：Baseline 与 FaceID 的 7 个视角 × 3 个 seed 均实际生成成功，FaceID 优于 Baseline，但 30°/45°视角控制不稳定，合格 Golden Pack 只有 3 张，Selector 仍有 4/7 请求回退。因此本轮不启动 LoRA，不宣称人物身份基础能力可进入生产。

回答三个验收问题：

1. 是否具备真正人物身份识别能力：**是，工具级能力已通过**；
2. 是否稳定生成同人物不同角度：**否**；
3. 是否 `READY_FOR_CHARACTER_LORA_POC`：**否**。

## 2. 门禁结果

| Gate | 结果 | 证据 | 说明 |
|---|---|---|---|
| Gate A：Face Embedding | PASS | `03-identity-threshold-calibration.json` | 30 对本地校准样本，阈值候选 0.5；仍需人工复核后才可作为生产阈值 |
| Gate B：View Angle | PASS | `04-view-angle-calibration.json` | 已完成已知左右样本、镜像不变量和方向分离校准；生成候选仍不代表已经稳定 |
| Gate C：Controlled Generation | FAIL | `07-controlled-candidates.json` / `08-character-qa-v2.json` | 42 张全部技术成功，但身份通过 4 张、视角通过 18 张、双通过 3 张 |
| Gate D：Golden Pack | FAIL | `09-golden-reference-pack-v2.json` | 目标 10–20 张，当前仅 3 张，且没有 30°/45° Golden |
| Gate E：Selector | FAIL | `10-reference-selector-v2-validation.json` | 当前 7 个请求仅 3 个 direct，4 个 fallback，qualified rate 42.86% |
| Gate F：Identity Method | PASS | `06-identity-method-benchmark.json` | Baseline/FaceID 均实际生成；FaceID 为当前候选方法，但不是生产放行 |

## 3. 真实 InsightFace 部署与 Worker

部署结果：**`PASS_REAL_RUNTIME`**。

- 官方 InsightFace 0.7.3 Python source 位于 `C:\install\AI\IdentityWorker\vendor-src\insightface-0.7.3`；独立 Python 3.13.2 venv 位于 `C:\install\AI\IdentityWorker\venv`。
- 模型包为 `buffalo_l`：
  - detector：`det_10g.onnx`
  - embedding：`w600k_r50.onnx`，512 维
  - landmarks：`2d106det.onnx`、`1k3d68.onnx`
- 当前实际 Provider：`CPUExecutionProvider`；可用 Provider 为 `AzureExecutionProvider` 与 `CPUExecutionProvider`。
- 18084 Worker 只绑定 `127.0.0.1`，不对局域网暴露；主服务 18080 未被停止，ComfyUI 8188 也保持在线。
- `GET /health`、`POST /identity/analyze`、`POST /identity/compare`、`POST /identity/view-angle` 均已实际调用；分析接口在缓存命中和 compare 后复测均不返回原始 embedding 向量。
- InsightFace 可选 `face3d` 扩展在本机安装时被 MSVC 14.0 依赖阻塞；本轮使用官方 FaceAnalysis 运行路径并省略可选 renderer，真实检测/embedding/landmark 仍已运行。这一限制已保留为 `BLOCKED_DEPENDENCY_MSVC14_FOR_OPTIONAL_FACE3D_BUILD`，没有伪装成完整编译安装。

主身份样本实际分析结果：1 张脸、检测置信度约 0.777、5 点与 106 点 landmarks 均存在；Yaw 3.441°、Pitch -7.001°、Roll -1.945°；图像清晰度未触发严重模糊；遮挡检测为 `unmeasured`，要求人工复核。

HTTP 契约和隐私边界证据：`14-worker-api-contract.json`。

## 4. 阈值与视角校准

### 4.1 身份阈值

三组校准队列均完成 10/10：

- SamePersonEasy：10 对；
- SamePersonHard：10 对；
- DifferentPerson：10 对。

当前推荐阈值为 raw cosine `0.5`。本地校准结果为 accuracy `1.0`、SamePersonHard recall `1.0`、false accept rate `0.0`，统计为 TP 20、FP 0、TN 10、FN 0。

校准状态仍是 **Preliminary / ManualReviewRequired**：Hard 队列含本地历史生成视图，DifferentPerson 不是公开人口学 benchmark，阈值必须在人工查看 contact sheet 后才可升级为生产阈值。

### 4.2 视角校准

使用真实已标注的左侧样本、其镜像右侧控制样本和正面镜像样本完成校准：

- 已知左侧 Yaw：`-42.080°`；
- 已知右侧 Yaw：`39.537°`；
- 左右分离：`81.617°`；
- 正面镜像不变量：PASS；
- 方向分离：PASS；
- 当前左右极性：`leftPolarity=1`。

视角原始区间：front `abs(yaw) < 15°`，30°候选 `[12°,40°)`，45°候选 `[27°,62°)`，profile `>=55°`。这些区间证明测量/校准链路有效，不代表生成器一定会服从目标角度。

## 5. PoseTemplateLibrary 与真实 Pose Control

已生成并登记 13 个模板：`front`、`front_left_30`、`front_right_30`、`left_45`、`right_45`、`left_profile`、`right_profile`、`half_body_front`、`half_body_left45`、`half_body_right45`、`full_body_front`、`full_body_left45`、`full_body_right45`。

模板来源为 `manual_standard_openpose_skeleton_v2`，Control 类型为 OpenPose；实际 workflow 使用 `LoadImage` + `ControlNetApplyAdvanced` + `control_v11p_sd15_openpose.pth`，不是只把视角写进 prompt。模板和登记文件位于：

`C:\install\AI\Workflows\CharacterPoseTemplates`\
`C:\install\AI\Data\QA\identity_foundation_20260816\run_02\pose_templates`

所有模板仍保留人工复核要求。尤其 half/full body 的头部、脚部、身体覆盖与姿态语义，不能只用单张脸的 detector 数值代替。

## 6. Identity Method Benchmark

两种可用方法严格采用同一基础条件：同一 master、SD1.5 checkpoint、512×768、28 steps、DPM++ 2M Karras、CFG 5.8、同一 OpenPose ControlNet、同一 7 视角、同一 3 个 seed（240101/240102/240103）。

| 方法 | 请求 | 实际生成 | 身份通过 | 视角通过 | 双通过 |
|---|---:|---:|---:|---:|---:|
| Baseline IP-Adapter Plus Face | 21 | 21 | 0 | 9 | 0 |
| IP-Adapter FaceID Plus V2 | 21 | 21 | 4 | 9 | 3 |
| InstantID | 21 | 0 | 0 | 0 | 0 |
| PuLID | 21 | 0 | 0 | 0 | 0 |

FaceID 是当前相对更好的方法，但其 4/21 identity pass 和 3/21 dual pass 仍不足以放行。InstantID 的 node、model 和 SDXL base checkpoint 缺失；PuLID 的 node 和 model 缺失。本轮没有把缺失方法偷偷替换成 prompt-only 或 Baseline。

## 7. Controlled Candidates / QA v2

当前候选总量 42 张，全部来自真实 ComfyUI 生成：

- technical success：42/42；
- identity pass：4/42；
- view pass：18/42；
- dual pass：3/42；
- hard reject：39/42。

QA v2 已记录：face detected/count/confidence、raw similarity/decision、Yaw/Pitch/Roll/view/confidence、blur/lighting/occlusion、hair/clothing、body coverage、head/feet crop、hard reject flags、auto/manual review、analysis time 和输入 workflow 索引。遮挡、头发、服装以及身体构图仍明确标为人工复核或 `unmeasured`，没有把未测量当作 PASS。

实际失败模式是：部分 30°/45°模板生成结果仍接近正面，部分左右方向发生反转或跨区间；FaceID 能提高身份相似度，但不能保证多视角身体/头部转向和服装一致性。ControlNet 强度提高到过强时出现背面/无脸倾向，因此正式 benchmark 保留可运行但不稳定的 0.85 配置，并将不稳定性记录为 Gate C 失败证据。

## 8. Golden Pack 与 Selector

当前自动推荐 Golden Pack 只有 3 张，均需人工确认：

- front：1 张；
- half_body_front：1 张；
- full_body_front：1 张；
- front_left_30、front_right_30、left_45、right_45：均为 0 张。

因此目标 10–20 张未满足，`loRAAllowed=false`。Selector 当前 7 个目标请求中只有 front、half-body-front、full-body-front 能 direct，其他 4 个请求 fallback 到 front 或 blocked；直接合格率为 42.86%，Gate E 失败。

## 9. 性能与资源

- 42 次 embedding 分析：p50 `1170.2945 ms`，最大 `1581.711 ms`，CPU Provider；
- 42 次图像生成：p50 `4054 ms`，最大 `8285 ms`；
- benchmark 期间显存总量约 `12282 MiB`，生成后空闲约 `6898–6954 MiB`；
- 本轮 SD1.5 + FaceID + OpenPose 在 12GB RTX 4070 上实际可跑，没有发生 OOM；这不等于 Wan2.2 Animate、HunyuanVideo-1.5 或 SDXL 路线在相同硬件上可跑。

## 10. 构建与回归

已通过：

- `dotnet build server\VideoStudio.Server.csproj --nologo`：0 警告、0 错误；
- `dotnet build tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj --nologo`：0 警告、0 错误；
- QualityHarness `--self-test`：Passed。

Git HEAD 为 `d6ec38d076a8b0336d349c36df5c123f2c941ac8`。构建回归记录时工作区有 141 个 dirty files；报告写入后当前观测为 142 个，均按要求保留。本轮没有执行 reset、clean、checkout 或删除用户已有工作。构建日志和退出码见 `12-build-regression.json`。

## 11. 阻塞与未验证边界

以下项目明确没有被冒充为完成：

- `BLOCKED_DEPENDENCY_MSVC14_FOR_OPTIONAL_FACE3D_BUILD`：可选 face3d 编译依赖缺失；真实 FaceAnalysis runtime 已通过替代路径运行；
- `BLOCKED_INSTANTID_NODE/MODEL/BASE`：当前 ComfyUI 没有 InstantID node、model 和 SDXL base；
- `BLOCKED_PULID_NODE/MODEL`：当前 ComfyUI 没有 PuLID node 和 model；
- `BLOCKED_MANUAL_REVIEW`：头发、服装、遮挡、身体覆盖、左右 45°语义与 Golden Pack 需要人工签字；
- `BLOCKED_LORA`：Gate A–F 未全部通过，禁止开始 Character LoRA POC；
- `BLOCKED_60S_ACTION`：按本轮提示词明确不在本轮范围；
- 本轮未执行中文 TTS、B04/B05/B06/B08 Driving/Pose、Wan2.2 Animate、HunyuanVideo-1.5 或 60 秒剧情片验收；这些任务不能从本报告推断为已完成。

## 12. 本轮输出索引

证据根目录：`C:\install\AI\Data\QA\identity_foundation_20260816\run_02`

- `01-environment.json`
- `02-insightface-deployment.json`
- `03-identity-threshold-calibration.json`
- `04-view-angle-calibration.json`
- `05-pose-template-library.json`
- `06-identity-method-benchmark.json`
- `07-controlled-candidates.json`
- `08-character-qa-v2.json`
- `09-golden-reference-pack-v2.json`
- `10-reference-selector-v2-validation.json`
- `11-performance.json`
- `12-build-regression.json`
- `13-final-acceptance.json`
- `14-worker-api-contract.json`
- `identity-method-comparison.html`
- `multiview-candidates-contact-sheet.html`
- `golden-reference-contact-sheet.html`
- `attempt_01\`：第一轮 42 张生成与证据快照，未被第二轮覆盖

## 13. 变更边界

本轮新增/修复的项目内能力主要是：

- `tools\identity_foundation\identity_foundation.py`：真实 FaceAnalysis、校准、Pose Template、QA v2、loopback Worker；另修复了缓存分支可能把内部 `_embedding` 放进 HTTP 分析返回的问题；
- `scripts\run_identity_foundation_20260816.ps1`：可复现的 7 视角 × 3 seed Baseline/FaceID benchmark；
- `C:\install\AI\Workflows\18_sd15_faceid_openpose_v1_api.json`：SD1.5 FaceID + OpenPose workflow；
- `C:\install\AI\ComfyUI\venv\Lib\site-packages\identity_worker_runtime.pth`：让 ComfyUI 复用独立身份 Worker runtime，不升级 ComfyUI 自身 NumPy/Torch；
- `C:\install\AI\Models\InsightFace\models\buffalo_l` 与 FaceID 权重：实际运行所需模型资产；
- 本报告和 `run_02` 全部新证据。

结论保持不变：**真实身份识别基础已具备；稳定多视角人物生成尚未具备；LoRA、动作和下一阶段模型测试必须等待 Identity Foundation 门禁重新达到全 PASS。**

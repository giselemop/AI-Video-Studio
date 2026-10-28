# AI Video Studio 人物视频质量优化执行结果

执行复核时间：2026-08-14 13:30–2026-08-15 00:10（Asia/Shanghai）\
项目根目录：C:\install\AI\VideoStudio\
证据原则：只采用本机代码、数据库、模型/工作流文件、任务记录、运行日志、输出媒体、FFprobe 和本轮可复核命令结果；历史报告中的预期值不作为本轮新执行结果。

## 最终状态

最终状态：CONDITIONAL GO

1. 本机实际可复核的模型/路线：SD1.5 静态、LTX 2B FP8 v3 人物 I2V、Wan2.2 TI2V-5B、SD1.5 + IP-Adapter Plus 静态身份路线。
2. HunyuanVideo-1.5、Wan2.2 Animate 的 ComfyUI 核心节点存在，但本机没有对应权重或可运行目标工作流；本次已完成部署前置核查，目标模型运行被本地资产与 12GB 显存余量阻塞。
3. 当前最佳人物视频工作流是 13_sd15_ipadapter_face_v1_api.json 生成静态身份锚点，再进入 12_ltx_face_stable_v3_api.json。
4. 当前正式推荐链是单脸参考、320×416、24 FPS、73 帧、guide 0.45、locked-off、small motion，先人工看首/中/尾帧。
5. 2026-08-13 的最新 20 个 LTX v3 生产样本全部技术完成，平均脸部代理 93.60，平均身份参考代理 93.73。
6. 2026-08-11 的受控 20-run 小动作实验平均脸部代理 95.15；它是实验最佳，不替代最新生产批次的 93.60。
7. 相对主要旧版 4-case Baseline 平均 92.14，最新生产批次提升 1.46 个脸部代理分数，约 1.59%。
8. 静态 IP-Adapter 矩阵的参考相似度代理从 95.88 提升到 97.17，提升 1.29 个百分点；尚未证明同等提升能传递到复杂 I2V。
9. 5 秒复杂动作仍未通过：任务 745、746 的脸部代理为 88.58、91.25，并出现手部/结构/时序问题。
10. RTX 4070 12GB 能运行当前低分辨率路线，但显存已接近上限，是部分瓶颈，不是所有脸部问题的唯一原因。
11. 当前最大剩余问题是复杂动作控制、跨镜头身份/场景一致性和人工内容验收。
12. 正式生产建议保持 Conditional Go；3 秒受监督 Draft 可继续，复杂长镜头、无人值守、局域网/公网发布仍 No-Go。
13. 本轮已完成中文 TTS 修复、REF1/REF3/REF5 静态多参考 Benchmark 和 B04/B05/B06/B08 三 seed Pose v2 技术 Benchmark；动作语义仍未通过，目标模型仍需 24GB 级机器和权重后再测。

## 一、执行范围与证据边界

本轮实际执行了：

- API /api/health、ComfyUI /system_stats、ComfyUI /object_info、端口、进程、GPU、磁盘、Python/PyTorch、FFmpeg/FFprobe、MySQL 版本复核。
- 真实模型和工作流文件清点，包含尺寸、实际路径和当前可用性。
- 数据库只读核验：schema_migrations、质量实验、质量实验运行、任务、结果、当前 Project 18 / Episode 28 20-shot 批次。
- 旧 Baseline、LTX v3、Wan2.2、IP-Adapter 和复杂动作输出的本机文件、日志、FFprobe 元数据复核。
- .NET build、Vue production build、git diff --check、阶段 0 静态证据回归。

本轮没有通过受保护业务 API 新建业务任务（缺少管理员测试凭据，业务 API 返回 HTTP 401），但实际重新执行了 8 个中文 TTS 修复任务、1 个 Episode 预览任务，以及通过直连 ComfyUI REST 队列执行的 9 个 REF1/REF3/REF5 静态样本和 24 个 Pose v2 样本。历史任务没有被改写；新增任务、prompt、输出媒体和 FFprobe 结果均单独记录。

本轮没有执行数据库迁移、备份恢复、删除文件、下载新模型、改变监听地址或改变 GPU 并发。

## 二、环境复核

| 项目 | 本机实测 |
|---|---|
| 日期时间 | 2026-08-14 13:35 左右，Asia/Shanghai |
| Windows | Windows 10 Home，Version 2009，OS Build 26200，64-bit（系统实际返回值） |
| CPU | 13th Gen Intel(R) Core(TM) i5-13600KF |
| GPU | NVIDIA GeForce RTX 4070 |
| GPU Driver | 591.86 |
| VRAM | 总 12282 MiB；复核时使用约 650 MiB，空闲约 11361 MiB |
| RAM | 系统总内存 34163720192 bytes，约 31.8 GiB；ComfyUI 当前可用约 16.8 GiB |
| C: 剩余空间 | 203631874048 bytes，约 189.6 GiB；系统盘与模型盘相同 |
| E: 剩余空间 | 298448060416 bytes，约 278.1 GiB |
| .NET SDK | dotnet --version = 10.0.103；项目目标框架为 net8.0 |
| Node | v20.18.1 |
| npm / pnpm | npm 10.8.2；pnpm 11.19.0 |
| Python | C:\install\Python\python.exe = 3.13.2；ComfyUI venv = 3.13.2 |
| CUDA | NVIDIA-SMI CUDA Version 13.1；ComfyUI PyTorch CUDA 13.0 |
| PyTorch | ComfyUI v2.11.0+cu130，cuda_available=True |
| ComfyUI | 0.31.0；API Python 3.13.2 |
| FFmpeg / FFprobe | C:\install\FFmpeg\bin 下 9.0 essentials build |
| MySQL | MySQL Community Server 8.0.22；require_secure_transport=0，bind_address=*（本机数据库状态，仍是安全风险） |

服务：

- API：http://127.0.0.1:18080，在线，/api/health 返回 200。
- ComfyUI：http://127.0.0.1:8188，在线，/system_stats 和 /object_info 返回 200。
- 两个端口当前均为 loopback-only；没有把 API、ComfyUI 或防火墙改为公网监听。
- 18081 Vite 开发服务器当前未监听。

## 三、Git 状态

执行前：

- Branch：main
- Commit：d6ec38d076a8b0336d349c36df5c123f2c941ac8
- status：34 个已修改 tracked 文件、76 个未跟踪条目、0 个删除、0 个重命名。

执行后：

- Branch：main
- Commit：仍为 d6ec38d076a8b0336d349c36df5c123f2c941ac8
- 本轮新增/修改：`server/MediaProductionServices.cs`、`server/FfmpegService.cs`、REF3/REF5/Pose v2 工作流和 3 个可复现实测脚本；结构化 JSON/媒体写入 C:\install\AI\Data\QA，不进入 Git 仓库。
- 执行前已有的代码、迁移、脚本和文档修改全部保留，没有 reset、checkout、clean 或删除。
- 未创建提交。

执行前已存在的主要修改/新增范围：

- 修改：server、web、config、database 相关现有文件；项目中文档和验收档案。
- 新增：server 的 AssetPathPolicy、FaceQuality、QualityOptimization、GPU gate、任务租约、生产核心等文件。
- 新增：004–008 迁移文件、质量/生产验收报告、阶段回归脚本和 Playwright 测试。
- 执行前已有的用户修改全部保留；本轮新增代码与工作流单独列出，不把旧修改冒充为本轮新代码。

## 四、代码与工作流修改摘要

### Backend

- GenerationQueue、ComfyUiClient 和 ProductionEndpoints 已加入人物 I2V 参数归一化：根据首帧画幅选择 320×416、512×320 或 384×384；人物稳定路线限制 73/121 帧；guideFrameIndex 保持在末帧之前。
- 有角色参考时默认采用 12_ltx_face_stable_v3；无角色参考时保留 05_wan22_ti2v_5b；GPU 队列固定为 1。
- 任务输入包含 seed、workflow、参考图、motionProfile、allowLongVideo、参考强度和结果质量字段。
- QA 回炉改变 seed，并把参考强度、画幅、帧数和动作档位写入 repair 记录；失败镜头最多按既有规则定向重做。
- 本轮实际改动 `MediaProductionServices.cs` 的本地 TTS 编码/音频有效性保护，以及 `FfmpegService.cs` 的临时输出扩展名处理；已通过真实 TTS/预览任务回归。
- 这些修改属于必要的质量/稳定性修改；不改变项目、Episode、Shot 的基本 CRUD 和旧任务结果。

### Frontend

- App.vue 已把人物有参考图的 I2V 默认参数映射到 320×416、73 帧、small motion、guide 0.45；工作流列表显示模型/工作流信息。
- UI 保留 Wan2.2 无参考图入口和按输入画幅自动选择的提示。
- 本轮没有新增前端业务修改；只完成现状构建验证。

### Database

- 质量实验表、质量运行表、Golden sample 和 repair run 已在现场数据库存在，并可读出真实运行记录。
- 任务结果保存 quality_score、qc_json、seed、duration_ms、vram_peak_mib 和输出路径。
- 当前数据库的 schema_migrations 实际记录为 002、003、004、005、007、008；006_repair_garbled_text.sql 文件存在但未出现在已应用列表。
- 本轮数据库无结构修改、无迁移执行、无清理；为保留可追溯性新增了 1027–1034 的音频修复任务和 1043 的预览任务记录。已有迁移是否可在另一套数据库重复执行，本轮未重新演练；现场已应用迁移保持旧业务记录可读。

### ComfyUI / 模型

- 新增/使用的工作流为 05_wan22_ti2v_5b_api.json、09_character_master_reference_v2_api.json、12_ltx_face_stable_v3_api.json、13_sd15_ipadapter_face_v1_api.json、14_sd15_controlnet_openpose_v1_api.json、15_sd15_ipadapter_ref3_api.json、16_sd15_ipadapter_ref5_api.json、17_sd15_ipadapter_openpose_v2_api.json。
- ComfyUI 直连实际完成 REF1/REF3/REF5 共 9 个静态样本；OpenPose v2 实际完成 B04/B05/B06/B08 各 3 个关键帧和 3 个 I2V，共 24 个样本，但动作语义门未通过。
- ComfyUI 0.31.0 核心节点列出 WanAnimateToVideo/WanAnimate2ToVideo/HunyuanVideo15ImageToVideo；模型目录没有对应权重，Workflows 没有目标工作流，未把节点存在写成模型已支持。

## 五、现有 Baseline

主要 Baseline：旧版 LTX character-lock，任务 611–614，工作流 03_ltx_character_lock_api，模型 ltxv-2b-0.9.8-distilled-fp8.safetensors。

| 指标 | 真实值 |
|---|---|
| Width / Height | 实际任务归一化为 320×416 |
| FPS / Frames | 24 FPS；73 帧或 121 帧 |
| Steps | 8 |
| Sampler | euler |
| CFG / Guidance | CFG 3；guide strength 0.45 |
| 生成时间 | 11.461–17.208 秒；4-case 平均约 15.083 秒 |
| Peak VRAM | 10345–10617 MiB |
| 技术成功率 | 4/4 |
| 主要脸部代理 | 94.19、91.34、90.35、92.69 |
| Baseline 平均分 | 92.14 |
| Primary hard reject | 2/4，50%；任务 612、613 |
| 人工评分 | 未保存统一 1–5 分；全部必须人工复核 |

扩展旧对照集任务 611–618 的平均脸部代理为 91.44，5/8 被旧诊断判为拒绝；该集合混合旧版与 v2、3 秒与 5 秒，不能替代主要 4-case Baseline，只作为风险对照。

Baseline 视频目录：C:\install\AI\Data\Videos\，代表文件为 task_611_task_611_00001_.mp4 至 task_618_task_618_00001_.mp4。

## 六、候选模型执行状态

### 当前 LTX Workflow

状态：SUPPORTED_LOW_VRAM

- 模型：ltxv-2b-0.9.8-distilled-fp8.safetensors，4,461,695,684 bytes。
- 路径：C:\install\AI\Models\video_models\ltxv-2b-0.9.8-distilled-fp8.safetensors。
- Precision / Quantization：FP8 distilled；运行日志显示 ComfyUI 动态显存加载并使用 CPU offload 设备。
- Workflow：12_ltx_face_stable_v3_api.json。
- 参数：320×416、24 FPS、73 帧、8 steps、euler、CFG 3、guide 0.45、small motion。
- 受控 20-run 实验任务 721–740：20/20 技术成功，平均脸部代理 95.15，平均生成 14.595 秒，峰值 11988 MiB。
- 最新 Project 18 / Episode 28 任务 986–1005：20/20 技术成功，平均脸部代理 93.60，平均参考相似度 93.73，平均 10.822 秒，峰值 12012 MiB。
- OOM / Crash：上述已运行任务没有 OOM 或 Crash；5 秒复杂动作仍有质量拒绝。

### HunyuanVideo-1.5

状态：BLOCKED_LOCAL_ASSETS_AND_HARDWARE_HEADROOM

- ComfyUI 核心 object_info 实际列出 HunyuanVideo15ImageToVideo 和 EmptyHunyuanVideo15Latent，但本机模型目录没有 HunyuanVideo-1.5 权重，工作流目录没有可运行的目标 API workflow。
- 因为没有权重/工作流对，无法提交真实目标推理；这不是 OOM 复现。现有 LTX 路线历史峰值 12012/12282 MiB，仅剩约 270 MiB，不能把 12GB 写成该目标硬件可部署。
- 完整证据：C:\install\AI\Data\QA\model-deployment-20260814.json。

### Wan2.2 TI2V-5B

状态：SUPPORTED_LOW_VRAM

- 模型：wan2.2_ti2v_5B_fp16.safetensors，9,999,658,848 bytes。
- 路径：C:\install\AI\Models\diffusion_models\wan2.2_ti2v_5B_fp16.safetensors。
- 依赖：umt5_xxl_fp8_e4m3fn_scaled.safetensors 6,735,906,897 bytes；wan2.2_vae.safetensors 1,409,400,960 bytes。
- Workflow：05_wan22_ti2v_5b_api.json；steps 20、sampler uni_pc、scheduler simple、CFG 5.0。
- 真实任务 574：320×416、49 帧、24 FPS、2.009 秒、30.862 秒生成、11861 MiB；首/中/尾帧人工观察稳定。
- 真实任务 575：512×320、49 帧、11722 MiB；竖幅参考图被横幅输出裁掉双眼，判为 FACE_BAD。
- 真实任务 577：自动归一化到 320×416、49 帧、11935 MiB；裁脸消失，但中后段出现时序彩色伪影。
- OOM / Crash：上述任务无 OOM/Crash；显存接近 12GB，质量依赖画幅、seed 和短动作。

### Wan2.2 Animate

状态：BLOCKED_LOCAL_ASSETS_AND_HARDWARE_HEADROOM

- ComfyUI 核心 object_info 实际列出 WanAnimateToVideo/WanAnimate2ToVideo，并显示 reference_image、face_video、pose_video 等输入契约；本机没有 Wan2.2 Animate 权重、Driving Video 输入链或目标 workflow。
- 没有权重/工作流对，无法提交真实目标推理；B08 的 Pose v2 结果是 SD1.5 + OpenPose + LTX 的控制链，不冒充 Wan Animate。
- 完整证据：C:\install\AI\Data\QA\model-deployment-20260814.json。

### HunyuanCustom

状态：NOT_TESTED

- 没有发现对应权重、工作流或多 Reference 运行链。

### 额外静态身份路线

SD1.5 v1-5-pruned-emaonly-fp16.safetensors 与 13_sd15_ipadapter_face_v1_api.json 状态为 SUPPORTED_LOW_VRAM（静态阶段）。

- SD1.5 权重：C:\install\AI\Models\checkpoints\v1-5-pruned-emaonly-fp16.safetensors，2,132,696,762 bytes。
- IP-Adapter Plus：C:\install\AI\Models\ipadapter\ip-adapter-plus-face_sd15.safetensors，98,183,288 bytes。
- CLIP Vision：C:\install\AI\Models\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors，2,528,373,448 bytes。
- OpenPose：C:\install\AI\Models\controlnet\control_v11p_sd15_openpose.pth，1,445,235,707 bytes。
- IP-Adapter 静态矩阵 50/50 技术成功，平均 face proxy 100，平均 reference similarity proxy 97.17，峰值显存约 4742 MiB。
- 这只证明静态关键帧身份代理改善，不证明复杂 I2V 已解决。
- LoRA 目录当前为空，没有角色 LoRA 质量结论。

## 七、Benchmark 测试矩阵

状态说明：R=有真实输出；SP=只有相近 stress probe，不能当作完整 case 通过；NR=未运行；BLOCKED=目标资产/硬件/输入合同阻塞，未提交目标推理；NA=该路线不是视频模型；HR=真实输出但自动/人工证据存在拒绝风险。

| Model × Case | B01 静止/呼吸/眨眼 | B02 正脸转45度 | B03 微笑/嘴部 | B04 走2–3步 | B05 拿杯子 | B06 转身/坐下 | B07 三Shot一致 | B08 Driving | B09 Push-in | B10 复杂背景 |
|---|---|---|---|---|---|---|---|---|---|---|
| LTX v3 3s | R：986–988，3 seeds | SP：743–746 仅小幅转头，不是45度 | NR | TECH：Pose v2 3 seeds；动作语义 FAIL | TECH：Pose v2 3 seeds；PARTIAL/FAIL | TECH：Pose v2 3 seeds；动作语义 FAIL | 静态 REF1/3/5 已完成；非 I2V 三 Shot | TECH：Pose v2 3 seeds；动作语义 FAIL | SP：旧 push-in probe | NR |
| Wan2.2 TI2V-5B | R/HR：574、577；575 画幅失败 | NR | NR | NR | NR | NR | NR | NR | NR，未做同输入推镜 | NR |
| LTX legacy/v2 | R/HR：611–618 | SP：小幅转头 | NR | SP：614/618 | NR | NR | NR | NR | SP：613/617 | NR |
| SD1.5 + IP-Adapter | NA；静态矩阵另计 | NA | NA | NA | NA | NA | NA | NA | NA | NA |
| Wan2.2 Animate | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED（无权重/Driving 输入） | BLOCKED | BLOCKED |
| HunyuanVideo-1.5 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED（无权重/工作流） | BLOCKED | BLOCKED |
| HunyuanCustom | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |

每一个 case 的 seed 1/2/3、实际 task/output、未运行原因和可量化字段已同步到 C:\install\AI\Data\QA\benchmark-results.json。未把 NR 写成失败。

本轮新增直连 ComfyUI Benchmark：REF1/REF3/REF5 各 3 seed，共 9/9 技术成功；B04/B05/B06/B08 各 3 seed，每个 seed 先生成 OpenPose + IP-Adapter 全空 latent 关键帧，再生成 81 帧、320×416 的 LTX I2V，共 24/24 技术成功。视觉门结论为：B04 未出现可验证的 2–3 步走动，B05 只有一个 seed 出现杯子/手但不稳定，B06 未出现转身坐下，B08 未出现可验证车辆/方向盘；因此是“Benchmark 完成、动作质量未通过”，不是“动作已通过”。证据目录：C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_v2。

## 八、Benchmark-A：Common Input Benchmark

本机没有完成“所有普通 I2V 模型使用完全相同 Reference、Prompt、Shot、duration、resolution、frames”的完整集合，因此不能给出虚假的基础模型排名。

| Engine | Face | Identity | Body | Motion | Temporal | Visual | Total | Time | VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LTX v3，Project 18 最新 20-shot | 93.60 | 93.73 | 未实现 | small/manual | 3/20 有伪影代理 | 未统一 | 未计算 | 10.822s avg | 12012 MiB |
| Wan2.2，task 574 matched aspect | 未记录 | 未记录 | 人工稳定 | 小动作 | 人工稳定 | 未统一 | 未计算 | 30.862s | 11861 MiB |
| LTX legacy primary Baseline | 92.14 | 未记录 | 未实现 | 5 秒项需人工 | 旧诊断有拒绝 | 未统一 | 未计算 | 15.083s avg | 10617 MiB |

结论：Common Input 排名暂缓。当前数字可以证明路线边界和风险，不能证明不同模型在严格同输入条件下的纯基础能力排序。

## 九、Benchmark-B：各模型最佳能力结果

| Engine / Workflow | 使用的最佳能力 | 实际结果 | 生产判断 |
|---|---|---|---|
| SD1.5 + IP-Adapter Plus | 静态身份参考 | 50/50 成功；face 100；reference similarity 97.17 | 作为身份锚点，不能直接替代 I2V |
| LTX v3 | 单脸 guide、320×416、73 帧、small motion | 最新 20-shot 20/20 技术成功；93.60 avg；3/20 伪影代理告警 | 当前正式人物 Draft |
| Wan2.2 TI2V-5B | 无参考或短动作、匹配画幅、49 帧 | task 574 人工稳定；575 画幅失败；577 时序伪影 | 无参考短动作实验路线 |
| LTX v3 5 秒 controlled-complex | 121 帧、头部/肩部动作 | 743/744 可继续人工审核；745/746 被脸部/手部/结构风险拒绝 | 不能作为默认生产 |

纯质量与正式推荐不是一回事。当前正式推荐综合了质量、稳定性、4070 可运行性、速度和生产成功率：LTX v3 3 秒 Draft 优于一次性追求 5 秒复杂动作。

## 十、Reference Pack Benchmark

### REF1

- 输入：单张正脸/单脸身份锚点 C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png。
- 实际用于任务 721–740、957 和 Project 18 任务 986–1005 的人物参考链。
- 静态预检 face proxy 100；任务 957 视频 face 96.02、reference similarity 95.91、identity drift 3.60。

### REF3

- 物理文件存在，包括正脸、identity_three_quarter 等标准图。
- 本轮通过 `15_sd15_ipadapter_ref3_api.json` 实际把三张图用 ImageBatch 链合并，并由 IPAdapterAdvanced `combine_embeds=average` 运行 3 个 seed；9 个 REF 样本全部技术成功，输出与 prompt/seed/prompt id 已记录。
- 这是静态身份一致性 Benchmark，不是多参考 I2V；静态 contact sheet 显示脸型、发型、胡须和五官总体稳定，仍需人工逐镜评分。

### REF5

- 物理文件存在，包括正脸、三分之四、半身和全身候选。
- 本轮通过 `16_sd15_ipadapter_ref5_api.json` 实际把五张图用 ImageBatch 链合并，并由 IPAdapterAdvanced `combine_embeds=average` 运行 3 个 seed；五张输入中的第 5 张是已验证正脸的确定性裁剪变体，不是新人物。
- 这是静态身份一致性 Benchmark，不是多参考 I2V；静态 contact sheet 显示总体身份稳定，仍需人工逐镜评分。

结论：REF1/REF3/REF5 静态多参考链已实际验收通过技术执行，不能据此宣称多参考 I2V 已通过。已观察到的主要失败仍是人物参考与输出画幅不匹配、低分辨率时序漂移和动作/控制不足；REF3/REF5 的下一步是把已验证参考包接入 I2V 并做镜头级人工评分。

## 十一、动作控制 Benchmark

| 路线 | B04/B05/B06/B08 实际状态 | Body | Motion | Temporal | Hard Reject |
|---|---|---|---|---|---|
| Free I2V / LTX v3 | 3 秒小动作可运行；5 秒复杂 probe 745/746 有问题 | 未实现自动分数，手部/身体需人工 | 3 秒受限；复杂动作未通过 | 5 秒有结构/时序风险 | 3 秒 0/20 自动拒绝；5 秒 2/4 stress probe 拒绝 |
| Wan2.2 TI2V-5B | 49 帧短动作 task 574 可观察；无物体接触验收 | 人工稳定/失败依赖画幅 | 无 Driving/Pose | task 577 中后段伪影 | 画幅失败和时序失败分别保留 |
| Driving Video | Wan Animate 和 Driving 输入未准备 | 未测试 | 未测试 | 未测试 | 未测试 |
| Pose / Retarget | OpenPose v2 实际 12 个关键帧 + 12 个 LTX I2V 视频，24/24 技术成功 | 关键帧存在上半身/多人/手部问题；无可靠身体评分 | B04/B06/B08 语义失败，B05 仅一个 seed 部分出现杯子 | 81 帧 WEBP 输出可读；复杂动作时序仍需人工 | 动作语义门未通过 |

动作链结论：本轮已把 OpenPose 控制输入、IP-Adapter 身份锁定、空 latent 全身尝试和 LTX I2V 实际跑通，但结果证明当前 SD1.5+ControlNet+LTX 组合不能稳定表达走动、拿杯、转身坐下或 Driving 语义。动作变形不是单一“换模型”问题；下一步应使用真实 pose/driving 视频与对应 Animate/Retarget 模型，而不是继续把 prompt 文字当作动作控制。

## 十二、自动 QA 结果

### Face Detection

- 实现：server/FaceQualityServices.cs 的 CPU face-region proxy，不是 landmark 或人脸识别模型。
- 输入：PNG/JPG 或视频；视频默认抽样最多 7 帧。
- 输出：画幅、面板布局、局部边缘能量、均值/对比度、face similarity、anomaly、high saturation、artifact、black frame 等。
- 图像拒绝阈值：panel layout >= 0.42、detail < 0.035 或局部标准差 < 0.018。
- 视频拒绝阈值包括画幅不匹配、结构变化、彩色伪影、足够多的视觉伪影、稳定性过低或极端帧过多。
- 误判：光照、快速镜头、画面裁切、非人脸主体和强表情可能触发 proxy；所以结果通常是 NeedReview。
- 可靠程度：低到中等，只能做筛查和回炉触发。

### Identity Similarity

- 使用首帧/相邻帧和可选参考图的图像特征 proxy，输出 referenceSimilarityProxy、faceSimilarityToFirstFrame、identityDriftProxy。
- 没有独立的人脸 embedding/识别模型，不能证明真实人物身份相同。
- 可靠程度：低到中等；task 957 的 95.91 只表示当前 proxy 结果。

### Pose / Body

- 当前没有已实现、已验收的 pose landmark、身体关键点或手部接触 QA。
- ControlNet/OpenPose 文件存在，但只有 loader smoke，不能把它写成 Pose QA 已通过。
- 当前可靠程度：未实现；必须人工检查。

### Temporal

- 使用相邻帧相似度、首帧相似度、结构差异、颜色饱和度和极端帧计数。
- 对彩色块、鬼影、明显脸部突变有筛查价值。
- 对动作是否符合语义、手是否拿住杯子、转身是否合理没有判断能力。

仍必须人工检查：身份、眼睛/嘴/发际线、手部和物体接触、动作语义、跨 Shot 连续性、背景/镜头关系、字幕音画同步和最终内容审查。

## 十三、Hard Reject

主要可比 Baseline：任务 611–614，2/4 = 50%。\
最新 Project 18 LTX v3：任务 986–1005，自动 face reject 0/20 = 0%，但 3/20 有视觉伪影 proxy，20/20 仍需人工审核。\
5 秒 controlled-complex：任务 743–746，2/4 被脸部/手部/结构风险拒绝；不能用 3 秒 0% 推导复杂动作 0%。

下表是依据实际输出/日志的人工主类别归档，不是后端已经实现的自动分类器：

| 类型 | 旧 Baseline 主拒绝 | 最新 3 秒批次 | 5 秒复杂 stress |
|---|---:|---:|---:|
| FACE_BAD | 1 | 0 | 1 |
| IDENTITY_DRIFT | 1 | 0 | 0 |
| BODY_BAD | 0 | 0 | 1 |
| HAND_BAD | 0 | 0 | 1 |
| MOTION_BAD | 0 | 0 | 0 |
| TEMPORAL_BAD | 0 | 0 | 0（但有伪影告警） |
| BACKGROUND_BAD | 0 | 0 | 0 |
| OTHER / legacy unclassified | 0 | 0 | 0 |

改善最大的类别是 3 秒人物脸部稳定性和明显伪影筛查；复杂动作的 BODY/HAND/控制问题没有被解决。

## 十四、模型综合排名

分数为 proxy 或实际记录，不是人工电影感评分。

| Rank | Engine | Production Value | Face | Identity | Motion | Speed | VRAM |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | LTX v3 3s Draft | 4/5 | 93.60 最新批次；95.15 受控实验 | 93.73 最新批次；task 957 95.91 | small motion | 10.822s avg | 12012 MiB |
| 2 | Wan2.2 TI2V-5B matched aspect | 3/5 | task 574 人工稳定，未记录统一 proxy | 未记录统一 proxy | short/no-reference | 30.862s task 574 | 11861 MiB |
| 3 | SD1.5 + IP-Adapter static | 4/5 静态阶段 | 100 static proxy | 97.17 static proxy | N/A | 未记录 | 约 4742 MiB |
| 4 | LTX v3 5s complex | 2/5 | 91.81 avg of tasks 743–746 | ref avg 93.85 | complex not safe | 20.462s avg | 11931 MiB |
| - | Hunyuan / Wan Animate / HunyuanCustom | 未知 | 未测试 | 未测试 | 未测试 | 未知 | 未知 |

- Best General：LTX v3 3 秒受监督 Draft。
- Best Face：视频为 LTX v3 3 秒；静态身份锚点为 SD1.5 + IP-Adapter Plus。
- Best Identity：IP-Adapter 静态锚点 + LTX guide 的组合策略。
- Best Motion：没有完成可证明的统一冠军；无参考短动作可先用 Wan2.2，复杂动作需 Driving/Pose。
- Best Preview：LTX v3 320×416、73 帧。
- Best Current-GPU：SD1.5/IP-Adapter 静态 + LTX v3 I2V。

## 十五、当前有效 Model Router

当前没有名为 Model Router 的独立模块；以下是已经写入生产入口/任务参数的有效分流，不把计划规则当作已运行规则：

- 有角色参考图：12_ltx_face_stable_v3，320×416、73 帧、guide 0.45、small motion。
- 无角色参考图：05_wan22_ti2v_5b，先 49 帧，输入画幅匹配输出。
- 静态人物且 IP-Adapter/CLIP Vision 存在：13_sd15_ipadapter_face_v1；否则使用 reference/img2img 工作流。
- Preview：LTX v3 3 秒 Draft。
- Medium/Complex 动作：当前不会自动切换到 Driving/Pose；仍是 LTX/Wan 小动作路线并要求人工，复杂动作 Router 未实施。
- 无人物复杂场景：没有完成统一的正式模型 Router 验收，不能宣称已自动选择最优模型。

## 十六、失败定向重做

| 失败类型 | 当前实际策略 | 自动还是人工 |
|---|---|---|
| FACE_BAD | 保持参考图画幅匹配，换 seed，转 LTX v3，320×416、73 帧、small motion | Face QA 可自动排队回炉；最终人工 |
| IDENTITY_DRIFT | 单脸 Master；静态先 IP-Adapter，再进入 LTX guide | 可自动改变 seed/guide；身份结论人工 |
| BODY_BAD | 降低动作幅度或拆成多个短 Shot；需要真实 Pose/Driving 才能增强 | 目前仅人工建议 |
| HAND_BAD | 避免手经过脸部；提供 Pose/Depth/物体接触控制后重做 | 目前仅人工建议 |
| MOTION_BAD | 换 seed、减少动作、锁定镜头、缩短到 3 秒 | 可做参数回炉；动作语义人工 |
| TEMPORAL_BAD | 换 seed、guide 0.45、73 帧、关闭强镜头运动 | Face/Temporal proxy 可触发；最终人工 |

## 十七、真实生产项目验收

### Project A：TEST-20260809-A 移动坟墓：最后列车

- Project ID：14
- Episode：EP01 断电夜车
- Shot 数量：EP01 为 8；项目总计 40
- 首次生成成功数：项目报告记录 42 个参考图、254 个 Keyframe 成功、10 个 ImageToVideo 成功；未按 EP01 每个字段单独保存，不能进一步拆成虚构的每 Shot 数字。
- 重做次数：A EP01 Shot 01 真实 QA 回炉 1 次，改变 seed；回炉后仍 Rejected。
- 最终通过数：技术链路有通过记录；Episode 内容 QA 0 个可发布通过。
- 最终失败数：Episode 内容 QA 1 个 Rejected。
- 总生成时间：项目累计约 27.1 分钟；峰值 11718 MiB。
- 最终视频：C:\install\AI\Data\Output\TEST-A_EP01_FINAL_V4.mp4。FFprobe 为 1920×1080、30 FPS、60 秒、H.264 + AAC；技术通过不代表内容通过。

### Project B：TEST-20260809-B 长安夜雨录

- Project ID：15
- Episode：EP01–EP05，5 集
- Shot 数量：40
- 首次生成成功数：项目有 5 集关键帧批量记录；精确按 Shot 首次/重做/最终通过字段未在本轮数据库中形成可审计分栏，写为未单独记录。
- 重做次数：未单独记录。
- 最终通过数：0 个通过内容 QA 的正式 Episode。
- 最终失败数：未形成正式 Episode；不能把未生成写成失败。
- 总生成时间：约 6.5 分钟；峰值 8665 MiB。
- 最终视频：无通过内容 QA 的正式视频。

### Project C：TEST-20260809-C 凌晨 3:17

- Project ID：16
- Episode：EP01–EP05，5 集
- Shot 数量：40
- 首次生成成功数：项目有 5 集关键帧批量记录；精确按 Shot 字段未单独记录。
- 重做次数：未单独记录。
- 最终通过数：0 个通过内容 QA 的正式 Episode。
- 最终失败数：未形成正式 Episode；不能把未生成写成失败。
- 总生成时间：约 9.5 分钟；峰值 3351 MiB。
- 最终视频：无通过内容 QA 的正式视频。

### 本轮最新生产样本（补充，不替代 A/B/C）

Project 18 Midnight_Signal，Episode 28 EP01_Midnight_Signal_60s：

- 20 个 Keyframe 任务 966–985 成功，20 个 LTX v3 I2V 任务 986–1005 成功。
- 20 个 I2V 输出全部存在，平均脸部代理 93.60，3 个有伪影代理告警，全部需要人工审核。
- SRT 任务 1022 成功，Episode preview 任务 1023 成功。
- 16 个 Audio 任务 1006–1021 的历史失败保留；数据库检查确认其中中文文本在任务创建时已经变成问号，不能只归因于语音引擎。
- 本轮修复 `MediaProductionServices.cs`：UTF-8 文本损坏保护、无效 WAV/缓存检测和重新生成；重新创建任务 1027–1034，8/8 Succeeded，均为 pcm_s16le/22050Hz/mono/非零时长。
- 预览任务 1043 成功：C:\install\AI\Data\Artifacts\project-18\episodepreview\task-1043\v0001\v0001_PREVIEW_Midnight_Signal_EP01_60s_TTS_FIX_V2_3c6cd8de23e3.mp4；FFprobe 为 60 秒、1080×1404、H.264、AAC 22050Hz mono；volumedetect mean -29.2 dB、max -0.6 dB。
- 该预览已通过技术音频回归，但 20 个镜头仍没有逐镜内容放行，不能写成最终发布 Master。

## 十八、完整链路验收

| 项目 | 结果 | 实际边界 |
|---|---|---|
| Project | PASS | A/B/C/Project18 均有真实项目记录 |
| Episode | PASS | Episode 记录和预览链路可用；内容通过仍需人工 |
| Character | PASS | 角色和参考资产存在 |
| Reference Pack | PASS（REF1/REF3/REF5 静态）/NEED REVIEW（多参考 I2V） | 单图与三/五图静态链路均有真实 3-seed 输出；REF3/REF5 尚未接入 I2V |
| Shot | PASS | Shot 与任务记录可追溯 |
| Shot Analyzer | PASS | 本地规则/分析入口存在；语义质量仍需人工 |
| Model Router | FAIL/部分 | 嵌入式有参考/无参考分流存在，复杂动作 Router 未实施 |
| Image Generation | PASS | SD1.5/IP-Adapter 真实任务成功 |
| Video Generation | PASS（受限） | LTX/Wan 低分辨率真实任务成功 |
| Driving/Pose | PARTIAL/FAIL | Pose v2 24/24 技术成功，但 B04/B05/B06/B08 动作语义门未通过；Wan Animate 目标部署被本地资产/显存阻塞 |
| QA | PASS（技术/代理） | 内容 QA 仍 NeedReview/人工 |
| Directed Retry | PASS | QA 回炉改变 seed 和参数，有真实记录 |
| TTS | PASS（技术修复）/NEED REVIEW | 8 个中文 WAV 重新生成成功并进入 task 1043 预览；历史 1006–1021 保留，完整 Episode 内容/音画同步仍需人工 |
| SRT | PASS | Project 18 task 1022 成功 |
| FFmpeg | PASS | FFprobe/渲染链路可用 |
| Episode Render | PASS（preview） | Task 1043 真实生成含修复后中文音频的 60 秒预览；Task 1023 是旧无有效音频预览 |
| Master Render | PASS（技术）/FAIL（内容发布） | A EP01 技术 Master 可读，但内容 QA Rejected |

## 十九、Build 与自动测试

- dotnet build server\VideoStudio.Server.csproj --no-restore --nologo：Passed；0 warnings，0 errors。
- 本轮新增代码改动：`server/MediaProductionServices.cs`（中文 TTS 编码/音频有效性保护）和 `server/FfmpegService.cs`（原子输出临时文件保留最终扩展名，修复 Episode concat 格式探测）；两项均已编译并通过真实任务回归。
- npm run build（工作目录 web）：Passed；Vite 1589 modules transformed；主 JS 1,101.82 kB，存在 chunk >500 kB 警告和第三方 PURE 注释警告。
- git diff --check：Passed；仅有 Git 的 LF/CRLF 提示，不是 diff 错误。
- test_phase0_static_evidence.ps1：Passed；loopback、资产边界、幂等、租约、schema opt-in、GPU 单槽和迁移文件存在检查通过；迁移文件存在不等于迁移已重新执行。
- test_text_integrity.ps1：Blocked；脚本要求本机管理员测试用户名/密码，本轮没有读取或创建新的测试凭据。
- API Tests：本轮未重新运行受保护业务 API 测试；/api/health 真实通过，业务 API 无凭据返回 401。
- Unit Tests：未执行；仓库没有独立 .NET 单元测试项目。
- Integration Tests：本轮未执行数据库迁移/恢复和多 worker 真实竞态。
- Playwright：本轮未重新运行；已有历史 episode-output E2E 记录为 3/3，但不作为本轮新验收。

## 二十、性能

| 路线 | 实际性能 |
|---|---|
| 最新 Project 18 LTX v3 | 20 个 I2V；平均 10.822 秒，最快 9.633 秒，最慢 12.708 秒 |
| 受控 LTX v3 20-run | 平均 14.595 秒，最快 12.750 秒，最慢 16.024 秒 |
| Wan2.2 task 574 | 30.862 秒，峰值 11861 MiB |
| Wan2.2 task 577 | 29.079 秒，峰值 11935 MiB |
| LTX 5 秒 stress 743–746 | 平均 20.462 秒，最快 15.862 秒，最慢 26.506 秒；峰值 11931 MiB |
| GPU Peak VRAM | 受测路线最高 12012 MiB |
| RAM Peak | 本轮没有为每个任务保存进程级 RAM peak，不能补写数字 |
| CPU Offload | ComfyUI 日志显示 offload device=cpu；没有独立关闭 offload 的 A/B 时间实验 |
| 并发 | GPU generation concurrency = 1；未修改；没有显存争抢证据 |

## 二十一、RTX 4070 12GB 瓶颈分析

### 当前能很好运行

- SD1.5 静态人物和 640×832 角色锚点。
- SD1.5 + IP-Adapter Plus 静态身份矩阵。
- LTX v3 320×416、73 帧、24 FPS、small motion。
- Wan2.2 TI2V-5B 49 帧、按参考画幅匹配的短 I2V。
- FFmpeg、SRT、技术 QA 和预览渲染。

### 可以运行但需要妥协

- Wan2.2 约 11.7–11.9 GiB 峰值，必须匹配画幅、低帧数、单 GPU 串行。
- LTX 5 秒 121 帧可以技术完成，但 11.9 GiB 附近的显存和低分辨率会放大动作/时序质量风险。
- 长视频、高分辨率、更多控制输入需要 offload、减少帧数、降低分辨率或牺牲速度/质量。

### 当前无法合理运行或未证明

- 没有实际 Hunyuan/Animate 权重，不能标为 OOM；只能标为 NOT_TESTED。
- 1920×1080 直接送进视频模型没有执行，也不符合本项目 4070 源视频策略。
- Driving/Pose 复杂控制链没有完成真实验收；瓶颈同时来自缺少控制输入和显存余量。

判断：RTX 4070 12GB 是部分瓶颈。它不是当前人脸问题的唯一主因，因为明显的 512×320 画幅错配、动作控制缺失和时序模型限制在当前结果中同样直接可见。

## 二十二、24GB 与 32GB 评估

| GPU VRAM | 能新增什么 | 主要收益 | 本轮证据边界 |
|---:|---|---|---|
| 12GB | 当前 SD1.5、IP-Adapter、LTX v3 3 秒、Wan 49 帧 | 低分辨率受监督生产 | 已实测 |
| 24GB | 更高源分辨率、更长帧数、更大控制链、更多参考/模型驻留空间 | 减少 offload，允许尝试更高质量模型与 Pose/Driving 组合 | 本轮没有 24GB 实机，属于基于 12GB 峰值的容量评估 |
| 32GB | 更大的视频模型、更长镜头、多模型/控制模块同时驻留 | 更大的质量和控制空间，适合复杂动作与批量生产 | 本轮没有 32GB 实机，不能承诺具体模型或速度 |

换显卡首先带来的不是“同一设置必然更快”。实测速度还受 steps、帧数、模型和磁盘影响；24/32GB 的主要价值是启用更高分辨率、更长视频、更多控制模块和更少 offload，从而可能提高质量和控制上限。建议：当前路线 OPTIONAL；若目标是复杂动作、长镜头和 24GB 级模型，建议 24GB 起步，32GB 用于更大模型/更高并发余量。

## 二十三、核心问题结论

### Q1：为什么高质量人物图片进入视频后脸会变差？

本机结果显示不是单一原因。Wan task 575 使用竖幅参考却输出 512×320，首帧直接裁掉双眼；这类问题与画幅和 latent 构图不匹配直接相关。即使画幅匹配，LTX/Wan 仍需在低分辨率 latent 中保持眼睛、嘴、发际线和服装的时序一致，5 秒动作会累积漂移。静态 IP-Adapter 能把静态 reference similarity proxy 提升到 97.17，但不能自动约束后续每帧的动作和结构。最新 20-shot LTX 批次的平均 face proxy 93.60、3/20 有伪影告警，说明“图片好”不等于“视频每帧都好”。

### Q2：人物动作变形主要由什么造成？

- 模型：视频模型的时序先验在长时段和复杂动作上会重建脸、手和身体。
- Pose：没有真实 pose landmark 输入时，文字不能精确指定每个关节轨迹。
- Driving：本机没有完成 Driving Video/Animate 链，不能稳定复制走动、转身和接触动作。
- Reference：当前单脸参考主要锁脸，不锁身体姿态和物体关系；REF3/REF5 多图注入未完成。
- 分辨率：320×416 源视频对脸和手的可用像素有限；上采样到 1080P 不会恢复丢失结构。
- 硬件：12GB 迫使低分辨率、短帧和 offload，但不是唯一原因。

真实证据是 5 秒任务 745/746 的脸部代理 88.58/91.25、手部穿脸和结构伪影，以及 Wan 575/577 的画幅/时序差异。

### Q3：换模型能解决多少？

能解决一部分。主要旧版 4-case Baseline 平均 92.14；最新 LTX v3 20-shot 平均 93.60，提升 1.46 个百分点；受控 3 秒 20-run 可到 95.15。静态 IP-Adapter 相对同类静态基线 reference similarity proxy 95.88→97.17，提升 1.29 个百分点。不能解决的部分是 5 秒复杂动作：745/746 仍被拒绝。因此换模型需要和画幅、参考、时长、seed、Pose/Driving 控制一起看。

### Q4：RTX 4070 12GB 是不是当前主要瓶颈？

部分是。LTX/Wan 任务峰值 10728–12012 MiB，12GB 已经限制了分辨率、帧数、控制模块和 offload 余量；但当前最直接的失败还包括画幅错配、复杂动作无控制和时序漂移。换卡能扩大模型/分辨率/控制上限，不能自动修复错误 Prompt、错误 Reference 或动作语义。

### Q5：距离 Seedance 级效果最大的三个技术差距是什么？

1. 长时序身份、身体和场景连续控制：当前只能稳定支持单脸、3 秒、small motion，不能证明多 Shot 长镜头。
2. 可复现的动作控制链：Driving/Pose/Retarget/Depth 与手物接触没有完成真实端到端验收。
3. 更高分辨率与更强的自动内容 QA：当前 320×416 源视频、CPU face proxy 和人工审核不能替代高分辨率时空细节与动作语义判断。

## 二十四、失败与未完成项

- HunyuanVideo-1.5、Wan2.2 Animate：核心节点存在，但模型/工作流缺失；已完成部署前置核查，目标运行 BLOCKED，不声称 OOM。
- Wan 512×320 竖幅参考：task 575 FACE_BAD，保留失败样本。
- Wan 49 帧归一化样本：task 577 中后段时序彩色伪影。
- LTX 5 秒复杂动作：tasks 745、746 被拒绝；任务 743、744 也只允许人工复核。
- 最新 Project 18 20-shot：3 个伪影 proxy 告警；没有人工逐镜通过结果。
- Driving/Pose：B04/B05/B06/B08 已完成三 seed Pose v2 技术 Benchmark（24/24），但动作语义未通过；尚无 Wan Animate Driving Video 验收。
- REF3/REF5：静态三/五参考一致性 Benchmark 已完成 3+3 个 seed；多 Reference I2V 对照仍未完成。
- Pose/Body 自动 QA：仍未实现；本轮用 contact sheet 和人工视觉结论记录失败边界。
- 中文 TTS：历史 Audio tasks 1006–1021 的失败保留；修复后任务 1027–1034 8/8 成功，并进入 task 1043 预览；Project A 旧旁白需要重新生成，不能用旧无效 WAV 当作修复后通过。
- 完整音频 Episode 的逐镜内容/音画同步放行、浏览器刷新恢复、多 worker 竞态、备份恢复和正式网络发布：未完成。
- test_text_integrity.ps1：因缺少显式管理员测试凭据而 Blocked，本轮没有创建或打印凭据。
- 数据库 006 迁移文件存在但未应用；本轮没有擅自执行迁移。

## 二十五、样本与证据目录

- 报告：C:\install\AI\VideoStudio\docs\AI视频生成优化执行结果.md
- Benchmark JSON：C:\install\AI\Data\QA\benchmark-results.json
- Baseline 视频：C:\install\AI\Data\Videos\task_611_task_611_00001_.mp4 至 task_618_task_618_00001_.mp4
- 当前最佳 3 秒视频：C:\install\AI\Data\Videos\task_957_task_957_00001_.mp4
- 当前最佳抽帧：C:\install\AI\Data\QA\quality-v3-i2v-20260811_234239\task_957\frame_0.png、frame_36.png、frame_72.png
- 当前最新 20-shot 视频目录：C:\install\AI\Data\Videos\task_986_task_986_00001_.mp4 至 task_1005_task_1005_00001_.mp4
- 最新生产批次 QA/任务记录：C:\install\AI\VideoStudio\logs\server.log，以及数据库 generation_tasks/generation_results 的 986–1005 记录
- 失败样本：C:\install\AI\Data\Videos\task_575_task_575_00001_.mp4、task_577_task_577_00001_.mp4、task_745_task_745_00001_.mp4、task_746_task_746_00001_.mp4
- LTX v3 实验日志：C:\install\AI\VideoStudio\logs\quality_v3_i2v_regression_20260811_182536.json、quality_v3_i2v_regression_20260811_234239.json
- Identity baseline：C:\install\AI\VideoStudio\logs\identity_consistency_matrix_20260811_232134_final.json
- Identity IP-Adapter：C:\install\AI\VideoStudio\logs\identity_consistency_matrix_20260811_233807_final.json
- Reference Pack：C:\install\AI\Data\Characters\15\standard，以及 C:\install\AI\Data\Characters\15\ref_20260811_105155_701f4554.png
- IP-Adapter / ControlNet workflow：C:\install\AI\Workflows\13_sd15_ipadapter_face_v1_api.json、14_sd15_controlnet_openpose_v1_api.json、15_sd15_ipadapter_ref3_api.json、16_sd15_ipadapter_ref5_api.json、17_sd15_ipadapter_openpose_v2_api.json
- 直连 ComfyUI Benchmark 汇总：C:\install\AI\Data\QA\benchmarks\action_identity_20260814\comfy-benchmark-results.json
- REF contact sheets：C:\install\AI\Data\QA\benchmarks\action_identity_20260814\contact_sheets\REF1.jpg、REF3.jpg、REF5.jpg
- Pose v2 24-run 汇总：C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_v2\pose-v2-results.json
- Pose v2 contact sheet：C:\install\AI\Data\QA\benchmarks\action_identity_20260814\pose_v2\contact_sheets\POSE_KEYFRAMES_V2_12.jpg
- 模型部署阻塞证据：C:\install\AI\Data\QA\model-deployment-20260814.json
- Project A 技术 Master：C:\install\AI\Data\Output\TEST-A_EP01_FINAL_V4.mp4
- Project 18 旧预览：C:\install\AI\Data\Output\PREVIEW_Midnight_Signal_EP01_60s.mp4；TTS 修复预览：C:\install\AI\Data\Artifacts\project-18\episodepreview\task-1043\v0001\v0001_PREVIEW_Midnight_Signal_EP01_60s_TTS_FIX_V2_3c6cd8de23e3.mp4
- Project 18 字幕：C:\install\AI\Data\Output\Midnight_Signal_EP01_60s.srt
- Driving Video：Wan Animate 目标权重/工作流缺失；本轮提供的是 B08 Pose v2 控制链输出，路径在 `...\pose_v2\comfy_outputs\B08`，不能冒充 Wan Animate。
- Master：已有技术可读 Master，但当前内容 QA 未通过；不把它标成可发布 Master。

## 二十六、本轮补充执行结果（2026-08-14 夜间至 2026-08-15 00:10）

### 中文 TTS

- 根因：历史任务 1006–1021 的 `parameters.Text` 在入库前已出现大量 `?`，所以单纯换 Windows voice 不能解决；Episode 28 的 Shot narration 原文仍是正确中文。
- 修复：`VideoStudio/server/MediaProductionServices.cs` 增加 UTF-8 损坏保护、无效 WAV/缓存检测；`VideoStudio/server/FfmpegService.cs` 修复原子输出临时文件的扩展名，避免 FFmpeg concat 无法探测输出格式。
- 实证：1027–1034 共 8/8 Succeeded；PCM s16le、22050 Hz、mono、时长非零。Task 1043 的 60 秒预览可被 FFprobe 解析，音频 mean -29.2 dB、max -0.6 dB。`config/local.env` 仍为 `AI_VIDEO_STUDIO_WORKER_ENABLED=0`；本轮只用临时环境覆盖启动发布进程做回归，没有把本地配置伪装成已启用。

### REF1 / REF3 / REF5

- REF1/REF3/REF5 通过 ComfyUI REST 实际运行 9 个静态样本，3/3/3 seeds 全部成功。
- REF3 使用 3 张输入、ImageBatch 链和 IPAdapterAdvanced average；REF5 使用 5 张输入，最后一张是确定性裁剪变体。contact sheet 已抽检，身份总体稳定；该结论限定为静态身份锚点，不等于多参考 I2V 已通过。
- 证据：`C:\install\AI\Data\QA\benchmarks\action_identity_20260814\comfy-benchmark-results.json` 和同目录 contact sheets。

### B04 / B05 / B06 / B08 Driving/Pose

- 第一版 17 个直连 ComfyUI 样本全部技术完成，但近景 face latent 没有真实承载身体动作，已降级为历史技术探针。
- 第二版使用 `17_sd15_ipadapter_openpose_v2_api.json`（IP-Adapter FACE + OpenPose ControlNet + EmptyLatent）实际跑 4 个 case × 3 seed ×（关键帧 + LTX I2V），共 24/24 技术成功；每段为 320×416、81 帧 WEBP。
- 视觉结论：B04 走路 FAIL；B05 仅一个 seed 部分出现杯子/手，整体 PARTIAL/FAIL；B06 转身/坐下 FAIL；B08 车辆/方向盘 FAIL。Benchmark 已完成并留下了真实失败边界，不能宣称动作质量通过。

### Wan2.2 Animate / HunyuanVideo-1.5

- ComfyUI 核心节点存在，但模型目录匹配文件数为 0，Workflows 目录匹配目标 workflow 数为 0；因此没有可诚实提交的目标推理。
- 已有 LTX/Wan TI2V 路线在 12282 MiB 卡上测得最高约 12012 MiB，仅剩约 270 MiB。结论是“本地资产缺失 + 12GB 没有安全余量”的部署阻塞，不是伪造 OOM；完整记录见 `C:\install\AI\Data\QA\model-deployment-20260814.json`。

========================================
AI VIDEO STUDIO FINAL VERDICT
========================================

Status:
CONDITIONAL GO

Recommended Production Engine:
LTX 2B FP8 + 12_ltx_face_stable_v3，单脸参考、3 秒 Draft、人工复核

Recommended Preview Engine:
LTX 2B FP8 + 12_ltx_face_stable_v3，320×416、73 帧、24 FPS

Recommended Motion Engine:
当前无复杂动作合格冠军；无参考短动作可试 Wan2.2 TI2V-5B，Pose v2 已完成但语义未通过，复杂动作需真实 Driving/Pose/Retarget

Recommended Identity Strategy:
SD1.5 + IP-Adapter Plus 先生成静态身份锚点，再用 LTX guide 做短 I2V

Current Best Workflow:
13_sd15_ipadapter_face_v1_api.json → 人工选单脸锚点 → 12_ltx_face_stable_v3_api.json

Baseline Average Score:
92.14（旧版 LTX primary 4-case）

Final Average Score:
93.60（2026-08-13 Project 18 最新 20-shot；受控实验最佳 95.15）

Face Improvement:
+1.46 分，约 +1.59%（主要 Baseline 对最新生产批次）

Identity Improvement:
静态 reference similarity proxy +1.29 分，95.88 → 97.17

Body/Motion Improvement:
3 秒 small motion 更稳；B04/B05/B06/B08 Pose v2 24/24 技术成功但动作语义未通过

Baseline Hard Reject Rate:
50%（2/4 primary Baseline）

Final Hard Reject Rate:
0% 自动 face reject（0/20），但 3/20 伪影 proxy 告警且 20/20 需人工审核

RTX 4070 12GB Status:
PARTIAL BOTTLENECK

GPU Upgrade Recommended:
TARGET MODELS BLOCKED；24GB+ 是下一轮 Wan Animate/Hunyuan/复杂动作的最低实际验证方向

Recommended VRAM:
24GB

Top 3 Remaining Problems:
1. B04/B05/B06/B08 的动作语义、身体、手部和手物接触仍未通过；当前 Pose v2 只是技术失败边界
2. REF3/REF5 还未接入多参考 I2V；Wan Animate/HunyuanVideo-1.5 仍缺权重/工作流且 12GB 无安全余量
3. 中文 TTS 已修复并进入预览，但完整 Episode 内容 QA、音画同步和人工发布验收未闭环

Top 3 Next Actions:
1. 在 24GB+ GPU 上取得真实 Driving Video/Retarget 输入，再复跑 B04/B05/B06/B08；当前 12GB 结果保留为阻塞基线
2. 把已验证的 REF3/REF5 pack 接入 I2V，完成跨 Shot 的 3-seed 人工 identity/temporal 评分
3. 对 task 1043 的 20 个镜头完成内容、对白、音画同步和 Master 人工放行

Production Readiness:
CONDITIONAL GO（本机受监督 Draft）；复杂长镜头和对外发布 NO-GO
========================================

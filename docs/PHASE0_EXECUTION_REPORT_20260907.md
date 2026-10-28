# 阶段 0 执行报告与 Windows 原子发布修复（2026-09-07）

## 结论

本轮完成了本机基线复核、历史代表片段抽帧检查、一个已定位的 Windows 文件句柄缺陷修复、后端/前端/静态回归、原子下载回归和隔离发布冒烟。当前结论是：

- 本机受监督研发：`CONDITIONAL GO`。
- 本机技术栈：可继续使用 ComfyUI + VideoStudio 队列 + FFmpeg，GPU 重任务必须并发 1。
- 试生产、连续多集、LAN/公网和自动发布：`NO-GO`。
- 现有《第三轨录音》代表片：技术文件可播放，但内容审核失败，不能作为可发布样片。
- 真实业务生产、任务/素材对账和浏览器受保护后台回归仍受本地认证门禁阻塞；本轮没有绕过登录、伪造业务状态或写入业务表。

## 现场基线

| 项目 | 实际结果 |
| --- | --- |
| CPU | Intel Core i5-13600KF，14 核 / 20 逻辑处理器 |
| 内存 | 34,163,720,192 bytes，约 31.8 GiB |
| GPU | NVIDIA GeForce RTX 4070，12,282 MiB；检查时约 1,300 MiB 已用、10,711 MiB 可用 |
| 磁盘 | C: NTFS 剩余约 159.2 GB；E: NTFS 剩余约 277.99 GiB；系统识别为 NVMe SSD |
| 服务 | VideoStudio `127.0.0.1:18080`、ComfyUI `127.0.0.1:8188`、MySQL `*:3306` |
| 运行版本 | VideoStudio `/api/health` 200；ComfyUI 0.31.0；PyTorch 2.11.0+cu130；FFmpeg 可用 |
| 认证 | `/api/auth/status`：configured=true、authenticated=false、setupAllowed=false |
| Git | `main`，HEAD `d6ec38d`；151 个 dirty entries（34 tracked modified、117 untracked），未 reset/clean/commit/push |
| 资产规模 | 38 个工作流、129 个模型文件约 61,037,290,190 bytes、104 个历史 mp4 输出 |

## 运行与权限事实

`/api/health` 报告数据库在线、ComfyUI 在线、RTX 4070 和 FFmpeg 可用；`/api/projects`、`/api/workflows`、`/api/models`、`/api/tasks` 在未认证状态均返回 401。故当前无法在不取得用户本地登录的前提下，对真实 Project/Episode/Shot 创建、队列入账、输出对账和业务数据库状态作通过性声明。

已在隔离端口 `18085` 对当前源码 Release publish 做过一次只读式启动冒烟：health 200、数据库在线、ComfyUI 在线、GPU/FFmpeg 可见；随后停止临时进程，未替换现有 `18080` 服务。

## 历史代表片内容检查

检查对象：`Data/Output/ThirdRailRecording_20260819` 的任务清单、质量报告、contact sheet 和首/中/尾帧。技术文件为 37 秒、1920×1080、30 FPS、H.264/AAC，字幕文件和任务清单存在；但质量报告明确记录官方资产发布任务 1068～1083 失败，且内容审核失败。

抽帧实际可见：多个镜头出现明显的洋红/绿色/青色几何与颜色跳变；多个人物镜头只是近似同一正面肖像，未完成所要求的复杂动作；S06/S10 出现额外人物样阴影或空间/几何变化；中后段对白画面与空窗画面连续性不足。因此该片是失败证据，不是新样片，也不允许标记为可发布。

## 本轮修复

### P0：ComfyUI 输出下载与资产发布的 Windows 句柄边界

修复 `server/ComfyUiClient.cs`：响应流和目标文件流在 `File.Move` 前明确结束作用域，并使用 `ResponseHeadersRead`、临时文件、Flush 后原子移动和失败清理。

修复 `server/AssetPathPolicy.cs`：上传临时文件的 SHA-256 读取句柄在原子移动前明确释放。

这修复的是与历史报告“文件被其他进程占用”一致的确定性边界；不等于历史业务任务已重跑，也不等于内容质量通过。

## 真实验证结果

### Passed

- 后端 Release build：0 warning / 0 error。
- 前端 `npm run build`：通过；保留既有大 bundle 和第三方注释提示。
- `test_phase0_static_evidence.ps1`：通过。
- `test_p0_boundary_static.ps1`：通过。
- `test_asset_path_policy.ps1`：通过，3,146 个 Data 文件、7 个恶意候选。
- `test_idempotency_fencing.ps1`、`test_queue_lease_fencing.ps1`：通过。
- `test_external_process_boundary.ps1`：通过，包含下载和上传句柄边界检查。
- `VideoStudio.QualityHarness --self-test`：通过。
- `VideoStudio.QualityHarness --atomic-download`：通过，真实 `ComfyUiClient.DownloadOutputsAsync` 使用假 HTTP 响应验证临时文件、字节一致性和无残留 `.part-*`。
- 隔离 Release 服务 `18085/api/health`：通过。

### Failed

- 《第三轨录音》内容审核：失败。具体失败证据在 `QA_第三轨录音_质量报告.md`、`contact_sheet_第三轨录音.png` 和抽帧目录。
- 现有历史样片不能证明身份跨镜头、复杂动作、手物接触、连续光影或发布资格。

### Blocked

- 受保护业务接口真实队列生产、任务/输出对账、Episode 级恢复回归：需要用户在本地后台完成登录。
- 浏览器业务 E2E：6 个用例均在登录助手处停止，缺少 `AI_VIDEO_STUDIO_TEST_USERNAME` 和 `AI_VIDEO_STUDIO_TEST_PASSWORD`；没有读取、打印或猜测凭据。
- 人工内容审核：当前没有新的合格样片可交付审片。
- 正式音频 Episode、发布包和三条不同剧情复用验证：前置内容路线尚未通过。

### Unverified

- 模型权重/节点的预期商业许可和完整来源：模型目录没有统一许可清单，未据此作许可通过声明。
- 12GB 显存下新候选模型的真实加载、采样、动作控制和内容质量：阶段 1 尚未开始批量候选下载或整集生成。
- 双 Worker/GPU 抢占、重启恢复、备份恢复、外部 LLM 和真实音频响度/移动端试听。

## 当前可采用的制作边界

目前可保留的保守路线是：参考图/身份锚定 → 人工关键帧检查 → LTX v3 小画幅、短时长、锁定镜头 Draft；Wan2.2 作为场景/画面路线候选，必须按实际动作和显存结果单独放行。复杂转头、走路、坐下、开门、拿杯子、遮挡后露脸和对白口型不能因为工作流能加载就自动放行。

任务级 GPU 重操作保持并发 1；每个镜头最多两次与失败原因相关的重试；原片、增强版、参数、seed、模型/工作流版本和人工审核结果必须共同归档。

## 官方候选初筛（只读，不代表已安装或已通过）

- LTX-Video 官方仓库为 Apache-2.0，但当前官方 LTX-2.5 路线公开说明需要约 66 GiB 模型文件，包含 22B BF16 组件；官方还提示 Windows 会跳过 Linux/CUDA 专用 `natten` 后端，并可能需要 FP8/CPU 或磁盘 offload。对本机 12GB 显存和现有磁盘余量，这不是首轮下载候选；LTX-2.x 的社区许可和商业实体条款也必须单独审查。见官方仓库：[LTX-Video](https://github.com/Lightricks/LTX-Video)、[LTX-2](https://github.com/Lightricks/LTX-2)。
- Wan2.2 官方仓库存在，版本为 2.2.0；其 Python 声明要求 Python >=3.10，并包含 `flash_attn` 等依赖。仓库软件许可文件是 Apache-2.0 形式，但具体权重和模型卡仍需逐项确认；Windows、现有 ComfyUI 节点、12GB 显存和动作质量尚未实测，暂不宣布优于现有 Wan2.2 TI2V-5B。见官方 [Wan2.2 仓库](https://github.com/Wan-Video/Wan2.2)。
- Tencent HunyuanVideo 官方仓库使用有地域限制的社区许可，明确排除欧盟、英国和韩国，并附带使用限制与分发 Notice 要求；在项目目标地域和许可边界未确认、且本机 12GB 方案未实测前，不进入默认生产路线。见官方 [HunyuanVideo 许可](https://github.com/Tencent-Hunyuan/HunyuanVideo/blob/main/LICENSE.txt)。

因此本轮没有下载新模型、没有复制模型缓存、没有改变系统环境。阶段 1 候选排序仍需以本机短片段加载/采样/解码、峰值显存/内存、实际身份/动作内容和逐项权重许可记录为准。

## 证据路径

- 历史样片：`Data/Output/ThirdRailRecording_20260819/ThirdRailRecording_final.mp4`
- 历史审核：`Data/Output/ThirdRailRecording_20260819/QA_第三轨录音_质量报告.md`
- 历史任务：`Data/Output/ThirdRailRecording_20260819/task_manifest.json`
- 历史抽帧：`Data/Output/ThirdRailRecording_20260819/frames/`
- 历史联系表：`Data/Output/ThirdRailRecording_20260819/contact_sheet_第三轨录音.png`
- 原子回归：`tests/VideoStudio.QualityHarness/Program.cs`、`scripts/test_external_process_boundary.ps1`
- 本报告：`docs/PHASE0_EXECUTION_REPORT_20260907.md`

本阶段没有生成新的剧情样片，没有自动上传，没有公开发布，也没有把失败结果改写为通过。

## 2026-09-08 继续执行增量

- 发现并修复 `QaEndpoints.cs` 的 P0 门禁漏洞：自动 QA `Rejected` 时，人工 `Passed` 现在必须显式提交 `OverrideHardFailure=true` 和非空复核说明；备注不能单独绕过。
- `dotnet build server/VideoStudio.Server.csproj --no-restore --nologo`：Passed，0 warning / 0 error。
- `scripts/test_p0_boundary_static.ps1`：Passed，新增 Override 门禁断言。
- 建立 `docs/PHASE1_FIXED_BENCHMARK_20260908.json` 与 `.md`，覆盖 12 个剧情无关能力用例；当前 `DefinedNotRun`，不虚构GPU或内容结果。
- 认证状态仍为未登录；本轮未输入凭据、未写业务表、未启动基准GPU任务、未下载模型、未生成或发布视频。
- 前端人工审核弹窗已同步提交 `overrideHardFailure`；自动 QA Rejected 时强制输入人工 Override 说明。`npm run build` Passed，保留既有 bundle 体积提示；真实浏览器业务回归仍因认证阻塞。
- 继续复核发现同类 Episode 级门禁缺陷并已修复：自动 Episode QA Rejected 时，Approved 也必须显式 Override 并填写说明；后端 P0 静态回归、后端构建和前端构建再次 Passed。
- 再次运行 `npm run test:e2e`：6/6 用例均在登录助手因缺少 `AI_VIDEO_STUDIO_TEST_USERNAME` / `AI_VIDEO_STUDIO_TEST_PASSWORD` 停止；这是认证 `Blocked`，不是业务断言通过或失败。

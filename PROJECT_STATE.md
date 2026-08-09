# AI Video Studio 当前项目状态

> 状态来源：实际源代码、运行中的本地服务、MySQL、ComfyUI、FFmpeg/FFprobe、真实生成任务和回归脚本。密码、Token 和 API Key 永不写入本文件。

## 1. 当前阶段

- 项目：`AI Video Studio`
- 阶段：本地 AI 短剧生产链 + Video QA 发布闸门 + 长期维护基线
- 阶段状态：`Passed`（已验收核心生产链；长期增强仍按 `NEXT_STAGE.md` 排队）
- 对话上下文：已迁移到 `docs\CONVERSATION_CONTEXT.md`；敏感凭据未迁移。
- 最后核验日期：2026-08-09
- 项目根目录：`C:\install\AI\VideoStudio`
- 服务地址：`http://127.0.0.1:18080`
- ComfyUI：`http://127.0.0.1:8188`
- Git：已初始化本地仓库，当前分支 `main`，无 remote；长期基线提交为 `f5a98b9`（后续文档提交以 `git log -1 --oneline` 为准）。

## 2. 硬件与运行时基线

| 项目 | 当前实测/配置 |
| --- | --- |
| 系统 | Windows 11 64 位 |
| CPU | Intel Core i5-13600KF |
| 内存 | 32 GB（ComfyUI `/system_stats` 返回约 34.16 GB 总内存） |
| GPU | NVIDIA GeForce RTX 4070，12 GB |
| GPU 分配器 | `cuda:0 NVIDIA GeForce RTX 4070 : cudaMallocAsync` |
| ComfyUI Python | `C:\install\Python\python.exe`，`embedded_python=false` |
| ComfyUI Python 版本 | 3.13.2（健康检查返回值） |
| PyTorch | `2.11.0+cu130` |
| ComfyUI 版本字段 | `/system_stats` 的 `comfyui_version=0.31.0`；健康探针另返回 ComfyUI 服务版本字段 3.13.2，后续以接口原始字段为准 |
| FFmpeg | `C:\install\FFmpeg\bin\ffmpeg.exe` |
| FFprobe | `C:\install\FFmpeg\bin\ffprobe.exe` |
| C: 可用空间 | 最近检查约 222.66 GB |

最近一次健康检查中 GPU 总显存约 12281 MiB、空闲约 11018 MiB，利用率为 0；数据库、ComfyUI、FFmpeg 均在线。

## 3. 代码与数据现状

- 后端：`server\VideoStudio.Server.csproj`，.NET 8 Web，MySqlConnector 2.3.5。
- 前端：`web`，Vue 3 + Element Plus + Vite；发布后的静态页面由后端提供。
- 数据库：MySQL 8，`ai_video_studio`，当前 schema 34 张表；基础结构 + `002_production_pipeline.sql` + `003_video_qa.sql` 已应用。
- 当前数据库记录（最近核验）：9 个项目、7 个 Episode、14 个 Shot、2 个角色、7 个场景、15 个资产、3 个模型、0 个 LoRA、8 个工作流、3 个 QA 预设。新增的 3 个 `Production Pipeline Test` 项目和 5 个测试 Shot 是本次回归留下的可识别测试数据，没有删除既有业务记录。
- 任务状态（最近核验）：无 Running 任务，43 个 Succeeded；历史回归故意留下的失败夹具任务必须与当前产品故障区分。
- TTS：`/api/audio/voices` 可用，返回 Windows System.Speech 音色；实际音频仍按具体 Episode 需要验收。
- LLM：支持本地规则解析及已配置时的 OpenAI-compatible/DeepSeek/OpenAI 适配器；没有外部 Key 时不阻断本地规则解析。

## 4. 已验收能力

- 项目、Episode、角色、场景、Shot、资产的 CRUD 和参考图路径边界。
- 剧本保存、版本、规则/LLM 分析、角色/场景匹配、缺失资产草稿。
- Prompt 七段组合、编辑、锁定、历史和回滚。
- 工作流/模型/LoRA 扫描；当前真实 LoRA 目录为空，不能把 LoRA 能力描述为已安装。
- SD1.5 人物关键帧、LTX 2B FP8 I2V、ComfyUI 任务提交/轮询/下载/取消。
- RTX 4070 单 GPU 队列、显存门禁、暂停/恢复、取消、重试、依赖和服务重启恢复。
- FFmpeg 去闪烁/插帧/增强、SRT、Windows TTS、SFX/BGM 上传与 Episode 合成接口。
- Technical QA、Shot QA、Episode QA、人工审核、Approved 锁定、Master 导出和 QA 报告。
- 角色资产库、场景资产库、动作/电影镜头工作流入口已在生产模型中保留；严格身份控制模型尚未安装。

## 5. 最近真实验收证据

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 后端构建 | Passed | `dotnet build server\VideoStudio.Server.csproj --no-restore`，0 warnings/0 errors |
| 前端构建 | Passed | `npm run build`；仅有 Vite chunk 体积提示 |
| PowerShell 脚本语法 | Passed | scripts 目录 AST 检查 |
| 生产流水线回归 | Passed | `logs\production_pipeline_test.json`；health/文件/数据库/RuleBased 5 Shot 分析全部通过 |
| 技术/QA 夹具 | Passed | `C:\install\AI\Data\QA\TestCases\20260809_122530`，9/9 |
| 队列回归 | Passed | 暂停/恢复/取消/重试通过；缺失输入夹具按预期最终 Failed |
| QA 自动回炉 | Passed | Shot 11，第一次 73.05、第二次 85.35，使用不同 seed，最多两轮后停止 |
| 真实 3-shot Episode | Passed | Episode score 91.11，Approved/locked；技术 QA 100 |
| Master 导出 | Passed | `C:\install\AI\Data\Output\Release\Acceptance 3Shot 20260809_104019\Episode001` |

## 6. 已知限制与下一步

- 12GB 显存不适合把大型 Wan/Flux/高分辨率视频模型作为默认链路；继续使用低分辨率 I2V + FFmpeg 1080P。
- 当前 `loras=0`，没有 IP-Adapter/ControlNet/角色 LoRA 资产；人物长镜头身份一致性仍依赖参考图、Prompt、seed 和镜头设计。
- 目前没有独立的 .NET 单元测试项目；真实验收依靠 API/PowerShell/FFprobe/ComfyUI/数据库链路脚本。建立自动化测试项目是 P1/P2 任务，不得把现有脚本称为完整单测覆盖。
- 前端是单页工作台，核心 UI 已可用；后续若修改 UI，必须通过真实浏览器操作验证按钮、刷新、状态恢复和错误提示，不能只通过编译。
- 任务表中存在历史失败夹具记录（例如缺失输入测试）；它们用于证明失败处理，不等同于当前未处理的产品失败。

## 7. 当前未阻塞项

核心生产链和本地服务当前没有外部 `Blocked` 项。角色 IP-Adapter/LoRA、OpenPose/ControlNet、口型同步和多 GPU 属于后续能力，不计入本阶段已验收核心。

# AI Video Studio Codex 项目规则

本文件是 `C:\install\AI\VideoStudio` 的长期维护约束。它服务于真实本地环境，不是一次性 Demo 的说明，也不是可以用“看起来能用”替代实际验收的清单。

## 1. 权威来源与项目边界

- 实际源代码、运行中的 API、数据库现状、ComfyUI 返回值和真实测试结果优先于旧文档、聊天记录和计划文字。
- 长期项目动态档案以根目录的中文项目状态、待办、变更、需求、架构、技术决策、验收标准和开发说明文件为权威入口；PROJECT_STATE.md、NEXT_STAGE.md、CHANGELOG.md 和英文技术文档保留为兼容入口或详细证据。
- 项目根目录固定为 `C:\install\AI\VideoStudio`。不重新安装或复制已有 ComfyUI、Python、Git、FFmpeg、模型和工作流。
- AI 根目录为 `C:\install\AI`；模型为 `C:\install\AI\Models`，工作流为 `C:\install\AI\Workflows`，媒体与生产数据为 `C:\install\AI\Data`。
- 现有 ComfyUI、模型和外部媒体不属于本 Git 仓库内容。仓库只保存源码、数据库结构、脚本、工作流元数据和文档。

## 2. 实际架构

生产链路固定为：

`剧本 → Episode → 角色/场景资产 → Shot → Prompt → 关键帧 → I2V → QA/定向重试 → TTS/SRT/音频 → FFmpeg 后处理 → Episode → Master`

- `web` 是 Vue 3 + Element Plus 单页工作台，发布后由 ASP.NET Core 提供 `web/dist`。
- `server` 是 .NET 8 ASP.NET Core Minimal API，包含 MySQL 访问、ComfyUI 客户端、FFmpeg/TTS 服务、QA 和 `GenerationQueue`。
- `database` 保存结构与迁移；媒体只保存安全的磁盘路径和元数据，不把模型权重或视频二进制写进 MySQL。
- `scripts` 负责发布、初始化/迁移、备份、扫描、测试和诊断。真实任务必须经过服务队列，不能手工修改数据库状态冒充完成。

详细架构以 `docs\ARCHITECTURE.md` 为准；数据库以 `docs\DATABASE.md` 为准；ComfyUI 协议以 `docs\COMFYUI_API.md` 为准。

## 3. Windows 路径与配置

- 不修改系统环境变量，不把软件迁移到 `C:\Program Files` 或用户 AppData。
- 运行配置的密码只放在未跟踪的 `config\local.env`。`config\config.example.json` 只是结构示例，不放真实凭据。
- 不在日志、README、验收报告、Git 提交、截图或命令输出中打印 MySQL 密码、API Key、Cookie、Token 或代理凭据。
- 服务默认只监听 `127.0.0.1:18080`，ComfyUI 默认只监听 `127.0.0.1:8188`。任何改为局域网/公网监听的变更必须单独评估认证与安全边界。
- 上传文件和生成媒体必须落在 `C:\install\AI\Data` 下；读取/复制路径必须做规范化和目录边界检查。

## 4. RTX 4070 12GB 运行规则

- GPU 任务并发固定为 1，执行前检查 ComfyUI `/system_stats`；空闲显存低于 `MinFreeVramMiB=1024` 时等待。
- 关键帧优先使用 SD1.5 人物工作流；I2V 优先使用 LTX 2B FP8 工作流。默认视频源参数为 512×320、24 FPS、73/97/121 帧（约 3/4/5 秒）。
- 1080P/30 FPS 是后处理输出目标，不把 1920×1080 直接送进 12GB 视频模型。
- OOM 时按“减少帧数 → 降低分辨率 → 降低候选数/steps”的顺序降低负载；不得默认引入需要 24GB 以上显存的模型。
- 保持 FP16/FP8 和工作流已有的 attention/显存优化；CPU offload 只有在实际工作流支持且有实测收益时启用。
- 每次模型或工作流变更都要记录 GPU 型号、总/空闲显存、峰值、生成耗时和最终分辨率。

## 5. 数据库与迁移

- MySQL 是项目元数据和任务状态的权威来源；Redis 或内存状态不是本项目当前的事实来源。
- 任何数据库结构修复前先运行 `scripts\backup.ps1` 并确认备份文件存在，再通过 `database\migrations` 或现有初始化脚本迁移。
- 禁止 `DROP DATABASE`、无确认的 `DROP TABLE`、直接删除业务数据、手工把状态改成 `Passed`，或用空文件伪造媒体结果。
- 迁移后必须检查表/列、外键、默认数据和现有项目/任务是否仍可读取；数据库问题要真实修复后重新跑相关回归。

## 6. 任务、QA 与质量门

- 任务状态必须反映真实执行：ComfyUI `/prompt`、`/history`、输出文件、FFprobe 和数据库记录要能互相对应。
- 队列支持依赖、暂停、继续、取消、重试、重生和服务重启恢复。修复队列后必须回归提交、取消、重试、恢复和并发限制。
- AI 内容失败时只回炉失败 Shot；最多自动修复/重生成 2 次。每次必须改变与失败原因相关的 Prompt、seed、Reference、LoRA 或 Workflow 参数，并记录前后结果。
- 技术 QA、Shot QA、Episode QA 和人工审核必须分别可追溯。只有 `Passed` 才能作为通过；`Failed` 和 `Blocked` 不能被改名为“基本可用”。
- 自动 QA 不能可靠判断身份、动作语义、连续性和电影感时，必须标记为需要人工复核，不能虚构高分。

## 7. Session Recovery Protocol

中文项目档案必须先于历史聊天和旧状态快照阅读；动态状态以项目状态.md、待办事项.md、变更记录.md 为准，实际代码和可验证运行结果可以纠正文档。

每次新会话接管前按以下顺序执行：

1. 阅读 `AGENTS.md`、`PROJECT_STATE.md`、`NEXT_STAGE.md`、`CHANGELOG.md` 和相关验收/修复记录。
2. 检查 `git status`、最近提交、当前分支和未跟踪文件；确认没有秘密、模型和生成媒体进入仓库。
3. 检查 `config\appsettings.json`、未跟踪的 `config\local.env`、服务进程、`/api/health`、ComfyUI `/system_stats`、FFmpeg/FFprobe 和 MySQL。
4. 阅读将要修改的实际源代码、迁移和工作流，不依据旧文档猜测 API 或状态。
5. 先复现失败项，记录失败类别和证据路径，再修改最小范围。

## 8. Session Completion Protocol

每次完成重要任务时，先更新中文权威档案；只有发生对应技术或验收变化时才同步英文兼容文档。

结束一个开发阶段前必须：

1. 运行受影响模块的真实测试和必要回归；不能只看编译结果。
2. 对每个失败项定位为代码、数据库、配置、Workflow、模型、Prompt、参数、GPU、ComfyUI、FFmpeg、TTS、文件、UI 或依赖问题。
3. 修复后重新测试并保留结果；三轮相同问题仍失败时标记 `Blocked`，说明缺少的外部条件，不能宣布完成。
4. 更新 `PROJECT_STATE.md`、`NEXT_STAGE.md`、`CHANGELOG.md`、`docs\ACCEPTANCE_REPORT.md` 和 `docs\FIX_HISTORY.md`。
5. 检查 `git diff`、秘密扫描、`.gitignore` 和实际输出路径；只提交有意纳入的源代码、迁移、脚本和文档。
6. 最终报告只使用 `Passed`、`Failed`、`Blocked`；报告真实分支、提交和未解决项。没有远程仓库时不创建或猜测 remote。

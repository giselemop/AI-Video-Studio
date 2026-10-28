# 资产路径与媒体访问边界实施记录（2026-08-13）

本记录对应实施方案阶段 1 的“资产 ID、路径规范化和根目录边界”子包。目标是先把现有单机生产链的媒体输入、上传、输出和前端公开契约收敛到受控 Data 根目录，并保留可回滚的兼容读取；本包不启动 API、不执行数据库迁移、不提交或推送 Git。

## 已实施

- `server/AssetPathPolicy.cs`
  - 统一规范化 Data/Models 路径，拒绝路径穿越、相似根目录、UNC、设备路径、NUL、ADS 和驱动器相对路径。
  - 逐级检查目录和文件自身的 Windows reparse point；上传临时目录和输出目录在创建前后均检查。
  - 上传使用服务端随机文件名、扩展名/MIME/魔数校验、大小上限、FFprobe 解码校验、SHA-256 和 Data 相对路径。
  - 图片上传不再只看文件头，还必须通过 FFprobe 尺寸校验。
  - 增加受控 Models 文件解析，角色 Embedding/LoRA 引用必须是 Models 目录内已存在文件。
- `server/Program.cs`
  - `/api/media` 支持受控 `assetId` 解析，并保留 `assetPath` 作为当前本机兼容字段；两者都必须经策略解析后才能读取。
  - 项目、Episode、Shot、角色、场景、资产、任务、结果、工作流、模型、LoRA 和媒体快照的公开响应不再返回本机绝对路径；媒体统一返回 Data 相对 `assetPath` 或 `/api/media` URL。
  - Episode 合成历史、任务详情和 QA 详情对旧任务 JSON 做公开投影，去除内部绝对路径。
- `server/ProductionEndpoints.cs`、`server/QaEndpoints.cs`、`server/GenerationQueue.cs`
  - 生产候选、视频、音频、字幕、QA 回炉和 Episode 渲染的输入均先通过策略解析。
  - 生产状态与 QA 结果改为安全投影；缺失工作流诊断只保留文件名。
- `server/TaskSubmissionPreflightService.cs`、`server/QualityOptimizationServices.cs`、`server/VideoQaServices.cs`、`server/FaceQualityServices.cs`
  - 预检、QA 和脸部代理结果中的路径诊断改为相对资产名/路径，避免把本机绝对路径写入 API 响应或日志。
- `web/src/App.vue`
  - 前端兼容映射 `assetPath`/`mediaUrl` 到现有页面字段；新增媒体 URL 只接受受控接口或外部 URL，不再拼接任意本机文件路径。
- `scripts/test_asset_path_policy.ps1`
  - 新增只读负向回归入口。

## 可核验结果

- 后端：`dotnet build .\server\VideoStudio.Server.csproj --no-restore --nologo`，0 warning / 0 error。
- 前端：`npm run build`（`web`），Vite 构建通过；仅保留现有大 chunk 和第三方 PURE 注释提示。
- 路径回归：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_asset_path_policy.ps1`，实际检查 Data 下 1360 个文件，7 类恶意候选全部拒绝。
- PowerShell 兼容性：使用 UTF-8 `ParseInput` 检查 `scripts\` 下全部脚本，通过。
- `git diff --check`：通过；工作区原有未提交改动未清理、未回滚。

## 未在本包冒充通过的内容

- 当前仍兼容 `assetPath` 相对字段，尚未把所有业务 DTO 完整迁移为项目绑定的 `assetId`；`/api/media?assetId=` 已提供入口，但跨项目资产授权和 Ready 状态约束仍需后续安全子包完成。
- 未启动服务，因此未宣称 API、浏览器、MySQL、ComfyUI、FFmpeg 实时链路已在本次改动后通过；已有服务/数据库状态不能替代本次运行证据。
- 数据库显式迁移、最小权限账户、备份恢复、双 Worker 竞态、LLM 出站白名单和 LAN/公网开放仍保持后续 P0/No-Go 边界。

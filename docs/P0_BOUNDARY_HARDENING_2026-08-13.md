# P0 边界加固记录（2026-08-13）

本记录对应阶段 1 的安全边界子包和阶段 2 的任务内核小步修复。只记录代码和可复核证据，不把构建结果冒充真实生产验收。

## 本次落地

- LLM 出站：`LlmEndpointPolicy` 仅允许明确的 OpenAI/DeepSeek 主机或本机 loopback OpenAI-compatible 服务；拒绝凭据、查询参数、片段、未知主机、外部 HTTP、私有/保留/组播 DNS 地址，并限制 Prompt 和响应体大小。命名 HttpClient 禁止自动重定向并限制响应缓冲；允许/拒绝决策写入不含密钥的操作审计。
- 任务租约：进度和错误写入现在可按 `lease_owner` 绑定当前 Worker；旧 Worker 在任务被恢复并重新领取后不能覆盖新 Worker 的进度/错误。
- 任务时间源：领取、心跳和 deadline 使用 MySQL `NOW(3)` 计算，不再把 Worker 的本机时钟直接写入租约字段。
- 幂等批次：生产批次复用幂等键时会校验项目、Episode、模式和镜头数量；不同批次复用同一键返回冲突。
- 工作流边界：数据库登记的工作流在预检、队列执行和生产前检查时均须解析到受控 Workflows 根目录内的 JSON 文件。
- 外部进程和产物：FFmpeg 参数继续使用 `ArgumentList`；输出先写同目录临时文件，成功后移动发布；取消 FFmpeg 会终止子进程树。ComfyUI 下载、Comfy 输入复制、字幕和 TTS 均采用临时文件发布。
- 备份脚本：数据库存在性检查不再把数据库名插入 SQL；导出完成后检查非空并写入 SHA-256 manifest。脚本未在本次执行，避免未确认的数据库/文件写入。

## 已执行证据

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_asset_path_policy.ps1`：通过，真实 Data 文件均在受控根目录，恶意路径候选全部拒绝。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_llm_egress_policy.ps1`：通过。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_queue_lease_fencing.ps1`：通过。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_idempotency_fencing.ps1`：通过。
- MySQL 只读/会话级表达式检查：`DATE_ADD(NOW(3), INTERVAL @lease_seconds SECOND)` 通过；未修改业务表。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_external_process_boundary.ps1`：通过。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_p0_boundary_static.ps1`：通过。
- PowerShell UTF-8 `ParseInput`：全部脚本通过。
- `dotnet build server/VideoStudio.Server.csproj --no-restore --nologo`：0 warning / 0 error。
- `npm run build`（`web`）：通过；仅有现存 bundle 体积和第三方 PURE 注释提示。
- 本机 API 只读冒烟：`/api/health` 200 且数据库可读；未初始化管理员时 `/api/auth/status` 返回未配置，未认证 `/api/projects` 返回 503；恶意 Origin 未获得 CORS allow header。未执行 setup/login、任务提交、迁移或 GPU 生产。

## 仍未通过或待验证

- 数据库运行账户仍需从 root 切换到最小权限账户；正式迁移、备份和隔离恢复尚未执行。
- 本机只读数据库探针仍显示 `root@%`、`require_secure_transport=0`、`bind_address=*`；这属于环境权限/网络配置，不在本次代码补丁中擅自修改。
- 备份脚本只完成代码级完整性检查，尚未取得新的 `backup_id` 或完成恢复演练。
- LLM 策略尚未在真实外部 provider 上发送请求；API key 仍沿用现有 system_settings 存储方式，未做 DPAPI/密钥库迁移。
- 租约跨进程竞态、GPU 命名信号量的双进程抢占、产物最终 FFprobe/人工质量验收仍需数据库和真实服务环境验证；代码已加入 `Local\\AI-Video-Studio-GPU` 操作系统级闸门。
- 未开放局域网或公网；受监督本机研发仍保持 Conditional Go。

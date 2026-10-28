# 2026-08-10 第一阶段实施记录

本轮按“先稳定生产闭环，再补安全与资产治理”的顺序落地了第一阶段改造。

## 已实现

- 生产启动、关键帧批准、I2V、TTS、字幕和 Episode Render 接入 `Idempotency-Key`；相同键和相同指纹复用原任务，相同键但参数变化返回 409。
- `generation_tasks` 增加 `request_id`、`idempotency_key`、`input_fingerprint`、`state_version`、租约、心跳、取消、deadline、超时和 `production_run_id`；新增 `task_events` 审计事件表。
- 队列改为 GPU 单并发、CPU 单并发。TTS、字幕、FFmpeg 不再被长时间 GPU Comfy 任务完全阻塞；任务领取、完成、重试和取消均带 worker 条件保护。
- 新任务按资源类型设置绝对执行时限，超时进入 `TASK_TIMEOUT`；服务重启可以按过期租约恢复 Pending。
- 关键帧候选改为显式选择，不再自动选第一张。
- 角色/场景参考图进入任务参数，并复制到 Comfy 输入目录。新增 `06_scene_keyframe_reference_api.json`；有参考图时关键帧切换到参考图工作流，I2V 切换到 LTX character-lock 工作流。要求参考图但工作流无法绑定时直接失败。
- 新增 `/api/audio/preflight`，通过实际生成 WAV、FFprobe 和文件大小/时长检查中文 TTS；生产启动在生成音频前执行同一预检。
- TTS 输出采用临时文件、FFprobe 校验和原子移动，拒绝空音频和无效缓存。

## 本地证据

- 数据库迁移前备份：`C:\install\AI\VideoStudio\backup\20260810_221931`。
- `dotnet build server\VideoStudio.Server.csproj --no-restore`：0 warnings / 0 errors。
- `npm run build`：通过；仅保留现有 Rollup 大 chunk 提示。
- `/api/health`：MySQL、ComfyUI 3.13.2、RTX 4070、FFmpeg 均在线。
- TTS 预检：通过，实际 WAV 时长约 2.22 秒。
- 中文 TTS 实际任务 569：Succeeded，UTF-8 文本 `中文语音测试。` 生成 WAV，时长约 2.22 秒。
- CPU/GPU 并发：GPU 任务 536 Running 时，CPU TTS 任务 552 Succeeded，耗时约 590ms。
- 参考关键帧任务 560 Succeeded；ComfyUI 历史节点 4 的 LoadImage 收到 `video_studio_input_560_reference_1.png`。
- I2V 任务 539 的 ComfyUI 历史使用 LTX character-lock，节点 79 和 LTXVAddGuide 收到 `video_studio_input_539_reference_1.png`。
- 幂等回归：同键同参数返回同一任务 553；同键不同参数返回 HTTP 409。

## 尚未完成

- 本轮没有实现登录、RBAC、CSRF、统一资产 ID/manifest、出站 SSRF allowlist、outbox/reconciler、完整备份恢复演练；这些仍是上线前 P0/P1。
- 参考图目前通过 LoadImage、img2img 和 LTX guide 实现，不等同于已安装 IP-Adapter/ControlNet/角色 LoRA；需要后续模型资产和人工一致性验收。
- 本地健康、构建和样例生成不代表目标环境、真实设备、并发压力或公开网络发布已验收。

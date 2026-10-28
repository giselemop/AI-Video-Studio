# Stage 3B Gate 3：正式迁移与应用切换报告

日期：2026-08-13\
状态：`PASS`（仅本轮明确授权范围）

## 范围与授权

本轮依据用户明确授权，目标正式数据库仅为 `ai_video_studio`。允许创建的正式账户为 `ai_video_studio_app@127.0.0.1` 和 `ai_video_studio_migrator@127.0.0.1`；未修改或删除现有 root，未执行正式业务数据修复。

密码由本机随机生成，仅保存于当前用户可读的本机安全文件 `%LOCALAPPDATA%\AI-Video-Studio\stage3b-formal-credentials.json`，本报告、命令输出和日志均不包含密码或完整连接串。

## 可重复命令

以下命令均在 `C:\install\AI\VideoStudio` 执行，退出码均为 `0`：

```text
dotnet build .\server\VideoStudio.Server.csproj --no-restore
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-setup
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-privilege
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-migrate
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-config-status
```

Harness 只接受精确数据库和账户边界；不接受已存在的同名账户、模糊主机匹配或非授权数据库。

## 迁移结果

| 检查 | 结果 |
|---|---|
| 正式迁移前 | 41表、5个既有迁移版本、Pending/Running=0；项目和任务空闲 |
| 本轮正式迁移 | 使用 migrator 执行 `008_stage12_production_core.sql` 首次前滚 |
| 重复执行 | 使用同一 migrator 再执行一次，成功且未产生重复对象 |
| 正式迁移后 | 49表、6个版本，包含 `008_stage12_production_core` |
| 必需对象 | 8张核心新表、必需列、索引和外键核验通过 |
| 既有数据 | projects、episodes、shots、assets、generation_tasks、generation_results 数量及任务状态聚合不变 |
| AUTO_APPLY_SCHEMA | 有效值为 `0`；迁移由显式 migrator 命令完成，启动不会隐式修改 schema |
| Worker | `AI_VIDEO_STUDIO_WORKER_ENABLED=0`；本轮未领取或执行正式任务 |
| migrator 生命周期 | 008完成后设置为 `ACCOUNT LOCK`，避免其继续作为运行账户使用 |

001～005、007 作为正式库既有基线；001～005、007、008 的等价干净库首次/重复迁移及结构/领域集成证据见 `STAGE25_DATABASE_MIGRATION_REPORT_2026-08-13.md`。本轮正式库只按真实当前迁移规则执行新增的008，不重复重建正式业务数据。

## 配置切换

迁移成功后，`config/local.env` 有效配置切换为正式 app 账户、`127.0.0.1`、正式数据库名、`AUTO_APPLY_SCHEMA=0`、Worker=0；`config/appsettings.json`和示例配置的非敏感默认用户也不再指向 root。`--stage3b-config-status`使用 app 账户执行 `SELECT 1` 成功，并确认有效设置不含 root。

## 安全边界与未完成项

- root 账户未修改、未删除、未降权。
- 未执行正式库回滚或数据修复；追加式008前滚的正式备份和恢复证据见 Stage 3A 报告。
- 未执行真实 GPU、Worker、ComfyUI生成、正式媒体写入或删除。
- 后续任何账户权限变化、迁移、回滚和生产启停仍需单独确认。

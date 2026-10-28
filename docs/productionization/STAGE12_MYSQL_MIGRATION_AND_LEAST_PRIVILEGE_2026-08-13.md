# 阶段2.5迁移与MySQL最小权限清单

## 1. 迁移文件

`database/migrations/008_stage12_production_core.sql`为追加式显式迁移，新增：

- `production_profiles`、`project_production_profile_bindings`；
- `entity_versions`、`shot_plans`；
- `task_attempts`、`asset_manifests`、`artifact_publish_intents`；
- `llm_egress_audit`及其脱敏预览/重定向/超时字段。

同时由`Stage12SchemaMigrator`按`information_schema`检查给既有任务、结果、事件和资产表增加关联列/索引。迁移使用MySQL advisory lock `ai-video-studio:stage12-schema`，重复执行先查`schema_migrations`，列和索引也逐项幂等检查；没有DROP TABLE或DELETE数据语句。

## 2. 阶段2.5实际结果

- `AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA`仍默认关闭；示例配置为`0`。
- 用户授权后，在全新`ai_video_studio_stage12_acceptance_20260813`执行001～005、007、008；006是干净库数据修复脚本，按真实迁移规则N/A。
- 首次和重复迁移均成功；结构核验49表、缺表/列/索引/外键均为0。正式数据库没有迁移、数据修复或权限修改。
- `scripts/test_stage25_api_startup.ps1`以`AUTO_APPLY_SCHEMA=0`启动loopback API，HTTP 200且schema摘要不变；Worker=0，未提交任务。
- 迁移、行数、schema时间和账户清理详见`STAGE25_DATABASE_MIGRATION_REPORT_2026-08-13.md`及`STAGE25_ISOLATED_DB_STATUS_2026-08-13.md`。

## 3. 建议账户与权限（清单，不是已执行操作）

建议使用独立账户，名称仅为提案：

| 账户 | 用途 | 建议数据库级权限 | 明确禁止 |
|---|---|---|---|
| `ai_video_studio_app`@`127.0.0.1` | API/Worker运行时 | `SELECT, INSERT, UPDATE, DELETE` on `ai_video_studio`.*；如部署要求可单独限制到表 | `CREATE, ALTER, DROP, INDEX, REFERENCES, FILE, PROCESS, SUPER, GRANT OPTION, CREATE USER` |
| `ai_video_studio_migrator`@`127.0.0.1` | 人工批准的迁移窗口 | `SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES` on指定数据库；仅迁移窗口启用 | 不用于API/Worker；无全局权限、无`GRANT OPTION`、无`CREATE USER` |
| `ai_video_studio_backup`@`127.0.0.1` | 备份/恢复演练 | 按工具需要的数据库级只读/锁表权限，单独审批 | 不与API账户复用，不给DDL或全局权限 |
| `ai_video_studio_stage12_app`@`127.0.0.1` | 隔离集成测试 | 仅`ai_video_studio_stage12_acceptance_20260813`的`SELECT, INSERT, UPDATE, DELETE` | 已创建并验证；测试后已删除 |
| `ai_video_studio_stage12_migrator`@`127.0.0.1` | 隔离迁移测试 | 仅上述隔离库的`SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES` | 已创建并验证；测试后已删除 |

运行时现有代码仍包含项目/角色/字幕的业务删除操作，所以最小可用运行账户目前需要DELETE；后续如改为软删除可再收紧为SELECT/INSERT/UPDATE。`GET_LOCK/RELEASE_LOCK`为单连接函数，不等于全局管理权限。

## 4. 正式切换前门禁

正式库仍使用现有配置，未在本轮切换。正式迁移必须先完成备份/恢复演练、正式非root账户审批、权限逐项核对、AUTO_APPLY_SCHEMA显式窗口、回滚/前滚方案和停机/恢复责任人确认；不得复用本轮临时账户或密码。正式库、root、媒体和公网边界继续保持不变。

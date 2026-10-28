# 阶段2.5隔离MySQL迁移报告

日期：2026-08-13\
范围：仅本机、仅用户授权的全新隔离对象；不代表正式库放行。

## 1. 隔离边界

| 对象 | 值 | 结果 |
|---|---|---|
| 隔离数据库 | `ai_video_studio_stage12_acceptance_20260813` | 保留 |
| 临时应用账户 | `ai_video_studio_stage12_app@127.0.0.1` | 测试完成后已删除 |
| 临时迁移账户 | `ai_video_studio_stage12_migrator@127.0.0.1` | 测试完成后已删除 |
| 正式数据库 | 未写入、未迁移、未修复 | 未触碰 |
| 现有root账户 | 未修改、未删除 | 未触碰 |
| 凭据 | 本机随机生成，临时安全配置使用后删除 | 未写入日志、报告或聊天 |

## 2. 实际迁移命令与结果

以下命令均通过本机安全配置加载数据库凭据，报告不记录密码或完整连接串：

```text
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-setup
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-apply
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-apply
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-structure
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-migration-report
```

| 验证项 | 结果 | 实际证据 |
|---|---|---|
| 全新库首次迁移 | PASS | migrator账户完成基线及002～005、007、008；006为干净库数据修复脚本，按规则N/A |
| 008首次执行 | PASS | 008表、列、索引、关联外键和schema_migrations记录存在 |
| 重复执行 | PASS | 第二次`--stage25-apply`成功，无重复对象、无重复版本记录 |
| 结构 | PASS | 49张表；缺表0、缺列0、缺索引0、缺外键0 |
| AUTO_APPLY_SCHEMA=0 | PASS | loopback API启动前后结构摘要不变；启动未修改schema |
| 回滚/破坏性验证 | NOT RUN | 本轮不删除隔离库、不执行破坏性回滚；前滚和重复执行已验证 |

迁移实现使用数据库版本记录、数据库锁和information_schema检查；008本身不执行DROP TABLE或业务数据DELETE。首轮试运行发现基线SQL前置注释解析问题，隔离迁移账户随后在正式库权限检查处被拒绝；修正解析逻辑后重新执行，首次和重复迁移均通过，未造成正式库变化。

## 3. Schema版本与行数摘要

本轮报告生成时记录的schema版本为：

| 版本 | 首次记录时间（UTC） |
|---|---|
| `001_database_sql` | 2026-08-13T06:32:28.3290000Z |
| `002_production_pipeline` | 2026-08-13T06:32:28.3270000Z |
| `003_video_qa` | 2026-08-13T06:32:28.9450000Z |
| `004_reliability_references_audio` | 2026-08-13T06:32:29.4000000Z |
| `005_quality_optimization` | 2026-08-13T06:32:29.5820000Z |
| `007_local_auth_audit` | 2026-08-13T06:32:29.6750000Z |
| `008_stage12_production_core` | 2026-08-13T06:32:31.5840000Z |

时间戳是数据库实际记录摘要，不作为迁移顺序的唯一证据；版本存在性、结构和重复执行结果才是本轮判定依据。代码已修正未来干净库中基线版本标记先于002的执行顺序。

测试数据行数摘要：

```text
projects=8
episodes=4
shots=3
generation_tasks=21
task_attempts=20
asset_manifests=4
artifact_publish_intents=4
entity_versions=21
shot_plans=3
llm_egress_audit=2
```

## 4. 结论与边界

隔离迁移和重复执行通过，正式数据库仍未迁移。隔离库保留供下一轮复核；临时账户已删除，不能使用本轮账户或临时凭据连接下一轮。正式迁移仍需独立审批、备份/恢复演练、非root账户窗口和明确回滚/前滚责任人。

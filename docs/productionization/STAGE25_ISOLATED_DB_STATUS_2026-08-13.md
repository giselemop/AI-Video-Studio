# 阶段2.5隔离数据库与临时账户状态

日期：2026-08-13。状态在本轮阶段结束时记录。

## 1. 保留对象

| 对象 | 最终状态 |
|---|---|
| `ai_video_studio_stage12_acceptance_20260813` | 保留，供下一阶段复核；不属于正式业务库 |
| `ai_video_studio_stage12_app@127.0.0.1` | 已删除 |
| `ai_video_studio_stage12_migrator@127.0.0.1` | 已删除 |
| 临时密码配置 | 已按精确路径删除；密码未进入报告、日志或聊天 |
| 正式数据库 | 未修改、未迁移、未修复 |
| 现有root账户 | 未修改、未删除 |
| 正式媒体 | 未删除、未覆盖 |

## 2. 清理证据

使用：

```text
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-drop-accounts
```

清理程序只对完整匹配的两个用户名和`127.0.0.1`主机执行删除；随后使用精确`SHOW GRANTS`确认账户不存在，并确认隔离数据库仍保留。没有使用通配符、变量目标或递归删除。

## 3. 保留库摘要

迁移结束时结构为49表；测试数据摘要包括`projects=8`、`episodes=4`、`shots=3`、`generation_tasks=21`、`task_attempts=20`、`asset_manifests=4`、`artifact_publish_intents=4`、`entity_versions=21`和`llm_egress_audit=2`。这些都是本轮隔离测试数据，不得当作正式业务数据。

## 4. 后续处理边界

下一轮复核前不自动清理该隔离数据库，也不复用已删除临时账户。若未来需要删除隔离库，必须再次得到明确授权，并再次确认名称完全匹配；正式数据库/root/媒体仍不在清理范围内。

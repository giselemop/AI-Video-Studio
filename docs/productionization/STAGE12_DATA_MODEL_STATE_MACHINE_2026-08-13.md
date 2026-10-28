# 阶段1/2数据模型与任务状态机

日期：2026-08-13\
范围：本机安全研发实现；阶段2.5已在授权隔离数据库完成集成验证，未在正式数据库执行迁移，未提交真实GPU任务。

## 1. 不可变生产规格

`production_profiles` 以 `(project_id, profile_key, version)` 和内容哈希唯一约束保存画幅、输出分辨率、FPS、音频编码/采样率、色彩空间及设置。`project_production_profile_bindings` 只表示项目当前绑定，不改变历史Profile行。

`entity_versions`统一保存 Character、Scene、Prompt、Workflow、Voice 的实体快照、来源Asset ID数组、内容哈希、版本和创建者。`shot_plans`保存 Project/Episode/Shot、ProductionProfile、各类版本ID、输入Asset ID数组、参数快照和内容哈希。仓储层只提供追加/按哈希复用，不提供版本原地更新或删除。

## 2. 任务、Attempt和产物

现有`generation_tasks`通过008迁移增加`production_profile_id`、`shot_plan_id`、`input_asset_id`、`active_attempt_id`、`lease_token`和`output_manifest_id`；`generation_results`、`task_events`和`assets`增加对应Attempt/Manifest关联。

每次领取在同一事务中创建`task_attempts`：`attempt_no`、随机`lease_token`、`worker_id`、`state_version`、租约时间、心跳时间和`Temp/Tasks/task-{id}/attempt-*`临时目录。正式发布先写`asset_manifests`和`artifact_publish_intents`为Staged，产物验证、哈希、原子移动和结果登记完成后，任务成功事务把Staged改为Ready；失败、取消、租约过期改为Quarantined/Rejected或NeedsReconcile。

## 3. 状态机

| 当前状态 | 允许的下一状态 | 入口 |
|---|---|---|
| Pending | Running、Failed、Cancelled | Claim、依赖失败、取消 |
| Running | Pending、Succeeded、Failed、Cancelled | 重试、完成、失败、超时、取消 |
| Failed | Pending | Retry；会清理活动租约并创建新Attempt |
| Cancelled | Pending | Retry；会清理活动租约并创建新Attempt |
| Succeeded | 无 | 终态，不允许重新运行原Attempt |

`TaskStateMachine`在`server/ProductionCoreModels.cs`执行白名单检查；`TaskLeaseRepository`所有Running写入都带`task_id + active_attempt_id + lease_token + lease_owner + state_version`条件。取消、重试、过期恢复和完成均先对任务行`FOR UPDATE`，再写事件和Attempt状态。

## 4. 版本/状态不变量

1. 同一个幂等键只能对应一个指纹；指纹不同返回冲突。
2. 旧Attempt的心跳、进度、错误、完成和发布不能匹配新Attempt的token。
3. `Succeeded`不能没有已验证的主Manifest；有Staged产物时必须提供主Manifest。
4. 终态任务不允许原地转回Running；Retry只允许Failed/Cancelled转Pending。
5. 正式任务只接受ProductionProfile/ShotPlan/Asset ID，原始文件路径属于旧兼容面，FormalTaskSubmissionService明确拒绝。

## 5. 隔离集成结果

`--stage25-domain`在隔离库真实创建并读取ProductionProfile绑定、Character/Scene追加版本、Prompt/Workflow/Voice快照、ShotPlan、TaskAttempt、AssetManifest和ArtifactPublishIntent；验证哈希复用、历史引用不变、跨Project拒绝、被引用删除保护、定向重做新Attempt以及Staged/Ready/Quarantined状态。`test_stage25_races.ps1`使用两个独立进程验证幂等、双Worker、租约恢复、迟到完成、取消/完成、非法迁移和重试上限。

## 6. 证据边界

上述结果只证明隔离库和受控夹具中的代码行为，不证明正式数据库、真实媒体、ComfyUI或生产Worker。`dotnet test`退出码为0但未发现独立测试用例，故不计为独立单元测试PASS；备份恢复、正式账户切换和真实GPU仍未运行。

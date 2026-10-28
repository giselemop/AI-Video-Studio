# 阶段1/2竞态测试报告

日期：2026-08-13。测试全部在`C:\install\AI\VideoStudio`进行；使用用户授权的隔离库`ai_video_studio_stage12_acceptance_20260813`和两个独立dotnet进程；没有执行正式数据库写入、没有提交真实GPU任务。

## 结果矩阵

| 场景 | 本轮状态 | 实际证据 | 结论边界 |
|---|---|---|---|
| 重复/并发幂等提交 | PASS | 两个独立进程；同键同指纹复用Task 22，同键不同指纹对Task 24返回明确冲突 | 仅隔离库 |
| 两个Worker领取同一任务 | PASS | 两个独立进程争抢同一Task；一个领取Attempt 1，另一个条件失败；胜者完成 | 仅隔离库 |
| 租约过期恢复 | PASS | 短租约后第二进程恢复；创建新Attempt；旧Worker完成影响行数0 | 仅隔离库 |
| 旧Worker迟到完成/心跳 | PASS | 旧lease token完成和心跳均影响行数0 | 仅隔离库 |
| 旧Worker产物 | PASS | 旧Attempt产物进入隔离/Quarantined，不能成为Ready | 仅隔离库/受控文件 |
| 取消/完成竞态 | PASS | 两个独立进程只有一个改变合法终态，另一方影响行数0 | 仅隔离库 |
| 最大重试上限 | PASS | maxRetries=1任务已有2次Attempt，继续Retry影响行数0，最终Failed | 仅隔离库 |
| 跨进程GPU锁竞争/恢复 | PASS（锁层） | 两进程临界区无重叠；持锁进程异常退出后新进程重新获取 | 不证明真实Comfy/GPU生成 |
| 非法状态迁移 | PASS | `Pending→Succeeded`及非法租约完成被拒绝，影响行数0 | DB/核心均有证据 |
| 半文件/空文件/损坏媒体 | PASS | 三类暂存输入均拒绝；同一最终目标非覆盖移动失败 | 真实视频未生成 |

## 已执行命令

```text
dotnet build server/VideoStudio.Server.csproj --no-restore
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage12_core.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage12_gpu_lock.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_queue_lease_fencing.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_idempotency_fencing.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage25_races.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage25_gpu_lock_recovery.ps1
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-domain <本机安全配置>
```

构建退出码0、0警告/0错误；阶段2.5竞态套件9/9通过，GPU锁竞争和异常退出恢复通过，域模型集成通过。报告保留任务状态/Attempt/Manifest摘要，不包含凭据。PowerShell旁路仅作用于当前测试进程，未改变系统执行策略。

## 后续隔离测试顺序

正式数据库仍不得直接套用本报告。下一轮若继续，先复核保留隔离库，再单独申请正式迁移/备份恢复窗口；本轮所有失败均保持原断言，未通过降低断言或扩大忽略范围处理。

# 阶段2.5完整竞态验收报告

日期：2026-08-13\
数据库：`ai_video_studio_stage12_acceptance_20260813`\
进程模型：任务竞态使用两个独立dotnet进程；GPU锁使用独立dotnet探针；不是源码正则、静态脚本或单进程Mock。

## 1. 可重复执行

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage25_races.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_stage25_gpu_lock_recovery.ps1
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-summary <TaskId>
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-manifest-summary <ManifestId>
```

竞态报告根目录：`%TEMP%\ai-video-studio-stage25-races-0dcb206a098547a1b4a3f2f7deea8b4b`。GPU恢复夹具：`%TEMP%\ai-video-studio-stage25-gpu-recovery-2c2d25c1060c488a9f57944f60d8bd92`。两处均为本轮受控临时证据，不是正式媒体目录。

## 2. 15项强制场景

| # | 测试名称 | 进程/Worker | 初始状态 | 交错顺序 | 预期 | 实际结果与数据库摘要 | 结果 |
|---:|---|---:|---|---|---|---|---|
| 1 | 相同幂等键并发提交 | 2 | 无任务 | A提交、B提交 | 只有一个有效任务 | 两方复用Task 22；无第二有效任务 | PASS |
| 2 | 同键不同指纹 | 2 | 无任务 | A先写、B带不同指纹 | 明确拒绝冲突 | Task 24为唯一胜者；另一方IdempotencyConflict | PASS |
| 3 | 双Worker领取同一任务 | 2 | Pending | A/B同时Claim | 仅一个领取 | 一个Attempt 1成功，另一方未领取；Task 12最终Succeeded | PASS |
| 4 | 心跳token围栏 | 2个执行者 | Running/有效lease | 新token取得后旧token心跳 | 旧token不能续租 | 旧心跳影响行数0 | PASS |
| 5 | 租约过期恢复 | 2 | Running/短租约 | A停止续租，B等待过期并恢复 | 新Worker可恢复 | 新Attempt建立；旧Attempt被隔离 | PASS |
| 6 | 旧Worker迟到完成 | 2 | 新Attempt已生效 | 旧A完成晚于B恢复 | 旧完成影响0 | 旧完成影响行数0；新状态未被覆盖 | PASS |
| 7 | 旧Worker产物不能Ready | 2+受控文件 | 旧Attempt有暂存产物 | 旧产物发布晚于恢复 | 不能成为Ready | Manifest 4、Asset 4为Quarantined，Intent为Rejected | PASS |
| 8 | Pending→Succeeded非法迁移 | 2 | Pending | 无合法Claim直接Complete | 拒绝 | 影响行数0；Task 17仍Pending | PASS |
| 9 | Cancel与Complete竞态 | 2 | Running | Cancel/Complete同时竞争 | 只有一个合法终态 | Cancel改变1，Complete改变0；无双终态 | PASS |
| 10 | maxAttempts耗尽 | 2 | Failed/已有Attempt | 继续Retry | 不得继续 | maxRetries=1且已有2次Attempt；Retry影响0，Task 11 Failed | PASS |
| 11 | 两进程GPU锁竞争 | 2 | 锁空闲 | A/B同时进入临界区 | 临界区不重叠 | worker-one和worker-two区间无重叠 | PASS |
| 12 | GPU锁持有进程异常退出 | 2 | A持锁后退出 | 杀止A，B重新获取 | B可重新获取 | crash探针退出后recovery探针entered/exited | PASS |
| 13 | 半/空/损坏媒体最终化 | 2个执行阶段+文件夹 | Staged候选 | 验证后尝试发布 | 不能成功 | 空、损坏PNG、半字幕均拒绝 | PASS |
| 14 | 最终目标不可覆盖 | 2 | 已有最终文件 | 第二次发布同目标 | 不能覆盖 | `File.Move(..., false)`拒绝；旧文件保持 | PASS |
| 15 | Manifest/任务成功无半完成状态 | 2+恢复夹具 | Staged Intent/Manifest | 发布故障后恢复扫描 | Ready必须成套，否则隔离 | 故障样本进入Quarantined/Rejected；恢复后不暴露Ready半成品 | PASS |

## 3. 代表性任务状态摘要

| Task | 最终状态 | attempts | 说明 |
|---:|---|---:|---|
| 11 | Failed | 2 | 达到maxRetries后拒绝继续重试 |
| 12 | Succeeded | 1 | 双Worker仅一方领取并完成 |
| 13 | Cancelled | 2 | 租约恢复/取消路径 |
| 14 | Cancelled | 2 | 旧Worker围栏路径 |
| 15 | Cancelled | 2 | 旧Attempt产物隔离 |
| 16 | Cancelled | 1 | 取消/完成竞态 |
| 17 | Pending | 0 | 非法直接完成被拒绝 |
| 22 | Pending | 0 | 同幂等键复用 |
| 24 | Pending | 0 | 同键不同指纹冲突胜者 |

## 4. 边界与未宣称事项

所有PASS均是隔离数据库、独立本机进程和受控临时目录证据。没有提交ComfyUI真实GPU任务，没有生成正式项目视频，没有开启默认Worker，没有证明正式数据库或连续生产环境的行为。`dotnet test`没有独立测试用例输出，未被用作竞态PASS证据。

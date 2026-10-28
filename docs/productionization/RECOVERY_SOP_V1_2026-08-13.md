# AI Video Studio故障恢复SOP v1

阶段2.5验证范围：本SOP的租约、旧Attempt围栏、Manifest/PublishIntent隔离、原子产物、GPU锁恢复和磁盘保护已在授权隔离库/受控夹具验证；正式库、正式媒体和真实GPU仍需独立门禁。

## 通用原则

先暂停接单并保存任务、Attempt、事件、PublishIntent、Manifest、Asset和日志快照；不直接改数据库状态、不覆盖文件、不删除未知残留。恢复动作必须使用带租约/版本围栏的服务入口。

## Worker中断/租约过期

1. 保持Worker关闭或暂停队列，确认旧进程已退出；不要用删除锁文件代替进程恢复。
2. 只对租约已过期任务运行`TaskLeaseRepository.RecoverExpiredAsync`；它锁任务行、写LEASE_EXPIRED事件、将Attempt标为Abandoned并隔离Staged产物。
3. 新Worker重新领取产生新Attempt/临时目录；旧token的心跳、完成和发布必须影响行数为0。
4. 检查旧Attempt临时目录和PublishIntent；文件存在但数据库未Ready时进入NeedsReconcile清单，不直接复用。

## 取消/完成竞态

取消优先通过队列取消令牌和同一任务行锁处理。若完成先取得围栏，则任务成功且产物Ready；若取消先取得围栏，则完成返回0，产物Quarantined。出现双终态或状态版本不一致时停止队列并保留证据，禁止手工UPDATE。

## ComfyUI失败/OOM

保留Prompt ID、Workflow版本和错误分类；OOM只按受控策略降低参数并以新Attempt重试，达到最大重试进入Failed。不得安装模型、改Workflow或提交真实GPU任务绕过门禁。ComfyUI重启后先做`/system_stats` loopback健康检查，再恢复Pending任务。

## FFmpeg/TTS/字幕/产物失败

检查Attempt临时文件、进程退出码、stderr、文件大小、SHA-256和FFprobe。`.part-*`、`.tmp-*`、未验证媒体不得放入正式Asset。验证失败保持失败/隔离状态，修复后新Attempt重新生成；不覆盖上一成功版本。

## 磁盘不足/锁文件

停止接收高成本任务，记录Data、Temp、Artifacts和Comfy输入/输出容量。只清理已确认可重建且未引用的临时目录，先dry-run并逐路径确认；不递归清理Data根。GPU锁文件是OS句柄锁，进程崩溃后句柄释放但文件可保留为审计痕迹，下一进程不得删除它来“解锁”。

## 数据库/媒体恢复

正式恢复必须由用户确认备份、目标隔离实例和账户。先恢复数据库到新库，再按Manifest相对路径和SHA-256核对媒体；校验通过后才允许只读查看。不得在正式库直接执行回滚/修复，不得把缺少Manifest的文件重新登记为Ready。阶段2.5隔离库保留作为下一轮复核证据，不因本SOP自动删除。

## LLM出站故障

检查allowlist、DNS、HTTPS、0重定向、预算和脱敏审计；`LLM_REDIRECT_BLOCKED`、`LLM_TIMEOUT`或预算拒绝都停止发送并保留审计。不得把完整Prompt、媒体、源码、凭据写入日志或报告。

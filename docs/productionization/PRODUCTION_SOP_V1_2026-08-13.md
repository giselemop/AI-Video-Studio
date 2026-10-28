# AI Video Studio生产SOP v1

本SOP只覆盖已实现的安全研发边界；本轮没有真实视频，正式生产仍需独立门禁。

阶段2.5隔离验收已通过迁移、最小权限、领域模型、双进程竞态、GPU锁恢复、路径/LLM/磁盘负向夹具；这不等同正式生产放行。真实GPU、样片和连续生产前必须重新复核隔离数据库状态，并取得正式迁移、备份恢复、非root账户和单镜头门禁确认。

## 1. 开始前门禁

1. 核对Git工作区、数据库名称/账户、`AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA=0`和`AI_VIDEO_STUDIO_WORKER_ENABLED=0`。
2. 高成本任务提交前执行磁盘空间检查；低于阈值直接拒绝，不通过清理正式目录规避。
3. 确认ComfyUI、模型、Workflow、TTS、FFmpeg版本和许可；不在生产启动时下载或升级依赖。
4. 确认项目、Episode、Shot归属；创建或选择ProductionProfile版本。
5. 通过`CaptureEntityVersionAsync`保存Character、Scene、Prompt、Workflow、Voice快照；创建ShotPlan并锁定输入Asset ID、参数和验收重点。

## 2. 任务提交

1. Formal API只提交Project/Profile/ShotPlan/Asset ID、用途、幂等键和参数快照；不提交任意绝对路径；普通API不得直接把任务改为Completed/Approved/Published。
2. 同一业务请求重试复用相同幂等键；Payload变化必须使用新键。
3. 检查Formal预检、项目归属、Asset Ready/Manifest、扩展名和Workflow版本。
4. 队列领取后记录Attempt、lease token、Worker、临时目录和事件；GPU任务必须经过跨进程文件锁，跨进程临界区只能有一个持有者。

## 3. 产物与审核

1. 生成、增强、TTS、字幕、Episode和Master均只写Attempt临时目录。
2. 完成前检查文件稳定、用途/扩展名、SHA-256、FFprobe/解码、字幕时间轴和QA报告。
3. 成功发布产生新版本Manifest/Asset/Result；旧版本不覆盖、不删除；被引用Asset只能经受控保留策略处理。
4. 技术QA通过后进入人工审核；人工通过、驳回、原因和备注均保存。自动分数不能代替最终批准。
5. 驳回只重跑必要阶段，并创建新Attempt；保留旧输入、版本、产物和QA记录。

## 4. Episode/Master

1. 仅使用Ready、项目归属一致的视频Asset编排Episode。
2. 音频、字幕、混音先分别验证，再运行EpisodeRender；Episode输出是新版本。
3. Master要求Episode Approved、QA锁定、所有Shot通过且无开放阻塞问题。
4. Master、字幕、封面和QA报告分别生成Manifest；完成后记录发布路径和哈希。

## 5. 结束与归档

保存任务/Attempt/事件/Manifest/Asset/QA/人工决定的只读快照，记录版本、耗时、失败分布、磁盘增长和批准秒数。缓存清理先运行dry-run并保存候选清单；任何未完成或NeedsReconcile项不得进入发布清单。

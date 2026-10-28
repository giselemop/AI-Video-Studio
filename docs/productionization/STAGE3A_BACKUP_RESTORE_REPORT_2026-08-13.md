# 阶段3A Gate 1/2备份恢复报告

日期：2026-08-13\
当前阶段：阶段3A；在正式非root账户和正式008迁移前暂停。

## 1. Gate 1：阶段2.5隔离环境复核

| 检查 | 结果 | 证据 |
|---|---|---|
| 隔离数据库名称 | PASS | `ai_video_studio_stage12_acceptance_20260813`仍存在 |
| 隔离表结构 | PASS | 49表；缺表0、缺列0、缺索引0、缺外键0 |
| schema_migrations | PASS | 7条：001、002、003、004、005、007、008 |
| 阶段2.5测试数据 | PASS | projects=8、episodes=4、shots=3、tasks=21、attempts=20、manifests=4；与阶段2.5报告一致 |
| 临时账户 | PASS | `ai_video_studio_stage12_app@127.0.0.1`和`ai_video_studio_stage12_migrator@127.0.0.1`均不存在 |
| 正式库只读基线 | PASS | 41表、5条正式迁移记录、projects=7、episodes=19、shots=148、assets=724、tasks=964；与阶段0基线一致 |
| 正式任务状态 | PASS | Cancelled=55、Failed=20、Succeeded=889；Pending/Running均为0 |
| root | PASS | 现有root权限仍为原基线；阶段2.5未修改root |

Gate 1未重新运行大范围竞态测试，仅执行上述只读核验。

## 2. Gate 2：正式数据库备份

使用项目认可的`scripts/backup.ps1`，内部调用本机MySQL 8.0.22 `mysqldump --single-transaction --routines --events`。未复制`config/local.env`，未上传备份，未写入Git。

| 项目 | 结果 |
|---|---|
| 备份目录 | `C:\install\AI\VideoStudio\backup\20260813_193208` |
| SQL文件 | `ai_video_studio.sql` |
| 创建时间 | 2026-08-13T19:32:09.5844334+08:00 |
| 命令墙钟耗时 | 备份命令约2.2秒；仅作本机操作记录，不作为生产SLA |
| 文件大小 | 4,315,569 bytes |
| SHA-256 | `59ef8347ea770d0777ad48cc9885a0297d25a28b4fc16f515d497e90f939b7f4` |
| 备份结果 | PASS；文件非空且哈希已记录 |

## 3. Gate 2：隔离恢复

恢复目标：`ai_video_studio_restore_acceptance_20260813`。目标创建前已用只读查询确认不存在；创建后通过MySQL客户端导入备份，没有覆盖任何已有数据库。

| 检查 | 结果 |
|---|---|
| 导入 | PASS；导入4,315,569 bytes，退出码0 |
| 导入命令墙钟耗时 | 约2.0秒；仅作本机操作记录，不作为生产SLA |
| 表数量 | PASS；41 |
| 迁移版本 | PASS；002、003、004、005、007，共5条，与正式库一致 |
| 记录聚合 | PASS；projects=7、episodes=19、shots=148、assets=724、tasks=964、generation_results=808 |
| 任务状态 | PASS；Cancelled=55、Failed=20、Succeeded=889 |
| Project→Episode→Shot | PASS；孤立Episode=0、孤立Shot=0、Project归属不一致=0 |
| Task/Result关系 | PASS；孤立Task=0、孤立GenerationResult=0 |
| Asset路径摘要 | PASS；724/724有path、relative_path和sha256 |
| 结构摘要 | PASS；indexes=155、foreign_keys=41；阶段2.5新表在正式备份中为0，符合迁移前状态 |
| 媒体抽样 | PASS；Asset ID 1～10均存在、大小匹配、SHA-256匹配；可探测视频/音频样本FFprobe通过 |

正式库已有35个`assets.project_id IS NULL`和71个`generation_tasks.project_id IS NULL`记录；恢复库数量完全相同，未出现新增断链。该项是基线数据特征，不被误报为恢复差异。

## 4. Gate 2结论

Gate 2 `PASS（隔离恢复）`。恢复库和备份均保留，未删除正式媒体、正式数据库或备份文件。Gate 3仍未执行：正式运行账户/迁移账户名称、保留策略和正式008迁移属于正式数据库与权限变更，需获得用户对具体对象和窗口的直接确认后才能继续。

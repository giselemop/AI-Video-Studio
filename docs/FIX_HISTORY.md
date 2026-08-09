# AI Video Studio 修复记录

本文件保留本阶段真实发现、修复和复测证据。每一项的最终状态只有 Passed；历史上的未通过结果没有被删除，而是记录在“修复前结果”中。

| 时间 | 问题 | 原因分类 | 修改内容 | 测试方法 | 修复前结果 | 修复后结果 | 状态 |
|---|---|---|---|---|---|---|---|
| 2026-08-09 | 数据库无法进入真实 CRUD/QA | 配置问题 | 使用用户提供的本地凭据配置 `config/local.env`；不写入报告 | 备份、Migration、健康检查、CRUD、真实任务 | 数据库依赖未通过 | 数据库在线；34 表；002/003 已应用 | Passed |
| 2026-08-09 | 备份 SQL 目标路径为空 | 脚本问题 | 使用明确的 `--result-file`，并预检查数据库是否存在 | `scripts/backup.ps1`，检查备份文件大小 | 备份脚本报路径错误 | 备份目录和非空 SQL dump 均验证通过 | Passed |
| 2026-08-09 | Schema 初始化输入失败 | 数据库/脚本问题 | 改用 MySQL 客户端 `source` 执行 schema；修复 JSON seed 和长路径索引 | `scripts/init_database.ps1`；读回 Migration、表和 preset | 初始化中断 | 34 表、3 QA preset、3 generation preset | Passed |
| 2026-08-09 | GUID 插值格式在运行时异常 | 代码问题 | 将非法 `Guid.NewGuid():N` 改为 `ToString("N")` | `rg` 全量扫描；.NET build；API 真实创建路径 | 运行时可能抛出格式异常 | 全量扫描无残留；build 0 警告/0 错误 | Passed |
| 2026-08-09 | 默认视频只达到约 3 秒 | 参数问题 | Smoke 与 I2V 参数统一为 121 frames / 24 FPS / 5 秒 | 真实 I2V task 4；FFprobe；技术 QA | 73 frames 结果约 2.99 秒 | 真实结果约 4.96 秒，技术 QA 100 | Passed |
| 2026-08-09 | QA 锁定状态判断错误 | 数据库/代码问题 | 修复 MySQL `TINYINT(1)` 返回 Boolean 的读取逻辑 | Approved、锁定、解锁、锁定时拒绝检查/重生成 | 锁定 Episode 检查接口错误放行 | 锁定时 Shot/Episode 检查均返回 409；解锁后流程正常 | Passed |
| 2026-08-09 | Episode render 返回未知字段错误 | 数据库 SQL 问题 | 修正音频结果排序字段，从不存在的 `s.shot_id` 改为有效字段 | 真实 3-shot Episode render | 合成返回 503 | Render task 24 成功，1920x1080/30 FPS/14.7 秒 | Passed |
| 2026-08-09 | 发布目录被运行服务锁定且脚本误报 | 运维/脚本问题 | 发布前安全停止目标服务；`publish.ps1` 检查 npm 和 dotnet 原生退出码 | 停止、发布、启动、HTTP health | 发布复制失败但脚本继续打印成功 | 发布成功；重启后数据库/ComfyUI/FFmpeg 全部在线 | Passed |
| 2026-08-09 | QA 回炉复用原 Seed | Workflow/参数问题 | 每次回炉生成新 Seed，并把 changedParameters 写入任务参数和日志 | Shot 11 两轮真实 I2V | 回炉参数可能完全相同 | 两个 Seed 不同，且日志可读回 | Passed |
| 2026-08-09 | QA 回炉没有自动增强和再次 QA | Workflow/代码问题 | QA-Retry I2V 自动排队 1080P Enhance；增强成功后自动排队 ShotQA | Shot 11 实际执行两轮完整链路 | 回炉后只停留在低分辨率视频 | 两轮均完成 `ShotQA → I2V → Enhance → ShotQA` | Passed |
| 2026-08-09 | 已完成 Enhance 被误判为活动任务 | 数据库查询问题 | 活动任务只统计 Pending/Running，排除 Succeeded | Shot 11 第二轮回炉 | 第二轮无法继续排队增强 | 第二轮 Enhance 和 QA 均成功执行 | Passed |
| 2026-08-09 | 回炉日志记录旧的 AutoChecking/0 分 | 代码问题 | 将本轮真实 `evaluation.Status` 和 `evaluation.Score` 传入回炉记录 | Shot 11 最终回归；读取 operation_logs 和 input_json | 原因和分数不准确 | 两轮日志分别记录 Rejected/73.05、Rejected/85.35 | Passed |
| 2026-08-09 | QA 夹具判定与时序/损坏文件兼容性问题 | QA/FFmpeg 问题 | 修复 FFprobe 数字解析、损坏文件判定、时序 Warning、PowerShell 参数过滤 | `qa_test.ps1` 9 个真实夹具 | 个别夹具结果与预期不一致 | 9/9 与预期一致 | Passed |
| 2026-08-09 | 队列回归不完整 | 任务队列问题 | 保留取消、暂停/恢复和任务重试路径，补充实际回归 | cancel task 46；retry task 47；检查 attempts/errorType | 缺少闭环证据 | 取消成功；缺失输入按预期失败并重试到 attempts=2 | Passed |
| 2026-08-09 | 生产流水线回归首次 404 | 测试脚本问题 | `Call-Api` 显式枚举 `Invoke-RestMethod` 返回的 JSON 数组，修复项目/集筛选 | 首次运行 `test_production_pipeline.ps1`；检查实际 HTTP 路径和服务端点 | 项目筛选为空，构造 `/api/projects//episodes`，返回 404 | 修复后同一脚本 health、文件、数据库和 5 Shot RuleBased 分析全部通过 | Passed |

## 最终回炉证据

Shot 11 的真实任务链：

`39 ShotQA → 40 I2V → 41 Enhance → 42 ShotQA → 43 I2V → 44 Enhance → 45 ShotQA`

最终 `qa_retry_count=2`，没有第三个回炉任务。最终测试使用故意不匹配的 9999x9999 Episode 输出标准，因此 Shot 最终保持 Rejected 是边界测试的预期业务结果；回炉机制本身验收状态为 Passed。

## 备份与数据安全

数据库修改前已创建备份：

`C:\install\AI\VideoStudio\backup\20260809_100930`

本阶段没有删除既有业务数据；清理动作仅删除了本轮临时 CRUD 测试记录。

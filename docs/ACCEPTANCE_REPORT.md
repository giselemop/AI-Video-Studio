# AI Video Studio 强制验收报告

验收时间：2026-08-09  
验收范围：本地数据库、项目生产链路、ComfyUI I2V、FFmpeg 增强、Shot/Episode QA、回炉、发布和 UI。

## 最终结论

阶段状态：**Passed**

所有核心验收项：**Passed**  
未保留 Failed 项：0  
未保留 Blocked 项：0

本报告只记录已经实际执行并重新验证的结果。内容质量中的人物身份、动作语义和场景连续性仍由人工复核确认；当前 CPU QA 不冒充未安装的视觉身份模型。

## 验收矩阵

| 功能 | 状态 | 实际验收证据 |
|---|---|---|
| 编译与发布 | Passed | .NET 8 构建 0 警告/0 错误；Vue production build Passed；发布脚本已检查原生退出码 |
| 服务健康 | Passed | HTTP 18080；数据库在线；ComfyUI 在线；FFmpeg 可用；RTX 4070，12281 MiB 总显存，检查时约 11018 MiB 空闲 |
| 数据库与 Migration | Passed | 已备份后应用 `002_production_pipeline`、`003_video_qa`；34 张表；QA preset 3；generation preset 3 |
| 项目/人物/场景/Episode/Shot CRUD | Passed | 独立 CRUD 回归创建、修改、读取、删除均通过；清理只针对本次临时数据 |
| 5 秒 I2V | Passed | 真实 Episode 4 的 I2V tasks 14、15、16；121 frames、24 FPS；3 个任务全部成功 |
| 1080P/30FPS 增强 | Passed | Enhance tasks 17、18、19；输出均为 1920x1080、30 FPS、约 4.9 秒 |
| 三镜头 Episode | Passed | Project 4 / Episode 4 / Shot 6、7、8；3 个真实镜头均完成生成、增强和人工复核 |
| Shot QA | Passed | Shot QA tasks 20、21、22；三镜头最终均 Passed，分数均 90.60，开放问题 0 |
| Episode QA | Passed | Episode QA task 23；整体分数 91.11；人工复核后 Approved，`qaLocked=true` |
| Episode 合成 | Passed | Render task 24；1920x1080、30 FPS、14.7 秒，输出可解码 |
| Master 导出 | Passed | Export task 26；Master、封面、QA_REPORT.md、QA_REPORT.json 均存在且非空 |
| Master 技术 QA | Passed | 分数 100；H.264；1920x1080；30 FPS；无黑帧；解码错误 0；突变比例 0 |
| QA 夹具 | Passed | `qa_test.ps1` 9/9 通过：正常、黑帧、短视频、分辨率、时序、损坏、缺音频、字幕超时、末日列车成片 |
| 自动回炉 | Passed | Shot 11 实际执行两轮 `ShotQA → I2V → Enhance → ShotQA`；两次 Seed 不同；`qa_retry_count=2` 后无第三轮 |
| 任务队列回归 | Passed | 暂停/恢复/取消/重试通过；取消 task 46 成功；缺失输入 task 47 按预期失败且 attempts=2 |
| UI 验收 | Passed | Chrome 实际打开质量验收页；数据库/ComfyUI/GPU 状态正确；Approved Episode、锁定状态和 Master 导出按钮正确显示 |
| 文档与日志 | Passed | `install_log.txt`、本报告、`FIX_HISTORY.md`、QA 报告均已生成 |

## 三镜头真实产物

项目：`Acceptance 3Shot 20260809_104019`  
Episode：`Three Shot Acceptance Episode`  
Master：

`C:\install\AI\Data\Output\Release\Acceptance 3Shot 20260809_104019\Episode001\Acceptance 3Shot 20260809_104019_Episode_001_MASTER.mp4`

封面与报告位于同一目录。Master 文件大小约 13.8 MB，技术 QA 分数 100。

抽帧人工复核文件：

- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_1.png`
- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_2.png`
- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_3.png`

## 自动回炉边界证据

Shot 11 使用故意不满足 Episode 输出分辨率的测试条件，验证的是回炉机制本身，不是业务成片。任务 39—45 全部执行成功，链路为：

`ShotQA → I2V → Enhance → ShotQA → I2V → Enhance → ShotQA`

两次回炉 Seed 分别为 `287263580`、`482466601`，均不同。数据库日志同时记录了：原始 `Rejected` 状态、原始 QA 分数、修改的 Seed、新视频路径、新增强 QC 分数和新 QA 分数。第二次 QA 后达到上限，未创建第三个 I2V 任务。

## 已闭环修复的问题

以下问题均已完成“发现 → 定位 → 修复 → 重新测试 → Passed”：

- MySQL 凭据缺失：配置后完成备份、Migration、健康检查、CRUD 和真实任务测试。
- 备份脚本目标路径为空：改为明确的 `--result-file`，并对数据库不存在场景安全跳过 SQL dump。
- MySQL 初始化输入、JSON seed、索引长度：改为客户端 `source`、`JSON_OBJECT` 和前缀索引。
- `Guid` 格式化运行错误：清理全部非法插值格式并重新发布。
- 5 秒默认参数：从 73 frames 修正为 121 frames / 24 FPS，真实输出约 4.96 秒。
- MySQL `TINYINT(1)` 布尔读取错误：修复后锁定/解锁/禁止重新生成回归通过。
- Episode 音频查询排序字段错误：修复后 Episode render Passed。
- 发布目录被运行服务锁定且脚本误报成功：修复退出码检查，停止服务后重新发布并健康回归。
- QA 回炉复用 Seed、缺少增强和再次 QA、已完成任务被误判为活动任务：改为不同 Seed，记录完整回炉元数据，自动执行增强和再次 QA，并只把 Pending/Running 视为活动任务。

## 证据文件

- 安装与闭环日志：`C:\install\install_log.txt`
- 修复记录：`C:\install\AI\VideoStudio\docs\FIX_HISTORY.md`
- QA 汇总：`C:\install\AI\VideoStudio\logs\qa_test_report.json`
- QA 夹具目录：`C:\install\AI\Data\QA\TestCases\20260809_111257`
- 数据库备份：`C:\install\AI\VideoStudio\backup\20260809_100930`

## 长期项目基线接管验收

| 功能 | 状态 | 实际结果 |
|---|---|---|
| 项目规则与状态文档 | Passed | `AGENTS.md`、`PROJECT_STATE.md`、`NEXT_STAGE.md`、`CHANGELOG.md` 已创建/更新，内容按实际代码与运行时核对 |
| 文档一致性 | Passed | 根目录文档改为入口，详细说明统一到 `docs`；旧的“数据库未配置”结论已清除 |
| Git 安全边界 | Passed | `.gitignore` 排除 `config/local.env`、日志、备份、模型、媒体、发布产物和依赖；提交前执行 staged 文件检查 |
| 构建与脚本静态检查 | Passed | .NET 0 警告/0 错误、Vue build Passed、PowerShell AST Passed |
| 生产流水线回归 | Passed | `test_production_pipeline.ps1` health/文件/数据库/5 Shot RuleBased 分析通过；报告位于 `logs\production_pipeline_test.json` |
| QA 夹具回归 | Passed | `qa_test.ps1` 9/9 通过，最新目录为 `C:\install\AI\Data\QA\TestCases\20260809_122530` |

### 接管期间发现并修复

第一次运行生产流水线回归时，`Call-Api` 将 JSON 数组作为单对象返回，导致项目筛选为空并请求 `/api/projects//episodes`，真实结果为 HTTP 404。修复脚本的数组枚举后，重新执行同一回归入口，health、文件、数据库和 5 Shot 分析全部 Passed。此项已写入 `docs\FIX_HISTORY.md`，没有把失败删除或改名。

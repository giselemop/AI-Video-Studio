# AI Video Studio 系统级验收报告

> 验收时间：2026-08-09 23:40 - 2026-08-10 00:12（Asia/Shanghai）\
> 验收环境：Windows 本机；`http://127.0.0.1:18080/`；MySQL 3306；ComfyUI `127.0.0.1:8188`；FFmpeg `C:\install\FFmpeg`；RTX 4070 12GB\
> 角色：产品经理、QA 测试工程师、前端体验与后端架构联合验收

## 1. 最终结论

**本地监督使用：Conditional Go。公网、局域网多人和生产发布：No-Go。**

核心单镜头生产链已经使用真实数据库、真实 ComfyUI、真实 RTX 4070、真实 FFmpeg 和真实 QA 跑通：

`项目 → 角色/场景 → Episode → 剧本拆分 → Prompt → 关键帧 → I2V → 视频增强 → Shot QA → Episode QA → Episode Render → Master/QA 报告`

但系统仍未达到可对外部署的生产级完成标准。未完成项包括认证/RBAC/CSRF、任务幂等与租约、多实例并发保护、LLM 出站地址安全、数据库备份恢复演练和音频完整回归。因此本报告不将项目标记为“全部通过”或“可公网发布”。

## 2. 验收范围与结果

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 服务启动与健康 | Passed | `/api/health` 200；MySQL、ComfyUI、FFmpeg 均在线 |
| ComfyUI/GPU | Passed | ComfyUI 3.13.2；RTX 4070；12,281 MiB 总显存，约 10,980 MiB 空闲 |
| 前端构建 | Passed | `npm run build`；仅有 chunk 体积提示 |
| 后端构建 | Passed | `dotnet build server\VideoStudio.Server.csproj --no-restore --nologo`；0 警告、0 错误 |
| 接口矩阵 | Passed | 18 个健康、Dashboard、CRUD、任务、系统、音频和 QA GET 接口均返回 200 JSON |
| 浏览器导航 | Passed with constraint | 13 个菜单均有主内容、无白屏；同一前端通过 18081 Vite 代理验证 |
| 浏览器刷新恢复 | Passed | `#system` 刷新后仍恢复系统设置页 |
| CRUD 与负向校验 | Passed | 项目/角色/场景/Episode/剧本创建与 PUT；临时角色/场景删除；空项目/空镜头 400 |
| 真实 GPU 生产 | Passed | Keyframe 76、I2V 77、Enhance 78 全部成功 |
| QA 技术夹具 | Passed | `scripts\qa_test.ps1` 9/9 通过 |
| Episode 合成与发布 | Passed after fix | Render 85、QAExport 86 成功；输出与 QA 报告存在 |
| Git 差异检查 | Passed | `git diff --check` 无错误 |

## 3. 真实生产链证据

本次验收保留了可追溯测试夹具：项目 `13`、Episode `11`、Shot `34`，项目名称为 `Acceptance Audit Fixture Updated`。本轮没有删除既有项目；仅删除了专门创建的临时角色和场景删除夹具。

| 步骤 | 任务/结果 | 实际结果 |
| --- | --- | --- |
| 剧本拆分 | Script 3 | RuleBased 分析成功，生成 1 个 Shot；Prompt 生成和版本历史成功 |
| 关键帧 | Task 76 | ComfyUI 成功，关键帧写入 `C:\install\AI\Data\Images\task_76_task_76_00001_.png`，图片 QC 100 |
| I2V | Task 77 | 成功，约 67.6 秒；H.264、512×320、约 4.80 秒；视频 QC 100 |
| 通过视频并增强 | Task 78 | 新增的 `approve-video` 真实生成 Enhance 任务；约 5.8 秒完成 |
| 增强输出 | Task 78 | `C:\install\AI\Data\Output\task_78_1080p.mp4`；1920×1080、30 FPS、H.264；视频 QC 100 |
| Shot QA | Task 79 | 自动 QA 成功，87.30 分，按策略进入 NeedReview，并生成 5 条 Warning |
| Episode QA | Task 80 | 自动 QA 成功，89.58 分；人工复核后 Shot Passed、Episode Approved/locked |
| Episode Render | Task 85 | 成功；`C:\install\AI\Data\Output\验收测试集-UTF8_001.mp4`；1920×1080、30 FPS、4.733 秒 |
| Master 导出 | Task 86 | 成功；Master、`QA_REPORT.md` 和 `QA_REPORT.json` 均存在 |

QA 的 Warning 是当前未加载大型身份/场景/动作视觉模型时的预期人工复核门禁，不是被自动忽略的问题。没有将自动评分直接冒充人工视觉通过。

## 4. 本轮发现并修复的问题

共完成 **10 个缺陷/防护修复项**，均完成构建或真实回归；其中两个问题是在正式成片和导出链路中由真实任务直接暴露的。

| 优先级 | 问题 | 修复 | 复测 |
| --- | --- | --- | --- |
| P1 | Shot 进入 `VideoReview` 后后台没有 Enhance，前端也没有通过按钮 | `approve-video` 创建 CPU Enhance 任务；生产中心增加“通过视频并增强” | Task 78 成功，Shot 变 Completed |
| P1 | Keyframe 可能误使用 I2V 工作流 | 任务读取工作流类型；任务阶段不匹配时回退到正确默认工作流 | Task 76 关键帧成功 |
| P1 | 中文/非法 Episode 名称导致 Windows 输出文件名错误 | Episode Render 使用安全文件名清洗，保留合法中文并替换非法字符 | Task 81 失败后，Task 82/85 成功 |
| P1 | Render 后 `status=Completed` 使已 Approved Episode 无法导出 | 输出更新保留 `qaStatus=Approved + qaLocked`；导出门禁统一读取 QA 状态 | Task 83 失败后，Task 84/86 成功 |
| P1 | CORS 允许任意来源 | 改为仅允许本机 18080/18081 的 localhost 与 127.0.0.1 来源 | Origin 18081 返回精确 Allow-Origin |
| P1 | `/api/media` 可读取 `C:\install\AI` 下 Data 之外文件 | 媒体服务限制到配置的 Data 根目录 | Data 文件 200；server 文件 404 |
| P1 | 未处理异常直接向客户端返回完整异常信息 | 保留服务端日志，客户端改为通用错误和 requestId | 代码构建通过；异常信息不再直接回传 |
| P2 | 刷新后单页工作台回到总览 | 用 URL hash 保存并恢复当前菜单 | `#system` 刷新恢复通过 |
| P2 | 项目/角色/场景/Episode/镜头/剧本空提交依赖后端报错 | 增加前端必填校验 | 空项目即时显示“项目名称不能为空”，不发请求 |
| P2 | 角色和场景删除没有确认 | 增加危险操作确认弹窗 | 删除夹具接口与 UI 路径均通过 |

## 5. QA 与任务结果说明

当前任务表中的历史失败记录被保留，不能简单按 Dashboard 的失败数量判断本轮未修复。此次验收新增的失败是：

- Task 81：修复前 Episode 中文/非法输出文件名失败；修复后 Task 82、85 成功。
- Task 83：修复前 QAExport 读取 production status 而不是 QA status；修复后 Task 84、86 成功。

`qa_test.ps1` 的 9 个夹具全部符合预期：正常视频 Passed、黑帧/短视频/错误分辨率/损坏视频/缺音频/字幕超时 Rejected、时序突变 NeedReview，以及既有真实视频技术检查 Passed。

当前队列没有 Pending 或 Running 任务；历史记录包含 Succeeded、Failed 和 Cancelled，失败夹具没有被删除。

## 6. 尚未闭环的风险

以下项目仍需后续实施，故不能宣称公网或多人生产可用：

| 优先级 | 风险 | 当前状态 |
| --- | --- | --- |
| P0 | 无登录、认证、RBAC、CSRF 防护 | 未完成；服务只绑定 loopback，必须保持本地监督边界 |
| P0 | 任务没有 requestId 幂等键、数据库租约/心跳、原子状态机和多 Worker 防重复执行 | 未完成；当前为单进程内存信号 + 数据库恢复机制 |
| P0 | LLM BaseUrl 出站地址没有完整 allowlist/SSRF 防护 | 未完成；不能把系统暴露到不可信网络 |
| P0 | 数据库迁移、最小权限、备份恢复和故障恢复未在本轮重新演练 | MySQL 在线且本地 CRUD/任务通过，但不等于恢复验收 |
| P1 | TTS、对白、旁白、SRT、SFX/BGM 混音的真实完整闭环 | 仅接口和可用性检查通过；本轮 GPU 夹具无对白、无音频，最终视频 `hasAudio=false` 是测试设计结果 |
| P1 | 角色/场景参考图上传、资产版本、软删除与历史 Shot 复现 | 未做完整回归；严格身份模型/LoRA 当前也未安装 |
| P1 | 多实例、并发、负载和长时间稳定性 | 未验证；当前只证明 RTX 4070 单并发本机链路 |
| P2 | 多数列表缺少搜索、分页和排序；单文件 App.vue 仍需拆分 | 产品能力缺口，不影响本次核心链路，但不满足大型资产库长期使用要求 |
| P2 | 没有独立 .NET 自动化测试项目和完整浏览器 E2E 套件 | 当前依赖真实 API、PowerShell、FFprobe、ComfyUI 和人工浏览器回归 |

## 7. 浏览器验收限制

直接访问目标 `http://127.0.0.1:18080/` 在当前浏览器控制环境被 Chrome/in-app Browser 报 `ERR_BLOCKED_BY_CLIENT`，这不是 Kestrel/API 返回的错误；PowerShell/curl 直接访问静态页和 API 均为 200。为验证修复后的前端，临时启动项目既有的 18081 Vite 代理，将同一 Vue 构建连接到真实 18080 API，完成了 13 菜单、刷新、空表单提示、生产按钮和控制台日志回归。该浏览器限制不能替代真实用户 Chrome 直接打开 18080 的最终环境验收。

## 8. 下一步 Go/No-Go

允许继续：本机单用户、单 GPU、人工复核、可追溯任务和测试夹具范围内使用。

禁止发布：局域网开放、公网部署、多人并发、未认证管理入口、自动无人值守生产。

下一阶段应优先完成 `TASK-P0-SEC-01`、`TASK-01`、`DATA-01` 和 LLM 出站边界，再做音频成片回归、资产版本/恢复和浏览器自动化测试。完成这些后必须重新进行真实链路验收，不能仅凭构建通过关闭本报告。

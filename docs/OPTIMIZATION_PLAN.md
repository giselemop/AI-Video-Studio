# AI Video Studio 安全、架构、可靠性与产品优化方案

> 方案状态：只读证据化规划，证据截止 2026-08-09。\
> 本轮只新增本文件，不执行代码、数据库、配置、工作流、模型或生产媒体变更。\
> 事实以源码、只读运行时探针、只读数据库查询和实际接口返回为准；历史验收文档只证明其中注明的范围。

## 0. 结论先行

当前项目适合在 API 和 ComfyUI 都只监听本机、只有受信任的单一操作者、无外部 LLM 密钥和有可验证备份的前提下继续做受监督的本机研发验收。这个结论不是生产安全证明。

当前安全发布结论：No-Go。原因是 API 对高风险接口没有认证授权和 CSRF 边界，CORS 为任意来源，媒体接口可按客户端绝对路径读取，任务和音频/工作流参数存在客户端路径入口，LLM 配置可指向任意地址并把密钥放入数据库；只读运行时还显示 MySQL 监听地址为通配地址、运行账户为 root@% 且未强制安全传输。

完成 P0 后，可以对“本机单用户、API/ComfyUI 仍为回环地址、数据库与文件目录不对外暴露”的场景给出 Conditional Go。局域网需要额外账户、角色、会话、TLS、CSRF、限流和审计验收；公网在这些条件以及 P1/P2 运维和内容治理完成前仍为 No-Go。

## 1. 当前架构事实表

| 领域 | 当前已确认事实 | 证据 |
|---|---|---|
| 前端 | Vue 3 + Vite + Element Plus；Vite 开发地址为 127.0.0.1:18081，生产静态文件由 ASP.NET 托管；当前入口直接挂载 App，没有 vue-router。 | web\vite.config.js:7-12；web\src\main.js:1-7；server\Program.cs:71-76 |
| API | .NET 8 Minimal API；默认 API 地址为 http://127.0.0.1:18080；健康检查、项目、任务、设置、队列、上传、导出等接口在同一应用内。 | server\VideoStudio.Server.csproj:1-13；server\Program.cs:14-20,78-221 |
| 浏览器安全 | 全局 CORS 使用 AllowAnyOrigin、AllowAnyHeader、AllowAnyMethod；前端 fetch 没有认证或 CSRF 处理。 | server\Program.cs:43-55；web\src\App.vue:72-80 |
| 数据库 | MySQL 是元数据权威源；只读运行时查询为 MySQL 8.0.22、ai_video_studio、34 张表；项目状态记录 schema 34、9 个项目、7 个 Episode、14 个 Shot、15 个资产、43 个成功任务。 | server\Database.cs:140-211,342-386；PROJECT_STATE.md:36-44；2026-08-09 只读数据库探针 |
| 数据库账户 | 当前只读查询显示 root@%，Select/Insert/Update/Delete/Create/Alter/Grant 均为 Y；bind_address 为 *，require_secure_transport 为 OFF。防火墙实际边界本轮未验证。 | config\appsettings.json:1-9；server\Database.cs:25-29,94-125；2026-08-09 只读 MySQL 变量与权限探针 |
| 文件存储 | 数据库保存路径、相对路径和媒体元数据，二进制主要位于 C:\install\AI\Data；Models、Workflows、ComfyUI 输入输出在 C:\install\AI 下。当前 15 个资产路径探测均在 Data 边界内，当前检查的目录没有重解析点，但这不能替代代码级防护。 | database\database.sql:111-136；server\Database.cs:342-356；2026-08-09 只读路径与 reparse-point 探针 |
| 媒体读取 | GET /api/media 接收客户端 path，规范化后只做 C:\install\AI 前缀判断；本轮用非敏感的本地配置文件做了不打印内容的探针，返回 HTTP 200。 | server\Program.cs:170-177,236-239；2026-08-09 只读接口探针 |
| 任务队列 | generation_tasks 存 Pending、Running、Succeeded、Failed、Cancelled 等状态，但表中没有 request/idempotency、租约、心跳、取消请求、状态版本字段；GenerationQueue 使用单进程 Channel 和内存 active 字典。 | database\database.sql:222-255；server\Database.cs:359-386；server\GenerationQueue.cs:8-16,54-117 |
| 任务执行 | ComfyUI 通过 /prompt、/history、/view；GPU 配置并发为 1、最低显存 1024 MiB。CPU 任务和 GPU 任务经过同一个单读者队列，GPU 等待最多约 10 分钟，但单个 Comfy 历史轮询没有总时限。 | docs\COMFYUI_API.md:15-45；config\appsettings.json:19-27；server\GenerationQueue.cs:510-514；server\ComfyUiClient.cs:41-119 |
| AI 配置 | LLM 兼容客户端从数据库读取 BaseUrl 和 API Key，拼接 /chat/completions 并发送 Bearer；设置接口允许客户端写入 BaseUrl 和 API Key。当前运行时 apiKeyConfigured 为 false、没有配置 BaseUrl，但代码风险仍存在。 | server\ScriptAndPromptServices.cs:18-88；server\ProductionEndpoints.cs:213-219；2026-08-09 只读设置探针 |
| 上传 | 参考图、音频和媒体库上传直接使用客户端文件名或扩展名写入 Data 子目录；音频有 300 MB 大小上限和扩展名白名单，但没有统一签名、隔离、病毒扫描或生命周期策略。 | server\Program.cs:121-152；server\ProductionEndpoints.cs:224-237；server\Models.cs:302-308 |
| QA | 现有 QA 能做 FFprobe/FFmpeg 等技术检查，也会产生人物、动作、连续性等启发式分数并要求人工复核；文档明确身份、动作和连续性不能仅由技术检查通过。 | server\VideoQaServices.cs:57-293；docs\质量验收说明.md:5-7,19-59；docs\ACCEPTANCE_REPORT.md:14 |
| 发布 | 现有发布脚本主要执行前端构建和 dotnet publish；前端 package scripts 没有测试、类型检查或浏览器 E2E 命令。本轮没有重新构建，也没有把历史构建通过解释为安全或生产通过。 | scripts\publish.ps1:1-14；web\package.json:6-18；PROJECT_STATE.md:60-78 |
| 运行时 | 2026-08-09 只读健康检查显示 API、MySQL、ComfyUI、FFmpeg 可用，RTX 4070 12 GB 显存空闲约 11 GB；ComfyUI 监听 127.0.0.1:8188，API 监听 127.0.0.1:18080。 | 2026-08-09 只读 /api/health、/system_stats、端口探针；PROJECT_STATE.md:19-34 |

## 2. 证据分级清单

### 2.1 已确认问题

以下问题已由源码或当前运行时直接确认，不代表已经做过攻击性利用：

| 编号 | 问题 |
|---|---|
| SEC-P0-01 | 宽泛 CORS、无认证授权、无 CSRF、高风险接口无独立权限边界。 |
| SEC-P0-02 | /api/media 和多个内部流程信任客户端路径；路径策略分散，存在前缀边界和重解析点设计缺口。 |
| SEC-P0-03 | 任务、参考图、音频、工作流、输出名及部分项目关系由客户端直接绑定，缺少统一归属校验。 |
| SEC-P0-04 | LLM BaseUrl 可任意写入，客户端随后向其发送 Bearer；密钥以 system_settings 明文值保存。 |
| DATA-P0-01 | 启动时创建数据库并执行兼容性结构修改；当前账户和数据库网络边界不满足最小权限假设。 |
| TASK-P0-01 | 领取、运行、完成、失败、恢复没有条件式状态迁移、租约和心跳，唯一执行依赖单进程内存。 |
| TASK-P0-02 | 生产启动、QA、重跑、导出等边界没有业务幂等保护，重复提交可创建重复工作。 |
| MEDIA-P0-03 | 上传、Comfy 下载、FFmpeg/TTS 输出没有统一签名、隔离、资源配额和原子发布策略。 |
| REL-P1-01 | Comfy 历史轮询没有总执行时限、退避、孤儿 prompt 对账和可证明的服务重启恢复。 |
| REL-P1-02 | CPU 与 GPU 任务共用单读者队列，CPU 工作会与 GPU 工作互相阻塞。 |
| MEDIA-P1-03 | 多处直接写最终输出或直接复制到最终路径，数据库与文件系统失败可能留下孤儿或半成品。 |
| DATA-P1-04 | 数据库有基础外键但缺少跨项目/集/Episode/Shot 的组合归属约束、服务端状态约束和 CHECK 约束。 |
| AI-P1-05 | 工作流/模型/输入/Prompt/seed/参数/QA 的完整哈希和版本溯源尚未形成不可变执行记录。 |
| UI-P1-08 | 当前前端没有路由状态恢复和实时任务状态；关键帧操作直接选 candidates[0]。 |

### 2.2 设计风险

这些是已根据源码和业务目标识别出的架构风险或待建设能力，部分尚未在生产负载下证明：

| 编号 | 风险 |
|---|---|
| COST-P1-06 | LLM 没有预算、项目配额、成本记录和熔断；异常重试会扩大成本或延迟。 |
| QA-P1-07 | 技术检测、自动启发式和人工判断已有概念但没有统一的不可绕过门禁和真实验收集。 |
| OPS-P2-01 | 日志不是结构化关联日志，指标、告警、就绪探针和任务/磁盘/GPU 运营闭环不足。 |
| TEST-P2-02 | 没有 .NET 测试项目、浏览器 E2E、状态机并发、路径攻击、迁移恢复和 CI 安全门禁。 |
| ASSET-P2-03 | 资产没有完整版本、软删除、引用计数、保留期、容量上限和可恢复清理模型。 |
| OPS-P2-04 | 构建发布缺少 CI、发布物审计、迁移闸门、回滚和恢复演练链路。 |
| COMP-P2-05 | 内容安全、肖像/声音授权、版权、保留和水印策略未形成产品与运营边界。 |
| PROD-P3-01 | 人物、场景、动作、音频成片仍需要真实验收集和人工标准，当前模型能力不能假设为完成。 |
| DEPLOY-P3-02 | 局域网和公网扩展需要新的身份、网络、TLS、限流、审计、合规和运维条件。 |

### 2.3 尚未验证项

本轮没有把以下事项写成已通过：

- 没有执行迁移、备份或恢复；现有 scripts\backup.ps1 只检查 mysqldump 退出码，备份可读性和恢复演练仍未验证。
- 没有执行真实视频生成、真实 ComfyUI 故障注入、双 worker 并发领取、租约过期或数据库断电恢复。
- 没有执行浏览器 E2E、刷新恢复、响应式、键盘可达性和真实长任务观测。
- 没有用恶意样本验证路径前缀绕过、UNC/设备路径、重解析点、压缩炸弹、伪造扩展名、签名/MIME 不一致或病毒扫描。
- 没有验证外部 LLM 的 DNS/IP 过滤、重定向、超时、响应大小、预算和密钥泄露；当前运行时未配置 API Key。
- 没有验证 FFmpeg/TTS 的进程树终止、内存/磁盘上限和异常输出上限。
- 没有验证真实项目下人物身份、场景连续性、动作语义、音频同步和人工评分一致性。
- 没有重新运行本轮构建；历史构建、管线和 QA 结果仅按 docs\ACCEPTANCE_REPORT.md:18-36,38-44,62-68,84-105 及 PROJECT_STATE.md:60-78 作为历史线索。

## 3. 详细问题与方案卡

每张方案卡都包含触发条件、影响、根因、依赖、回滚和验收；“回滚”指未来执行该项时的安全退回路径，不是本轮已经执行的操作。

### SEC-P0-01：建立本机调用认证与高风险授权边界

- 优先级：P0；类别：已确认问题。
- 证据：server\Program.cs:43-55,78-221；web\src\App.vue:72-80,222-233；server\ProductionEndpoints.cs:213-219；server\QaEndpoints.cs:69-101。当前 CORS 探针在 2026-08-09 返回了 Access-Control-Allow-Origin: *；这不是攻击成功证明，但证实了宽泛中间件。
- 触发条件：任意能访问 API 的本地进程、恶意网页、局域网暴露或浏览器已有会话访问项目控制、设置、删除、导出、队列和重跑接口。
- 影响：未授权读取/修改项目和媒体、跨站请求伪造、删除/覆盖/导出任务、改变 LLM 设置、无审计地解锁或重跑。
- 根因：全局 AllowAnyOrigin；没有账户、会话、权限策略、Origin/CSRF 检查和操作者身份；高风险路由没有独立授权。
- 建议：生产静态站点改为同源；开发仅精确允许 http://127.0.0.1:18081，必要时同时显式登记 localhost 变体，不允许通配符。为本机生成高熵随机启动令牌，一次性配对后换成 HttpOnly、Secure（HTTPS 时）、SameSite=Strict 会话；CLI 使用短期 scoped token。按 Admin、Producer、Reviewer、Viewer 划分设置/扫描/删除/导出/队列/LLM/重跑/审核权限；所有状态改变记录 actor、request_id、resource_id。未来 LAN/公网必须加账户、角色、会话轮换、CSRF、登录限速/锁定、TLS、审计和反向代理。
- 依赖：会话/令牌安全存储、前端请求封装、权限矩阵、审计表、反 CSRF 中间件；本机默认保持 API 只监听回环。
- 回滚：若配对流程故障，关闭高风险接口并保持回环限制，修复后再开；不得以恢复 AllowAnyOrigin 或匿名管理接口作为回滚。
- 验收标准：匿名调用高风险 API 返回 401/403；不同角色权限矩阵全部通过；恶意 Origin 不收到允许头；缺少/错误 CSRF 令牌的状态改变被拒绝；重复/过期会话被拒绝；审计事件包含操作者、请求、资源和结果；启动令牌不进入日志、数据库明文或错误响应。

### SEC-P0-02：把媒体访问和服务器文件读写收敛到资产策略服务

- 优先级：P0；类别：已确认问题。
- 证据：server\Program.cs:170-177；server\GenerationQueue.cs:150-215,431-508,529-536；server\VideoQaServices.cs:428-439；server\Database.cs:342-356；server\ComfyUiClient.cs:86-119。当前 /api/media 接收 path，并对 C:\install\AI 下的配置文件探针返回 HTTP 200。
- 触发条件：请求带入绝对路径、..、相似前缀、UNC/设备路径、Alternate Data Stream、符号链接/ junction，或数据库中保存了非预期路径。
- 影响：读取配置、工作流、模型元数据或其他本机文件；把任意路径传给 FFmpeg/ComfyUI；跨项目资产越权；文件覆盖和信息泄露。
- 根因：路径检查散落在多个服务；StartsWith 缺少统一目录分隔符边界，部分检查只到 C:\install\AI；没有重解析点拒绝、扩展名分级和资产 ID/下载令牌。
- 建议：建立唯一 PathPolicy 服务。所有路径先做全路径规范化，拒绝 UNC、设备路径、NUL、ADS 和未知扩展名，检查 Data 及允许子目录的分隔符边界，逐级检查 reparse point/真实目标，限制最大路径和文件大小。外部接口只接受 asset_id 或短期签名下载令牌；令牌绑定用户、项目、用途、过期时间和一次性/下载次数。工作流、模型、Comfy 输入只能引用目录清单中的 catalog ID。
- 依赖：资产表补充类型/版本/状态，迁移现有路径并生成 manifest；所有上传、下载、FFmpeg、Comfy、QA、导出调用统一收口。
- 回滚：先让旧 path 接口返回 410/受控错误并保留本机管理员诊断命令；若新资产索引不完整，停用生成和导出，不恢复任意路径读取。
- 验收标准：绝对路径、相似前缀、..、UNC、junction、symlink、ADS、未知扩展全部拒绝；只读属于当前项目且状态为 Ready 的资产；下载响应不返回绝对路径；路径策略单元测试和 Windows 实际目录测试通过；数据库现有资产全部能被安全解析或进入隔离待修复清单。

### SEC-P0-03：服务端重建任务输入并验证项目归属

- 优先级：P0；类别：已确认问题。
- 证据：server\Models.cs:5-18,20-50,64-142,302-308；server\Program.cs:181-216,241-249；server\Database.cs:592-615；server\GenerationQueue.cs:150-215,431-508；server\ProductionEndpoints.cs:106-142,172-211。
- 触发条件：客户端修改 ProjectId、EpisodeId、ShotId、WorkflowId、ModelId、InputImagePath、AudioPaths、Parameters、OutputName 或任务类型。
- 影响：跨项目读取/写入、工作流或模型越权、将任意文件交给 AI/FFmpeg、输出覆盖、伪造状态和资源消耗。
- 根因：TaskInput 和 EpisodeRenderInput 可直接绑定客户端字段；Bind 方法没有一致的层级归属校验；Parameters 是任意 JsonElement；多个执行器读取 input_json 中的路径。
- 建议：API 只接收业务实体 ID、受限枚举和结构化 DTO；服务端按 Project→Episode→Shot→Asset 关系重建输入。工作流/模型/LoRA 使用启用且已扫描的 catalog ID；参数按任务类型白名单、范围和组合校验；输出名改成服务端生成的任务/资产键。拒绝客户端提交绝对路径、执行命令和任意节点 JSON。
- 依赖：SEC-P0-02 的 PathPolicy、DATA-P1-04 的关系约束、任务输入 schema 版本化。
- 回滚：保留旧字段只作为内部迁移读取，外部字段先拒绝；发现兼容性问题时只放开明确的本机调试开关，不放开生产接口。
- 验收标准：跨项目 ID 组合返回 400/403；不在 catalog 的工作流/模型返回 409；越界参数、未知字段、路径和输出名被拒绝；同一个合法任务的服务端生成输入可审计且不含绝对客户端路径。

### SEC-P0-04：限制 LLM 出站地址并迁移密钥安全存储

- 优先级：P0；类别：已确认问题。
- 证据：server\ProductionEndpoints.cs:213-219；server\ScriptAndPromptServices.cs:18-88,91-123；server\Database.cs:543-545；database\database.sql:296-306。当前运行时 LLM 设置探针显示 apiKeyConfigured=false、没有配置 BaseUrl；风险来自可执行代码路径而不是当前密钥存在。
- 触发条件：管理员或被伪造的请求把 BaseUrl 指向内网、回环、云元数据、文件协议、恶意重定向或攻击者服务器。
- 影响：SSRF、内网探测、向错误地址发送 Bearer Token、密钥泄露、无控制外部费用。
- 根因：客户端可写 BaseUrl；HttpClient 直接拼接 /chat/completions；没有 HTTPS/主机白名单、DNS/IP 过滤、重定向限制、请求/响应大小和出站审计。
- 建议：Provider 采用固定枚举和已审核 endpoint catalog；默认只允许 HTTPS 或明确登记的本机回环服务。解析 DNS 后拒绝私网、回环、链路本地、保留和云元数据地址，除非是显式的本机 provider；禁用自动重定向，设置连接/总超时、请求/响应字节上限和仅 POST 的路径；密钥只发往已批准的 host。密钥从 system_settings 明文值迁移到 Windows DPAPI/Credential Manager 或不跟踪的本机受保护文件，数据库只存 provider、host、key fingerprint 和配置版本。
- 依赖：SEC-P0-01 的管理员授权、秘密迁移工具、出站 DNS/IP 校验、预算策略 COST-P1-06。
- 回滚：迁移失败时保持 LLM disabled，保留旧配置的加密备份供人工恢复；不得把明文密钥重新写回生产数据库。
- 验收标准：非 allowlist、HTTP、重定向、私网/元数据地址均被拒绝；密钥不出现在数据库查询、日志、异常和客户端响应；模拟 provider 能通过，超时/大响应/连续失败触发熔断；迁移后仅指纹和脱敏状态可见。

### DATA-P0-01：停止启动时隐式改生产 Schema，降低数据库权限和网络暴露

- 优先级：P0；类别：已确认问题。
- 证据：server\Program.cs:45-53；server\Database.cs:627-671；server\ProductionSchemaMigrator.cs:7-67；server\VideoQaSchemaMigrator.cs:12-65；scripts\init_database.ps1:1-28；scripts\backup.ps1:15-44；config\appsettings.json:1-9；2026-08-09 只读探针显示 root@%、bind_address=*、require_secure_transport=OFF。
- 触发条件：应用启动、升级、数据库版本不一致、应用账户拥有 DDL，或数据库端口被非本机访问。
- 影响：无备份前置的结构改变、启动竞争、部分迁移和难以回滚；root 权限扩大应用入侵后果；通配监听和未强制安全传输扩大网络风险。
- 根因：DatabaseInitializer 在启动创建数据库并执行 SQL/兼容性 ALTER；迁移脚本与运行时职责混合；默认用户 root；备份脚本只检查 dump 退出码，未验证可读/可恢复。
- 建议：拆出显式迁移命令和迁移清单，记录 version/checksum/applied_by/backup_id；迁移前必须通过数据库存在性、空间、锁、备份可读性和恢复演练前置检查。迁移账户拥有 DDL，运行账户只给目标库所需 SELECT/INSERT/UPDATE/DELETE/EXECUTE；禁止 root 运行应用。MySQL 仅监听回环（或明确受控网段），启用 TLS/require_secure_transport，防火墙拒绝非目标来源。
- 依赖：数据库备份目标、维护窗口、应用账户切换、迁移脚本清单、恢复演练。
- 回滚：采用向前修复优先；若迁移失败，停止应用、保留现场、用已验证备份恢复数据库和文件 manifest，再按版本重放；不以 DROP/清库或自动反向 ALTER 作为默认回滚。
- 验收标准：应用启动只读校验 schema，不执行 CREATE/ALTER；运行账户无法 CREATE/ALTER/GRANT；迁移在锁和校验和不匹配时停止；备份能在隔离实例读取并恢复抽样关系；非本机数据库连接被拒绝或仅允许明确的管理来源。

### TASK-P0-01：建立数据库权威的可恢复任务状态机

- 优先级：P0；类别：已确认问题。
- 证据：database\database.sql:222-255；server\Database.cs:368-386；server\GenerationQueue.cs:13-16,54-117,119-146。RecoverRunningTasksAsync、MarkTaskRunningAsync 和 MarkTaskAsync 当前没有 expected state、lease owner 或 state version 条件。
- 触发条件：两个 worker 同时启动/恢复、进程崩溃、网络断开、ComfyUI 重启、重复消息、取消与完成竞态。
- 影响：同一任务重复执行、完成结果被失败/取消覆盖、任务永久 Running、数据库与 Comfy prompt 不一致、不可审计恢复。
- 根因：Channel 只负责单进程唤醒；领取是先读 Pending 后无条件更新；active 字典是进程内存；状态字段没有租约和版本。
- 建议：状态设计为 Pending → Claimed → Running → Succeeded/Failed/Cancelled/TimedOut。generation_tasks 增加 request_id、idempotency_key、business_key、state_version、lease_owner、lease_expires_at、heartbeat_at、cancel_requested_at、claimed_at、deadline_at、timed_out_at、failure_code。使用 MySQL 事务和行锁/SELECT FOR UPDATE SKIP LOCKED，或带 state/status/version 条件的原子 UPDATE；只有 lease owner 能心跳和完成；过期租约由恢复器重入 Pending 或按 deadline 进入 TimedOut。所有迁移写 task_events/operation_logs。
- 依赖：DATA-P0-01 的迁移、TASK-P0-02 幂等表、Comfy prompt 对账、持久化 worker 标识。
- 回滚：先双写事件和新字段、旧执行器只消费明确兼容状态；新状态机异常时停止 worker 并保留 DB 状态，不直接批量重置 Running。
- 验收标准：两个并发 worker 只能一个获得同一任务；失联租约能在到期后恢复且不重复发布最终结果；非法前序完成/取消/失败返回冲突；已终态不可被覆盖；重启后 Pending/过期 Running 可恢复，审计包含每次状态转移。

### TASK-P0-02：为生产、QA、重跑和导出建立业务幂等边界

- 优先级：P0；类别：已确认问题。
- 证据：server\ProductionEndpoints.cs:106-142,87-104,148-211；server\QaEndpoints.cs:32-51,53-67,104-138；server\GenerationQueue.cs:324-411；server\Database.cs:490-516,539-545。
- 触发条件：浏览器双击、刷新重试、网络超时后重发、worker 恢复、用户同时点击开始/重跑/导出。
- 影响：重复 production_run、重复候选和 I2V、重复 QA/导出、覆盖状态、重复扣费/耗时和磁盘膨胀。
- 根因：接口直接创建任务或更新状态，没有 request_id 唯一约束、业务键、提交指纹和条件更新；部分 active 检查只看 Pending/Running。
- 建议：所有状态改变接收客户端 request_id，由服务端生成/校验幂等键；数据库建立唯一业务键。建议键包括 episode + stage + shot + input fingerprint + workflow/model version + desired output profile；生产开始、关键帧 I2V、增强、QA、音频、Episode render、export、retry 分别定义 stage。相同键相同 payload 返回原结果，不同 payload 返回 409；重试新建 attempt，但关联原任务和原因。
- 依赖：TASK-P0-01 状态版本、AI-P1-05 输入指纹、前端请求封装和冲突提示。
- 回滚：新幂等记录只增加数据；发现误合并时禁止删除历史，停用该 stage 的自动提交并人工核查，按新 business key 继续。
- 验收标准：相同 request_id 重发只产生一个任务/一次 run；相同业务键返回同一 task/result；不同参数得到明确冲突；并发 start、QA、export、retry 测试没有重复输出或终态覆盖。

### MEDIA-P0-03：统一媒体验证、隔离、配额和生命周期

- 优先级：P0；类别：已确认问题。
- 证据：server\Program.cs:121-152；server\ProductionEndpoints.cs:224-237；server\ComfyUiClient.cs:86-119；server\FfmpegService.cs:154-164；server\MediaProductionServices.cs:62-184；database\database.sql:111-136。
- 触发条件：伪造扩展名、超大图片/音频、畸形媒体、ComfyUI 返回异常文件、FFmpeg 输出异常、同一项目大量上传或任务失败后重试。
- 影响：解析器漏洞、资源耗尽、恶意文件落入工作流、半成品被当作可用资产、磁盘无限增长。
- 根因：不同入口分别用扩展名、File.Exists、FFprobe 或客户端文件名判断；没有 quarantine 状态、统一签名/MIME/FFprobe、病毒扫描、项目配额和清理器。
- 建议：上传和外部下载先进入 task/asset quarantine 目录，随机服务端文件名；验证魔数、MIME、扩展名一致性、FFprobe 时长/分辨率/FPS/帧数/声道/编码，按文件类型设大小和时长上限。可用时接入本机 AV/隔离扫描；扫描前不进入 Comfy 输入和用户下载。按项目、用户、任务类型和全局磁盘设置配额，维护保留期、软删除和清理审计。
- 依赖：PathPolicy、资产版本表、磁盘门禁、AV 选择、MediaInfo/FFprobe 夹具。
- 回滚：新入口灰度期间发现误拒绝时只调整白名单/阈值，不退回原始文件名和任意路径；隔离区可人工恢复但不直接覆盖已发布资产。
- 验收标准：扩展名与签名不一致拒绝；超限在解析前拒绝；Quarantine 资产不能被 API/Comfy/FFmpeg 使用；所有可用资产有校验摘要和探测元数据；配额达到硬门禁；任务取消和失败后孤儿可枚举、可恢复清理。

### REL-P1-01：为 ComfyUI 增加时限、退避、心跳和孤儿对账

- 优先级：P1；类别：已确认问题。
- 证据：server\ComfyUiClient.cs:41-119；server\GenerationQueue.cs:150-215,510-514；docs\COMFYUI_API.md:15-45。
- 触发条件：ComfyUI 不响应、/history 没有 prompt、服务重启、GPU OOM、下载中断、任务进程崩溃。
- 影响：worker 长时间占用、任务卡 Running、队列误判、旧 prompt 输出污染新任务、磁盘孤儿。
- 根因：WaitForHistoryAsync 只受外部 CancellationToken 控制，没有任务总 deadline、指数退避或 prompt owner 校验；队列只在进程启动时简单恢复 Running。
- 建议：提交设置连接/提交超时；按任务类型设置总 deadline 和 GPU 等待 deadline；轮询采用 1、2、4、8 秒上限退避并记录 heartbeat；保存 prompt_id、client_id、workflow fingerprint 和提交时间。启动和定时对账 /queue、/history、任务表，识别没有 DB owner 的 prompt 和没有 Comfy prompt 的 Running 任务；服务重启后只按 lease/deadline 恢复，下载输出必须再次按 task fingerprint 验证。
- 依赖：TASK-P0-01 租约、MEDIA-P1-03 临时目录、Comfy fixture 和服务重启测试。
- 回滚：若对账器误判，只停止自动回收并把任务标为 NeedsReconcile，不删除 Comfy 历史或生产文件；人工确认后恢复。
- 验收标准：提交、轮询、下载各自有超时；挂起 prompt 最终进入 TimedOut 或可恢复状态；重启后不会重复发布同一结果；孤儿 prompt/文件有清单和告警；退避下的请求量和心跳可观测。

### REL-P1-02：拆分 GPU/CPU 队列并实行有界背压

- 优先级：P1；类别：已确认问题。
- 证据：server\GenerationQueue.cs:8-16,54-117；config\appsettings.json:19-27；PROJECT_STATE.md:19-34。
- 触发条件：生成任务等待 GPU 时同时提交 TTS、字幕、QA、FFmpeg，或大量任务积压。
- 影响：CPU 任务被 GPU 等待阻塞，GPU/CPU/磁盘负载不可控，用户无法判断队列位置，失败重试形成雪崩。
- 根因：一个单读者 Channel 承载不同资源类；Concurrency=1；CPU 任务没有独立容量和磁盘门禁。
- 建议：持久化任务仍由数据库领取，内存信号只负责唤醒。GPU worker 固定并发 1；以 i5-13600KF、32 GB、RTX 4070 12 GB 为起始建议，TTS/字幕等轻 CPU 并发 2，FFmpeg/技术 QA 并发 1，磁盘密集型合成并发 1，实际压测后再调；每个池有队列上限、项目配额、显存门禁、磁盘门禁和公平策略。建议保留现有 GPU MinFreeVramMiB 1024 作为初始保护值，按 OOM 数据调整。
- 依赖：TASK-P0-01、磁盘/显存指标、真实本机压力测试。
- 回滚：池化异常时将新提交置 Pending 并停止 worker，不自动把所有任务合并回单队列；保留 GPU=1 的安全模式。
- 验收标准：GPU 同时运行数恒为 1；CPU 池不会被 GPU 阻塞；满载时提交得到可解释的 429/排队结果；内存、显存、磁盘没有持续单调增长；队列位置和预计时间可以查询。

### MEDIA-P1-03：临时目录、验证后原子发布和文件/数据库补偿

- 优先级：P1；类别：已确认问题。
- 证据：server\GenerationQueue.cs:150-215,431-501；server\ComfyUiClient.cs:86-119；server\FfmpegService.cs:69-151；server\VideoQaServices.cs:296-337。
- 触发条件：下载成功但 DB 写入失败、DB 成功但移动失败、进程在写文件时退出、取消发生在转换或导出中。
- 影响：用户看到不完整视频、数据库指向不存在文件、最终目录出现未登记输出、重跑覆盖旧结果。
- 根因：Comfy download、Enhance、EpisodeRender、ExportMaster 等路径直接创建或复制到最终位置；事务不能覆盖文件系统。
- 建议：每个任务创建 Data\Temp\{task-id} 隔离目录，使用随机文件名；下载和 FFmpeg 输出先 fsync/关闭，再做签名和 FFprobe 验证；登记 immutable manifest 后用同卷原子 MoveFile 发布到版本目录；数据库事务只登记 manifest/asset/result。加入 outbox/reconciler：DB 记录发布意图、文件清单和 checksum，定时对账缺失、未登记和过期临时文件；取消/失败走可追踪清理而非盲删。
- 依赖：资产版本、PathPolicy、任务事件、备份 manifest。
- 回滚：发布失败保留临时目录和事件，标记 PublishPending/Orphaned；人工或清理器确认后回收，禁止覆盖已发布版本。
- 验收标准：在下载、验证、DB commit、原子移动每个故障点注入退出；已发布文件要么有完整 DB 记录要么进入可见对账清单；重复发布不覆盖版本；恢复器可安全重试或清理。

### DATA-P1-04：补齐层级归属、服务端约束和一致性校验

- 优先级：P1；类别：已确认问题。
- 证据：database\database.sql:22-40,111-136,183-255；server\Database.cs:247-356,592-615；2026-08-09 只读聚合检查当前 project/episode/shot/task/QA 归属不一致为 0，但这是当前数据状态而不是保护证明。
- 触发条件：客户端组合不同项目的 IDs、删除父实体、状态越级、写入负尺寸/异常 FPS/过大帧数、并发更新。
- 影响：跨项目资产和任务污染、删除后悬挂引用、无效媒体消耗 GPU、QA/导出引用错误结果。
- 根因：已有单列 FK 不能表达多列同归属；应用 Bind 逻辑分散；数据库没有足够 CHECK/状态约束，部分删除是硬删除。
- 建议：服务端所有写操作先执行层级归属查询；对 Project/Episode/Shot/Asset/Task/Result/QA 使用复合唯一键或触发器/约束策略表达同项目关系；补充状态、尺寸、FPS、帧数、文件大小、重试次数的数据库和 DTO 双层约束。先以报告模式扫描并修复历史不一致，再逐步启用约束。
- 依赖：DATA-P0-01 的显式迁移、历史数据审计、资产版本设计。
- 回滚：约束先以拒绝新写入和报告模式灰度；发现历史数据问题时暂停硬约束并修复数据，不删除行。
- 验收标准：所有跨层级组合在 API 和数据库层均被拒绝；负值/超限值不能落库；父级删除不会留下不可解释结果；并发更新有版本冲突；现有数据扫描报告可复现且归零。

### AI-P1-05：建立可复现的模型、工作流、输入和结果溯源

- 优先级：P1；类别：已确认问题。
- 证据：server\WorkflowCatalog.cs:19-85；database\database.sql:138-181,222-269；server\Database.cs:359-366,389-395；server\GenerationQueue.cs:150-215；docs\COMFYUI_API.md:35-45。
- 触发条件：工作流/模型文件被替换、任务重试、多人改 Prompt、模型节点版本变化、QA 需要解释结果。
- 影响：无法复现实验、无法定位质量回退、许可证/来源不明、重试结果无法比较。
- 根因：catalog 主要登记路径和名称；models 的 sha256 字段没有由 UpsertModelAsync 完整填充；任务 JSON 没有不可变版本和完整资产摘要。
- 建议：为工作流、模型、LoRA、节点清单记录 SHA-256、大小、来源、许可证、版本和扫描时间；任务冻结 Prompt、负面 Prompt、seed、采样器、尺寸、帧数、CFG、steps、运行时版本、GPU、参考资产/版本和输入摘要；结果记录输出摘要、QA 版本/分数和人工意见。缺失版本或许可证信息的实体只能进入隔离/实验状态。
- 依赖：资产版本、catalog 扫描、任务输入 schema、发布物清单。
- 回滚：新溯源字段可追加；旧任务标记 legacy/不可复现，不伪造缺失值。
- 验收标准：给定任务能生成完整 manifest；同一 fixture 的输入摘要、工作流和参数可比较；模型/工作流哈希变化会产生新版本而不是覆盖旧记录；导出报告含溯源和许可证状态。

### COST-P1-06：为外部 LLM 加入预算、大小边界、重试和熔断

- 优先级：P1；类别：设计风险。
- 证据：server\ScriptAndPromptServices.cs:18-123；server\ProductionEndpoints.cs:213-219；server\Models.cs:256-264。MaxTokens 虽有 256-16000 的配置夹取，但输入脚本和请求体没有项目/请求级预算。
- 触发条件：脚本过长、连接超时、429/5xx、用户重复分析、Provider 异常或密钥误配。
- 影响：外部费用失控、长时间占用、重复请求、敏感内容向外部传输、LLM 失败被本地规则误认为同等质量。
- 根因：没有 token 预估、预算台账、指数退避上限、按错误类型分类和熔断；异常只记录文字。
- 建议：按 provider、项目、用户、日/月设预算与最大请求次数；输入字符/估算 token、输出 token、单请求时限和响应大小上限；只对可重试错误做有上限的指数退避，429 遵守 Retry-After；连续失败熔断并回退到明确标记的本地规则；日志只记 request_id、模型、token/cost 摘要，不记密钥和完整敏感脚本。
- 依赖：SEC-P0-04、权限和项目配额、provider 价格配置；测试使用本机 stub，不付费。
- 回滚：超预算时保持 LLM disabled 或本地规则，不能绕过预算直接重试。
- 验收标准：超长输入、超预算、429、5xx、慢响应均有可见状态；成本/令牌台账可按项目查询；熔断后不继续出站；本机 stub 回归不依赖外部付费服务。

### QA-P1-07：建立不伪装质量的技术、自动和人工三道门

- 优先级：P1；类别：设计风险。
- 证据：server\VideoQaServices.cs:57-293；server\QaEndpoints.cs:32-138；docs\质量验收说明.md:5-7,19-59；docs\ACCEPTANCE_REPORT.md:14。
- 触发条件：技术指标达标但人物变脸、场景跳变、动作不符合、音频不同步，或自动分数与人工判断冲突。
- 影响：低质量视频被错误标记 Passed，回炉成本延后，产品对“生成成功”的承诺失真。
- 根因：技术检查、启发式分数和 manual 标记在同一流水线中；没有固定验收集、评分者一致性和不可绕过的人工 gate。
- 建议：状态分离为 TechnicalPassed、AutoScored、NeedHumanReview、Approved/Rejected；技术层只判断文件完整性、编码、时长、FPS、音频轨道等。自动层报告身份/动作/连续性候选分数与置信度，不替代人工。建立版本化验收集：人物一致性逐镜对比参考，场景一致性检查主体/背景/光照/道具，动作标准按镜头意图和时间段评分，音频成片检查清晰度、响度、对白/画面同步、音乐/音效遮挡；记录评分者、依据、分歧和回炉原因。
- 依赖：AI-P1-05 溯源、UI-P1-08 审核体验、真实素材和人工评审资源。
- 回滚：自动评分异常时将结果降级为 NeedHumanReview，不自动批准、不删除原候选。
- 验收标准：技术通过不能直接绕过人工门；代表性验收集有盲评结果、评分标准和失败样例；身份、动作、连续性、音频分别可追踪；报告明确区分技术通过、自动建议和人工批准。

### UI-P1-08：让关键选择、长任务和危险动作可恢复且可理解

- 优先级：P1；类别：已确认问题。
- 证据：web\src\main.js:1-7；web\src\App.vue:5-30,83-169,222-233；web\package.json:6-18。关键帧函数将候选列表直接取 candidates[0]；当前没有 router、SSE/WebSocket 或合理的自动轮询。
- 触发条件：刷新、关闭标签页、网络短断、多个候选、长任务、删除/覆盖/解锁/导出操作。
- 影响：用户丢失项目/Episode/Shot 选择，不知道任务是否仍在运行，误选关键帧，重复点击和误删除。
- 根因：状态只在 App 内存 ref；状态更新主要依赖手动 refresh；危险动作的后端权限和前端影响说明不成体系。
- 建议：按路由和功能拆包，使用 URL + 本地安全状态保存 project/episode/shot/asset selection；增加 SSE/WebSocket 或带退避的轮询，显示状态、队列位置、租约/预计时间、失败原因和“重试会产生新 attempt”的提示。关键帧必须显示候选缩略图、技术分数和人工选择按钮，不自动提交第一张。删除、覆盖、重新生成、解锁、导出显示影响范围并要求确认，后端再次校验权限、版本和幂等键。
- 依赖：SEC-P0-01、TASK-P0-01/02、QA-P1-07、浏览器 E2E。
- 回滚：实时推送失败时使用有限轮询；状态恢复失败时保留 URL 参数和服务端当前选择，不重置为第一项。
- 验收标准：刷新和重新登录后可继续查看同一资源；候选未明确选择不能生成 I2V；重复点击不重复任务；危险操作显示资源、版本和可逆性；移动端、键盘和错误/空态通过浏览器验收。

### OPS-P2-01：建立结构化可观测性和运营告警

- 优先级：P2；类别：设计风险。
- 证据：server\FileLogger.cs:5-41；server\Program.cs:56-69,78-83；server\Database.cs:387-387；config\appsettings.json:19-27。
- 触发条件：任务长时间等待、ComfyUI 失联、磁盘不足、显存不足、数据库慢、失败率上升或重复任务激增。
- 影响：无法按请求/任务追踪故障，健康检查只告诉“在线”，无法及时止损。
- 根因：文本文件日志无统一 request/correlation/task context；健康接口未分离 liveness/readiness；没有队列、资源、失败率和重复率指标。
- 建议：统一结构化日志字段 timestamp、level、request_id、task_id、project_id、stage、worker_id、duration、status、error_code；敏感字段脱敏。增加 liveness/readiness、DB/Comfy/FFmpeg/磁盘/显存指标和任务状态计数；告警包括积压、租约超时、OOM、Comfy 无响应、磁盘警戒/硬门禁、连续失败、重复 business key 和备份过期。
- 依赖：任务事件、队列池、部署目标和告警接收渠道。
- 回滚：新指标旁路写出；日志格式切换失败时保留本地日志，但不恢复秘密和完整 Prompt 输出。
- 验收标准：任意任务可从 API 请求关联到 worker、Comfy prompt、输出 manifest 和 QA；readiness 在依赖不可用时失败；模拟阈值能触发并消除告警。

### TEST-P2-02：建立覆盖安全、并发、媒体、迁移和浏览器的 CI

- 优先级：P2；类别：设计风险。
- 证据：server\VideoStudio.Server.csproj:1-13；web\package.json:6-18；scripts\test_production_pipeline.ps1:1-95；scripts\qa_test.ps1:1-74；scripts\publish.ps1:1-14；PROJECT_STATE.md:72-78。
- 触发条件：提交代码、依赖更新、数据库迁移、工作流/模型 catalog 变更、发布前。
- 影响：构建通过但安全、并发、恢复、浏览器和真实媒体行为未被发现。
- 根因：没有 .NET test project、浏览器 E2E 命令和 CI 安全门；现有脚本偏向本机验收且真实生成默认跳过。
- 建议：建立 .NET 单元测试与 MySQL 集成测试；状态机双 worker/lease/取消竞态；路径边界和 reparse；上传签名/MIME/配额；迁移升级/失败/回滚；FFmpeg/Comfy stub 和挂起/重启夹具；LLM mock/SSRF；浏览器 Playwright 覆盖登录、刷新恢复、候选选择、危险操作和响应式/键盘。CI 依次执行 restore/build/typecheck/test/format、依赖漏洞、秘密扫描、生成物清单和迁移 dry-run；真实生成放在受控本机 acceptance，不向 CI 发付费请求。
- 依赖：测试数据隔离、容器或临时 MySQL、Comfy/FFmpeg 夹具、P0 接口稳定。
- 回滚：CI 新门禁先以报告模式收集，再按 P0/P1 风险逐项设为阻断；生产发布不因临时跳过测试而自动继续。
- 验收标准：主分支合并必须通过上述门禁；失败提供 artifact 和关联 ID；秘密扫描不输出秘密；浏览器 E2E 在干净数据库可重复；迁移测试验证备份前置和恢复路径。

### ASSET-P2-03：引入资产版本、引用计数、软删除和可恢复清理

- 优先级：P2；类别：设计风险。
- 证据：database\database.sql:111-136,257-269；server\Database.cs:342-356,247-265；server\GenerationQueue.cs:431-501；server\VideoQaServices.cs:296-337。
- 触发条件：重新生成、覆盖、删除项目/Shot、导出发布、任务失败或用户要求删除。
- 影响：旧版本被覆盖、QA/结果引用断裂、无法恢复误删、Data 无上限增长。
- 根因：assets 以路径/哈希登记但没有 parent/version/status/deleted_at/retention_until；部分实体硬删除；文件清理不受引用和审计控制。
- 建议：资产使用 immutable content record + logical asset/version；结果、候选、QA、导出均引用版本；增加 soft_deleted_at、retention_until、ref_count/可重算引用关系、quarantine/ready/published/expired 状态；清理器先生成候选清单、等待保护期、再次对账后移动到回收区，再物理清理并记录事件。设置全局和项目容量上限。
- 依赖：MEDIA-P0-03、MEDIA-P1-03、备份 manifest、用户保留政策。
- 回滚：只恢复 soft delete/回收区索引，不直接恢复被物理清理文件；所有清理前保留 manifest。
- 验收标准：重跑保留旧版本；被引用版本不能清理；软删除可恢复；到期孤儿经过两次对账后才可清理；容量门禁和清理事件可查询。

### OPS-P2-04：建立发布、迁移、备份和回滚闸门

- 优先级：P2；类别：设计风险。
- 证据：scripts\publish.ps1:1-14；scripts\backup.ps1:15-44；scripts\init_database.ps1:1-28；PROJECT_STATE.md:46-56。
- 触发条件：发布新服务/前端、升级数据库、替换模型/工作流或改变任务状态机。
- 影响：新旧 schema/worker 不兼容，失败时无法快速恢复，发布物和外部模型不可追溯。
- 根因：发布脚本没有 CI、artifact 签名/清单、迁移前置 gate、canary、版本化配置和回滚演练。
- 建议：每个发布生成服务/前端/迁移/工作流 catalog manifest 和版本；先备份并验证，再以兼容顺序部署；数据库迁移与应用分开；本机单用户可使用停机发布，LAN/公网增加反向代理、健康闸门、canary、保留上一版本和一键停写/回滚 runbook。工作流/模型替换必须有 hash、许可证和回退版本。
- 依赖：DATA-P0-01、TEST-P2-02、备份目标和维护窗口。
- 回滚：默认回到上一应用版本并向前修复 schema；仅在恢复演练证明可行且获批准时恢复数据库快照和对应文件 manifest。
- 验收标准：发布前没有备份/校验和/健康 gate 就不能继续；失败能在演练目标时间内恢复到上一可用版本；发布报告能区分本机验证、外部依赖和未验证项。

### COMP-P2-05：把内容安全、授权、版权和数据治理写成产品边界

- 优先级：P2；类别：设计风险。
- 证据：docs\质量验收说明.md:5-7,45-59；docs\ACCEPTANCE_REPORT.md:14；server\ProductionEndpoints.cs:224-237；database\database.sql:296-306。源码中本轮未找到可证明的授权、版权、内容审核、保留和水印闭环。
- 触发条件：上传真人肖像/声音、使用第三方素材/模型、生成含敏感内容、导出或分享给外部用户。
- 影响：侵权、未经授权的肖像/声音使用、隐私泄露、滥用内容上线、删除请求无法执行。
- 根因：本地研发管线默认信任输入，缺少 consent/license 元数据、审核状态、审计留存和发布前水印/来源策略。
- 建议：本机版明确“操作者负责权利与授权，默认不外发、不上传第三方 LLM”；资产登记来源、授权范围、到期时间和处理同意。公网版增加内容分类/人工升级审核、肖像与声音 consent、版权/模型许可证、可见水印或 provenance、举报/下架、保留/删除/导出流程和审计。未经人工批准的内容不得标为公开发布。
- 依赖：目标用户/地区法律要求、外部审核或扫描服务、发布渠道和水印策略。
- 回滚：新治理字段不阻塞本机实验资产时标为 Experimental；公网发布功能保持关闭，不能通过删除审核字段绕过。
- 验收标准：每个公开资产能追溯来源和授权；缺失授权、过期授权和未审核内容不能导出公开包；删除请求能找到数据库记录、文件版本、缓存和日志；水印/provenance 可验证。

### PROD-P3-01：把人物、场景、动作和音频能力按真实验收集推进

- 优先级：P3；类别：设计风险/产品能力。
- 证据：docs\COMFYUI_API.md:35-45；NEXT_STAGE.md:13-17,78-80；docs\质量验收说明.md:19-43；PROJECT_STATE.md:46-56,72-78。
- 触发条件：需要连续镜头、固定角色、复杂动作、对白和音乐成片，而当前流程只有基础参考图/I2V、技术 QA 和人工检查。
- 影响：产品承诺超过模型/工作流实际能力，返工、人工成本和用户预期风险上升。
- 根因：当前没有已验收的 IP-Adapter/ControlNet/LoRA 能力，LoRA 记录为 0；身份、场景、动作、音频指标没有版本化验收集。
- 建议：先定义四类真实验收集和人工 1-5 评分/硬失败样例，再分别评估参考图策略、人物/场景 embedding 或控制节点、动作控制、TTS/对白/音乐/混音。每种新模型/工作流必须在 4070/12 GB 门禁下做小样本、可回退实验；不把新能力设为默认，直到通过身份、场景、动作、音频四组门槛。
- 依赖：AI-P1-05 溯源、QA-P1-07 人工资源、模型/节点许可证、真实素材。
- 回滚：新工作流以实验 catalog 状态发布，失败时回到已验收 SD1.5/LTX2B FP8 路径，不改写旧结果。
- 验收标准：四类验收集分别达到经用户确认的阈值；失败原因可定位到模型/Prompt/控制/音频步骤；同一参考资产的多镜头结果可复现比较。

### DEPLOY-P3-02：在扩大监听地址前完成分层部署条件

- 优先级：P3；类别：设计风险。
- 证据：config\appsettings.json:1-27；server\Program.cs:14-20,78-83；docs\ARCHITECTURE.md:14-31；2026-08-09 端口探针。当前 API/ComfyUI 为回环监听，但 MySQL bind_address 为 *，公网条件和防火墙状态未验证。
- 触发条件：把 API、Vite、ComfyUI 或数据库监听改为局域网/公网，或开放远程 worker。
- 影响：未授权生成/下载/删除、凭据泄露、GPU/磁盘 DoS、数据库被直接访问。
- 根因：当前架构是本机单用户假设，没有远程身份、TLS、反向代理、worker mTLS、限流和审计；“能监听”不等于“能安全发布”。
- 建议：本机：API/ComfyUI/MySQL 仅回环，浏览器通过同源或精确 Vite origin；局域网：API 仅受控网段、TLS、账户/RBAC/CSRF、速率与配额、ComfyUI/DB 不直接暴露；公网：反向代理/WAF、强身份、密钥轮换、隔离 worker、备份/恢复/监控/内容治理和渗透测试。任何层级都先通过 P0 安全闸门。
- 依赖：SEC-P0-01~04、DATA-P0-01、OPS-P2-01/04、合规与网络条件。
- 回滚：默认保持回环监听；远程试验只在隔离网络和临时 allowlist 中启用，发生异常立即撤销网络规则，不扩大应用匿名权限。
- 验收标准：部署矩阵逐项签字；未满足条件不能改监听地址；远程请求通过身份、权限、CSRF、限流和审计测试；数据库和 ComfyUI 在外部扫描中不可直接访问。

## 4. 目标安全边界

### 4.1 分层边界

~~~mermaid
flowchart LR
    Browser["同源静态站点或精确允许的本机 Vite"] --> Session["本机配对令牌 / HttpOnly 会话 / CSRF"]
    Future["未来局域网或公网"] -. "默认关闭" .-> Gateway["TLS / 账户 / RBAC / 限流 / 审计"]
    Session --> API["API 边界"]
    Gateway --> API
    API --> Policy["PathPolicy / Asset ID / 下载令牌"]
    Policy --> Data["Data 受控子目录"]
    API --> DB["MySQL 最小权限运行账户"]
    API --> Queue["数据库权威任务状态 / 幂等"]
    Queue --> GPU["GPU worker，租约并发 1"]
    Queue --> CPU["CPU worker 池，有界并发"]
    GPU --> Comfy["回环 ComfyUI，受控工作流/模型"]
    API --> LLM["allowlist LLM 出站，禁止任意 SSRF"]
~~~

### 4.2 必须保持的边界规则

1. 外部输入只能是结构化值、实体 ID、受限枚举和幂等键；绝对路径、命令、任意工作流 JSON 不属于公共 API。
2. 文件系统是受策略保护的实现细节；API 返回资产 ID、版本和短期下载令牌，不返回可直接使用的服务器绝对路径。
3. MySQL 保存权威元数据、状态和审计；文件以 manifest/checksum 与资产版本关联，数据库事务失败时由 outbox/reconciler 补偿。
4. ComfyUI、FFmpeg、TTS、LLM 都是受控出站/子进程边界，必须有资源上限、超时、错误分类和输入白名单。
5. 本机调用机制默认服务单用户；只要扩大监听地址，就必须切换到远程部署的身份和网络安全模型，不继承本机匿名假设。

## 5. 目标任务状态机与幂等模型

### 5.1 状态机

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Claimed: "原子领取，写 lease_owner/version"
    Claimed --> Running: "owner 确认启动并心跳"
    Claimed --> Cancelled: "取消请求生效"
    Claimed --> Pending: "领取失败或租约失效"
    Running --> Succeeded: "输出验证并条件提交"
    Running --> Failed: "不可重试或达到上限"
    Running --> Cancelled: "取消已确认且停止子任务"
    Running --> TimedOut: "超过 deadline"
    Running --> Pending: "租约过期且允许恢复"
    Failed --> Pending: "显式 retry，生成新 attempt"
    TimedOut --> Pending: "显式 retry 或人工恢复"
    Succeeded --> [*]
    Cancelled --> [*]
~~~

### 5.2 状态转移规则

| 转移 | 必要条件 | 禁止事项 |
|---|---|---|
| Pending→Claimed | DB 条件更新或事务行锁，status/version/租约条件同时满足 | 不能只依赖 Channel 或内存字典 |
| Claimed→Running | 同一 lease_owner、未过期、version 匹配 | 其他 worker 不能接管未过期租约 |
| Running→Succeeded | owner、version、输出 manifest Ready、结果唯一键均匹配 | 不能覆盖 Cancelled/Failed/TimedOut |
| Running→Failed/TimedOut | owner/version；记录分类错误、尝试次数和 Comfy prompt | 不能无条件把所有 Running 批量重置 |
| Pending/Claimed/Running→Cancelled | cancel_requested_at、权限、停止子进程和补偿清单 | 取消后不能由迟到的完成消息改回成功 |
| Failed/TimedOut→Pending | 只有显式 retry 且未超过 max_retries；新 attempt 和事件 | 不能原地重置历史错误或改变已发布结果 |

### 5.3 建议字段和事件

- generation_tasks：request_id、idempotency_key、business_key、state_version、lease_owner、lease_expires_at、heartbeat_at、cancel_requested_at、claimed_at、deadline_at、timed_out_at、failure_code、attempt、input_fingerprint、schema_version。
- task_events：task_id、from_state、to_state、actor/worker、request_id、state_version、reason、comfy_prompt_id、output_manifest_id、created_at。operation_logs 保留为人类可读摘要，但不取代事件表。
- unique key：按阶段定义 episode/shot/stage/input_fingerprint/workflow_version/output_profile；相同 request_id 返回原始结果，不同 payload 返回冲突。

### 5.4 资源池建议

| 池 | 初始建议 | 保护 |
|---|---|---|
| GPU/Comfy | 并发 1；保留现有 1024 MiB 最低空闲显存作为初始门禁 | 任务 deadline、OOM 分级降级、磁盘门禁 |
| TTS/字幕 | 并发 2 起步 | 文本长度/单任务时限、项目配额 |
| FFmpeg/技术 QA | 并发 1 起步 | 进程树终止、临时目录、CPU/磁盘限制 |
| Episode 合成/导出 | 并发 1 起步 | 大文件空间预估、输出原子发布 |

上述 CPU 数值是基于当前 i5-13600KF、32 GB 环境的保守起始建议，不是已压测结论；必须用真实本机链路校准。

## 6. 目标媒体数据流

~~~mermaid
flowchart TD
    Input["参考图 / 音频 / Comfy 下载"] --> Quarantine["随机名临时隔离目录"]
    Quarantine --> Verify["签名 + MIME + FFprobe + AV + 配额"]
    Verify --> Asset["资产版本 / manifest / checksum"]
    Asset --> DB["事务登记 DB 资产、结果、引用"]
    DB --> Token["Asset ID + 短期下载令牌"]
    Token --> Client["前端预览或导出"]
    Asset --> TempTask["任务临时目录"]
    TempTask --> Process["ComfyUI / FFmpeg / TTS 受限处理"]
    Process --> Verify2["输出签名、时长、尺寸、FPS、音频验证"]
    Verify2 --> Promote["同卷原子移动到版本目录"]
    Promote --> DB
    DB -. "失败/取消/超时" .-> Reconcile["outbox / 对账 / 可恢复清理"]
    Reconcile --> Quarantine
    Reconcile --> TempTask
~~~

当前代码在部分路径直接写最终目录；图中流程是目标设计，不是当前实现。

## 7. 数据库迁移、备份与恢复方案

### 7.1 迁移原则

1. 删除启动时的 DatabaseInitializer、ProductionSchemaMigrator、VideoQaSchemaMigrator 对生产 schema 的隐式写入职责；应用启动只检查版本和兼容性，失败则 NotReady。
2. 用显式迁移清单记录版本、文件 SHA-256、执行人、执行时间、backup_id、数据库版本和结果；迁移命令取得 MySQL advisory lock，禁止并行迁移。
3. 迁移账户与运行账户分离。运行账户不再使用 root；应用只拿业务所需 DML 权限。迁移账户不得放入应用配置。
4. 采用 additive-first：先加字段/表和索引，再双读/双写和回填，验证后启用唯一约束/归属约束，最后在单独发布中移除旧列。禁止未经备份和审批的 DROP、清库或覆盖历史媒体。
5. 关系回填先报告后拒绝：扫描 Project/Episode/Shot/Asset/Task/Result/QA 的归属；历史异常进入修复清单，不用自动猜测覆盖。

### 7.2 建议迁移顺序

| 阶段 | 内容 | 闸门 |
|---|---|---|
| M0 | 备份 DB、文件 manifest、工作流/模型 catalog；校验备份可读并在隔离实例恢复抽样 | 备份与恢复报告有 backup_id |
| M1 | task state_version、request/idempotency/business key、lease/heartbeat/cancel/deadline、task_events | 双 worker 和竞态测试通过 |
| M2 | asset version、manifest、quarantine/status/deleted_at/retention、结果引用和唯一键 | 历史路径/资产回填报告可追溯 |
| M3 | 关系组合校验、尺寸/FPS/帧数/大小/重试 CHECK 或等效服务端/数据库约束 | 报告模式归零，非法写入测试通过 |
| M4 | system_settings secret_ref/key fingerprint、LLM provider catalog、workflow/model hash/license | 密钥迁移和脱敏检查通过 |
| M5 | 运行时移除隐式 DDL，应用账户降权，迁移账户单独执行 | 干净启动无 schema 写入，readiness 正常 |

### 7.3 备份和恢复

现有 scripts\backup.ps1:15-44 会生成 mysqldump，并备份部分配置示例、目录和迁移文件，但主要依赖退出码；scripts\init_database.ps1:15-24 会在初始化前调用备份。后续必须补充：

- 数据库 dump 的压缩包 SHA-256、大小、表/行统计和加密存储；不可把 config\local.env 或任何密钥复制进报告。
- 文件 manifest：资产 ID、版本、相对路径、大小、SHA-256、MIME/探测摘要、发布状态、保留期；按数据分类备份 Data，Models/Workflows 只备份已登记可复现版本。
- 可读性检查：在隔离 MySQL 实例导入或至少恢复关键表并执行外键/计数/抽样 checksum；记录耗时和失败原因。
- 恢复演练：应用停写、恢复 DB、恢复文件、运行对账、只读启动、健康/任务/导出抽样；记录 RPO/RTO，演练不得接触生产覆盖目标。
- 事务无法覆盖文件系统时，以发布意图/outbox、manifest 和对账器补偿；不以“数据库提交成功”推断文件一定存在。

## 8. 质量、成本与媒体资源计划

### 8.1 媒体与子进程门禁

- 图片：签名/MIME/尺寸/像素总量/解码成功；音频：签名、时长、采样率、声道、编码和大小；视频：签名、时长、宽高、FPS、帧数、编解码器、音频轨道。
- FFmpeg/FFprobe/TTS：每次调用使用独立临时目录、显式连接/总时限、取消时终止进程树、限制 stdout/stderr、预估和检查磁盘；异常只记录错误码和安全摘要。
- ComfyUI：工作流、模型和节点必须来自 catalog；提交前验证 hash、输入资产和尺寸/帧数/steps/CFG 上限；OOM 按 frames→resolution→candidates/steps 降级，并在任务事件中记录。
- 磁盘：沿用现有环境脚本的 50 GB 警告和 20 GB 低位建议作为起始阈值，改为服务端硬门禁和告警；具体项目配额由用户确认。

### 8.2 Prompt、模型和成本

- Prompt 和脚本按版本保存，记录来源、编辑者、时间、输入摘要和是否发送外部服务；导出报告只显示必要内容。
- 每次执行保存 workflow/model/LoRA hash、节点版本、seed、参考资产版本、参数、GPU/运行时版本、输出 hash、QA 版本与人工结论。
- LLM 只使用本机 stub 或明确批准的 provider 做测试；预算按请求、项目、用户和周期计算，429/5xx 有界重试，连续失败熔断。

### 8.3 真实质量验收集

| 能力 | 最低验收问题 | 不能用什么替代 |
|---|---|---|
| 人物一致性 | 同一参考人物在不同镜头、姿态、光照下身份和关键特征是否稳定 | 仅用分辨率、清晰度或文件存在 |
| 场景一致性 | 背景、空间关系、道具、时间/光照是否连贯 | 仅用 codec、FPS 或黑帧 |
| 动作控制 | 目标动作的主体、方向、时序和结束状态是否符合镜头意图 | 仅用运动量启发式 |
| 音频成片 | 对白可懂、响度一致、口型/画面同步，音乐和音效不遮盖对白 | 仅用有音频轨道 |

每项都需要正例、硬失败例、人工评分说明和回炉原因；自动分数必须显示置信度和“需要人工判断”。

## 9. 前端、测试、发布与可观测性路线

### 9.1 前端

- 按路由和功能拆分项目、制作、候选、QA、导出、设置等 bundle；建立共享 API 客户端，统一会话、CSRF、request_id 和错误解析。
- 用 URL/安全本地状态恢复项目、Episode、Shot 和候选；任务使用 SSE/WebSocket 或带退避/ETag 的轮询。
- 明确“生成、取消、重试、覆盖、删除、解锁、导出”的影响、版本、费用/资源和可逆性；后端二次校验。
- 增加加载/空态/错误态、网络断开、长任务恢复、键盘焦点、ARIA、窄屏布局和候选明确选择。

### 9.2 测试矩阵

| 测试层 | 必测内容 | 当前状态 | 通过标准 |
|---|---|---|---|
| 本地静态 | .NET build/test/format；前端 build/typecheck/lint；SQL/迁移校验；依赖漏洞和秘密扫描 | 历史构建/管线有通过记录；本轮未重跑 | 干净 checkout 可重复，秘密不进入输出 |
| 本地安全 | CORS、认证/CSRF/RBAC、路径边界/reparse/UNC/ADS、资产归属、上传签名/MIME/配额、异常响应脱敏 | 未验证；/api/media 宽路径和 CORS wildcard 已确认 | 负向用例全部 fail closed |
| 本地一致性 | 双 worker 领取、状态竞态、幂等重复、租约恢复、取消/超时、DB/文件对账 | 未验证；当前无 Running/Pending 只代表静态时点 | 一任务一执行，终态不可覆盖，孤儿可处理 |
| 本地真实链路 | 真实本机项目→参考图→Comfy→QA→TTS/字幕→FFmpeg→导出；不使用付费 LLM | 健康和空队列已探测；本轮未生成视频 | 任务事件、资产 manifest、QA 和人工判断完整 |
| 外部服务夹具 | Comfy hang/OOM/restart/history 缺失；FFmpeg/TTS 超时；LLM stub 的 429/5xx/重定向/大响应 | 未验证 | 有 deadline、重试上限、熔断和对账 |
| 浏览器 | 登录/配对、刷新恢复、实时状态、候选选择、危险操作、响应式、键盘和长任务断线 | 当前无 router/Playwright 命令，未验证 | 干净浏览器可重复，错误不丢状态 |
| 迁移/恢复 | backup 可读、隔离恢复、升级/失败/回滚、文件 manifest 对账 | 未验证；现有脚本缺可读性证明 | 有 RPO/RTO 报告，恢复后可只读启动和抽样导出 |
| 未来局域网 | TLS、账户/RBAC/CSRF、限流、审计、数据库/Comfy 不暴露、worker 隔离 | 不满足 | 外部扫描和故障演练通过后才 Conditional Go |
| 未来公网 | 反向代理/WAF、密钥轮换、内容审核/授权/水印、备份监控、渗透/合规 | No-Go | 全部 P0/P1/P2 与用户/法律条件满足 |

## 10. P0-P3 路线图

| 优先级 | 目标 | 项目项 | 完成定义 |
|---|---|---|---|
| P0 | 先封闭攻击面和一致性灾难 | SEC-P0-01~04、DATA-P0-01、TASK-P0-01/02、MEDIA-P0-03 | 无匿名高风险访问；无任意路径；无任意 LLM 出站；应用非 root/不启动改 schema；任务可原子领取和幂等；输入/输出隔离 |
| P1 | 让长任务可恢复且结果可解释 | REL-P1-01/02、MEDIA-P1-03、DATA-P1-04、AI-P1-05、COST-P1-06、QA-P1-07、UI-P1-08 | deadline/lease/背压/对账/版本溯源/成本/真实 QA/刷新恢复全部有验收证据 |
| P2 | 建立长期运营和发布能力 | OPS-P2-01、TEST-P2-02、ASSET-P2-03、OPS-P2-04、COMP-P2-05 | CI、告警、备份恢复、资产治理、发布回滚和内容治理可演练 |
| P3 | 在边界清晰后扩展产品能力和部署范围 | PROD-P3-01、DEPLOY-P3-02 | 四类内容能力有真实验收集；LAN/公网按独立 Go 条件通过 |

## 11. 分阶段实施顺序

### 0～3 天：封闭边界、定规则、建立基线

1. 冻结对外监听和现有数据；确认只允许本机单用户；为高风险路由制定权限矩阵和“默认拒绝”清单。
2. 设计并评审 PathPolicy、资产 ID/下载令牌、任务状态/幂等字段、LLM provider allowlist 和密钥迁移策略。
3. 对现有数据库、资产路径、工作流/模型和任务做只读 manifest/一致性报告；不修改生产数据。
4. 把当前 No-Go 条件写入发布闸门；准备本机安全测试夹具、Comfy/LLM/FFmpeg stub 和备份恢复隔离目标。

阶段出口：用户确认本机认证 UX、数据保留/配额、LLM provider 和备份目标；无代码变更也不能把当前系统宣称为安全发布。

### 1～2 周：执行 P0

1. 落地同源/精确 CORS、本机配对会话、CSRF、角色授权和审计。
2. 落地 PathPolicy、资产 ID、客户端输入重建、LLM 出站限制和安全密钥存储迁移。
3. 完成显式迁移命令、备份可读/隔离恢复、应用最小权限账户和数据库网络收敛。
4. 完成任务字段、原子领取、租约、条件转移、幂等键和高风险操作的负向测试。
5. 统一上传/下载/Comfy 输出隔离和基本签名/MIME/大小/配额门禁。

阶段出口：P0 测试矩阵全通过，应用启动不改 schema，No-Go 仅保留外部/LAN/公网条件，不以本机 build 代替安全验收。

### 3～6 周：执行 P1/P2 基础

1. Comfy deadline/退避/重启恢复/孤儿对账；CPU/GPU 独立池、背压和资源指标。
2. 临时目录原子发布、outbox/reconciler、资产版本和关系约束。
3. 完整溯源、成本/熔断、技术/自动/人工 QA 和四类真实验收集。
4. 前端路由恢复、实时状态、候选明确选择、危险操作说明和浏览器 E2E。
5. 结构化日志、指标/告警、CI、依赖/秘密扫描、发布 manifest、备份恢复演练和回滚 runbook。

阶段出口：真实本机链路可恢复、可解释、可审计；发布可回滚；局域网是否开放仍需独立 Conditional Go。

### 长期：产品能力与受控扩展

1. 以验收集推进人物、场景、动作、音频能力；新模型/工作流只作为有许可证和 hash 的实验版本。
2. 完成资产保留/删除、授权/版权/肖像/声音 consent、水印/provenance 和人工审核闭环。
3. 如确有需求，再按 DEPLOY-P3-02 开启 LAN；公网另做威胁建模、合规、内容治理、容量与灾备验收。

## 12. 上线 Go / Conditional Go / No-Go

| 场景 | 结论 | 条件 |
|---|---|---|
| 当前代码直接对 LAN/公网或无人值守开放 | No-Go | CORS/认证/路径/LLM/数据库/任务一致性问题未闭环 |
| 当前代码用于受监督本机研发 | Conditional Go | API/ComfyUI 仅回环；没有不可信本地用户；不配置外部 LLM 密钥；生产媒体不外发；人工确认每次危险操作；另有可验证备份 |
| P0 完成后的本机单用户 | Conditional Go | P0 测试、备份恢复、任务恢复和路径负向测试全通过；仍不等于公网生产 |
| P0+P1+P2 完成后的局域网 | Conditional Go | TLS、账户/RBAC/CSRF、限流、审计、网络隔离、监控、恢复演练和真实浏览器/压力测试通过 |
| 公网或多租户产品 | 当前 No-Go | 还需要专门威胁建模、隔离 worker、内容/版权/授权治理、WAF/密钥轮换、容量/灾备、渗透和法律合规验收 |

## 13. 需要用户选择或提供的外部条件

1. 本机认证方案：推荐 Windows DPAPI/Credential Manager + 一次性启动令牌配对；请确认是否接受首次配对 UX，或要求纯命令行 token。
2. 网络范围：继续保持单机，还是计划局域网；暂不建议直接规划公网。若 LAN，需要指定信任网段、TLS 证书和账户来源。
3. 账户角色：至少 Admin、Producer、Reviewer、Viewer 是否满足；谁可以改 LLM、删资产、解锁、导出和批准。
4. LLM：允许哪些 provider/host，是否只允许本机；预算上限、数据是否可以离开本机、密钥使用 DPAPI 还是企业秘密服务。
5. 数据治理：项目/全局磁盘配额、临时文件保留期、已发布版本保留期、删除后恢复窗口和备份保存周期。
6. 扫描与运行环境：本机是否有可调用的病毒/隔离扫描器；是否允许准备隔离 MySQL 恢复实例；备份目标、RPO/RTO 和维护窗口。
7. CPU 池起始值：是否接受 TTS/字幕 2、FFmpeg/QA 1、Episode 合成 1 的保守起点，并用真实本机链路校准。
8. 内容政策：真人肖像/声音授权、第三方素材/模型许可证、水印/provenance、人工审核和未来公开发布规则。
9. 执行授权：本方案完成后等待明确指令“执行 P0”或“执行全部计划”；在该指令前不修改业务代码、数据库、配置、工作流、模型或生产数据。

## 14. 本轮变更与证据边界

- 本轮只读检查了项目文档、源码、配置示例、运行中的 API/ComfyUI、MySQL 元数据、端口/进程和目录属性；没有读取、输出或记录 config\local.env 的秘密。
- 本轮没有执行数据库迁移、备份、恢复、清库、删除、付费 LLM 调用或真实视频生成，没有修改系统环境变量、ComfyUI、模型、工作流或 C:\install\AI\Data 中的生产媒体。
- 历史文档中的 build、pipeline、QA 和 3-shot 结果只按其记录的范围引用；当前健康可用不代表权限安全、并发安全、灾备可恢复或公网可用。

# MiniMax 本地接入与流程优化实施记录

> 21时结果更新：四个H3权重已完成下载和完整校验，真实队列任务1165于20:58完成视频/WAV登记，技术Passed；864×480/24FPS/124帧，约656.3秒，队列采样峰值9484MiB。中文声音、口型、身份/动作仍需人工观看，发布Blocked。下方20时下载文字为当时的阶段记录。

> 后续20时阶段：用户请求的10秒校园样片已用当前可用的本地LTX生成；不是H3结果。发现之前Video VAE下载已因Windows进度文件原子替换访问冲突退出，已修复有界重试、7项离线回归Passed并恢复续传。详见[校园样片记录](CAMPUS_PREVIEW_20261018.md)。

日期：2026-10-18（Asia/Shanghai）。本轮采用用户选定的“本地开源优先，云 API 作为可选补充”；随后按用户要求取消本机登录。

## 当前结果

- Passed：本机免登录、前后端构建、本地 H3 工作流登记、模型准备/续传工具、任务参数校验、原生音轨提取代码及回归。
- Passed：真实队列的新首帧任务 1156、系统中文配音任务 1158、修复后的 LTX 视频任务 1159。
- Failed：首次 LTX 对照任务 1157 输出 113 帧，未达到请求的 121 帧；失败记录保留，新版本任务 1159 已通过。
- Passed：四个H3权重下载/完整校验、真实任务1165及独立视频/WAV登记；尚未完成H3画质、动作或声音的内容审核，不能给出提升百分比。
- Blocked：内容审核、正式剧集采用与发布资格。技术生成成功不自动通过这些环节。

实时下载和联调进度见工作台 `http://127.0.0.1:18080/#minimax`，以及 `C:\install\AI\Data\MiniMaxLocal\integration-run.json`。本报告中的任务号是本次验收记录，不能当作后续新运行的任务号。

## 接入范围

新增“MiniMax 本地”页面，使用既有 ComfyUI、GenerationQueue、MySQL、资产登记和 FFmpeg。用户选择项目、上传首帧、填写动作/声音描述及固定种子；任务独立保存视频和 WAV 音轨，可查看最近实验版本、播放和取消任务。

当前路线固定为量化 H3 FL2VA，864×480、124 帧、24 FPS、20 steps；原生声画约 5.167 秒。GPU 并发仍为 1。不会自动换到云 API、另一个模型或缩减规格；实验路线的自动重试次数为 0，OOM 保留实际失败原因。

H3 原生声音与独立 TTS 是不同能力。本轮提供视频原生声音生成和分离音轨，原有 Windows 系统中文 TTS 独立配音继续可用；没有宣称 MiniMax 云 Speech 模型已在本地部署。云视频/云 TTS 尚未实现或启用，本轮无需 API Key，没有进行云端付费调用。

[MiniMax 官方 H3 仓库](https://github.com/MiniMax-AI/MiniMax-H3)公开了 Base 声画模型；官方 Context-IR 和 2K 再生成不在当前开源发行范围内。因此本机量化短片不能等同于完整云端 2K 流程。

## 本机访问

用户明确表示忘记密码并要求取消登录。本机 `config/appsettings.json` 设置 `LocalAccess.RequireLogin=false`；原有管理员校验值未重置。示例配置仍以密码模式为默认，`AI_VIDEO_STUDIO_REQUIRE_LOGIN=1` 可恢复密码登录。

免登录模式启动时只允许回环监听；请求同时检查回环来源地址、Host 和精确 Origin。写请求使用进程密钥签名的 CSRF 令牌并检查 Cookie/Header 配对；审计身份为 `local-operator / LocalOperator`，不伪造管理员会话。状态如实返回 `authenticated=false, loginRequired=false, accessMode=LocalOnly`。

实际 API 验证：业务读取 200、签名写入 200；缺少 CSRF、陌生 Origin、伪造 Host 均为 403。API 和 ComfyUI 分别监听 `127.0.0.1:18080 / 8188`。

## 模型与依赖

设备：RTX 4070 12GB（12282 MiB）、约 31.8 GiB 内存。复用 ComfyUI 0.31.0、现有 Python/torch/FFmpeg，不重装基础环境。

| 组件 | 来源 | 大小 |
| --- | --- | ---: |
| H3 diffusion Q4_0 | molbal/MiniMax-H3-GGUF | 10.60 GiB |
| Qwen3-VL 文本编码器 Q2_K_M | unsloth/MiniMax-H3-GGUF | 12.20 GiB |
| Video VAE FP16 | Comfy-Org/MiniMax-H3 | 4.85 GiB |
| Audio VAE FP32 | Comfy-Org/MiniMax-H3 | 0.56 GiB |
| 合计 | 四个数据文件 | 28.21 GiB |

仓库修订、文件名、完整 SHA-256 和目标路径固定在 `config/minimax-local-assets.json`。下载采用有界分块、原子进度记录、进程锁及完整哈希校验；`.part` 预分配长度不代表下载进度，页面按完成的数据块计数。已有不同内容的模型/工作流被保留并报错。

[官方集成索引](https://github.com/MiniMax-AI/awesome-minimax-h3-integration#by-vram-and-hardware)提供小显存量化路线参考，但不是本机通过证明。当前使用 [H3 GGUF 兼容分支](https://github.com/kyuz0/ComfyUI-GGUF-H3)，固定提交 `6d33de29cdc8bfa3f417dc0d96cbbc3b5412b8ed`，仅补充安装 `gguf==0.19.0`。最初下载的通用 GGUF 节点没有 H3 支持，已作为本轮新建目录保留为 `.disabled`，没有覆盖旧环境。

普通 `start.bat` 与新增启动脚本统一使用已实测兼容 LTX 的 H3 低显存配置：关闭 dynamic VRAM、保留 1.5 GiB 显存并关闭 pinned memory。当前实际 ComfyUI 已加载对应节点；4 个模型完成完整校验后已实际执行1165。模型缺失或漂移时仍拒绝生成。H3 Community License 与内容/发布审核状态分别记录。

## GitHub 借鉴落地

| 参考 | 采用的设计 | 当前落地 |
| --- | --- | --- |
| [MiniMax H3 / 官方集成索引](https://github.com/MiniMax-AI/MiniMax-H3) | 原生声画、显式首帧、可复现部署 | 固定工作流、量化文件版本/哈希、单首帧、无生产关联的本地实验 |
| [XmYx/ComfyStudio](https://github.com/XmYx/ComfyStudio)（MIT） | 按镜头管理生成版本，保存参数并预览输出 | 最近实验版本、固定种子、真实任务结果、独立音轨预览；没有移植 Qt 应用 |
| [oiuv/ai-short-drama](https://github.com/oiuv/ai-short-drama) | 明确阶段、素材职责和 TAKE | 延续现有 stage/role/changeReason 与 TAKE；切换项目时清除首帧绑定，避免旧素材混用。README 声明 MIT，本轮仅参考流程设计 |
| [MiniMax 官方 MCP](https://github.com/MiniMax-AI/MiniMax-MCP)（MIT） | 区分提交、查询与结果文件 | 复用现有持久队列，提交使用稳定幂等键；响应丢失时保留键，不盲目创建新任务。未安装或调用其云工具 |
| [VBench](https://github.com/Vchitect/VBench)（Apache-2.0） | 分维度评估视频，而非只看文件生成成功 | 对照固定首帧、动作和种子，分别记录技术执行、内容审核与发布资格；未安装完整 VBench，也未虚构其评分 |

本轮新增逻辑沿用 .NET/Vue/MySQL，没有复制外部项目的大段实现。现有阶段参考与 TAKE 的先前记录见 `docs/EXTERNAL_PROJECT_ADAPTATION_20260914.md`。

## 真实队列验收

新建项目 24，名称前缀 `MiniMax本地接入验收_`，没有使用以前的媒体。所有生成经服务 API 和真实队列执行，没有手工改任务状态。

| 任务 | 内容 | 结果 |
| --- | --- | --- |
| 1156 | SD1.5 新首帧，864×480 | Passed |
| 1157 | 原 LTX 契约，实际 113 帧 | Failed：FRAME_COUNT_MISMATCH |
| 1158 | 系统中文配音，约 6.177 秒 | Passed |
| 1159 | LTX 契约 v2，512×320、24 FPS、121 帧 | Passed，任务约 45.4 秒 |
| 1165 | H3，同一张新首帧、相同动作和固定种子，请求原生中文声音 | Passed：864×480、24FPS、124帧视频及独立WAV；耗时656259ms，采样峰值9484MiB。台词/口型等内容待审 |

LTX 根因：当前 ComfyUI 的无 Guide `LTXVImgToVideo` 按请求长度直接解码；旧契约错误减去 8 帧。通过 FFprobe 确认任务 1157 为 113 帧后，将该实验契约显式升级为 `02_ltx_i2v_quality_api.comfy031-v2`，执行完整 121 帧，记录 changeReason 并新建任务 1159。带 Guide 的其他契约保持原映射，没有补帧伪装成功。

`tools/minimax/run_local_acceptance.py` 会持久记录项目和任务 ID，等待模型完成后核验、登记并仅提交一次 H3。重启该工具会读取既有记录和真实任务；对已失败任务不自动重生。成功时必须同时存在可用 MP4 和 WAV，仍标记 `contentStatus=NeedReview, publicationStatus=Blocked`。

运行状态位于 `C:\install\AI\Data\MiniMaxLocal\integration-run.json`；实际 API 安全检查和任务明细位于忽略目录 `logs/minimax-local-20261018/runtime.json`。文件均不含密码、Cookie、令牌或 API Key。

## 已执行的回归

- `.NET Release` 构建与发布、Vue production build：Passed。前端原有第三方 PURE 注释及大 chunk 提示仍存在。
- `--minimax-local-regression`：17 Passed；缺模型、哈希漂移、预分配进度、固定参数、非正式生产和目录边界。
- `--local-only-access-regression`：16 Passed；回环、Host、Origin、签名 CSRF 和恢复密码模式；不访问数据库。
- Python 下载工具离线回归：5 Passed；续传、范围响应、完整哈希、已有文件保留和路径越界。
- 前端 MiniMax mock 回归：4 Passed；模型未就绪、免登录、稳定幂等键和项目切换清首帧。此项不是 GPU 端到端证明。
- 工作流契约 self-test：Passed；11 个契约及 Guide/实验路线阻断。新增横屏首帧契约为实验用途。
- H3 参数回归：14 Passed；质量工具 self-test：Passed。
- 实际 FFmpeg 有声/无声 720p 后期及原生音轨提取回归：Passed，合成夹具目录 `C:\install\AI\Data\acceptance\delivery720_20261018_080937_271`。该夹具不证明人物内容质量。
- 真实发布页面：免登录进入 MiniMax 页面、无密码输入、无 JS pageerror，状态和验收进度可读。

## 复现与接续

在项目根目录执行；已有服务/下载在运行时不要重复启动。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_minimax_local.ps1 -Workers 8
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/publish.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_minimax_local.ps1 -EnableWorker
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/run_local_acceptance.py
```

模型校验可使用准备脚本的 `-VerifyOnly`。Worker 仅在 migration 008 已验证、无旧待执行任务后启用；本轮已确认 schema ready。没有执行数据库结构迁移。

后续验收需看真实 H3 短片的身份、手部/动作完成、中文台词、口型、声音自然度及耗时/峰值显存。没有这些证据前不报告“提升多少百分比”，也不把本地实验升级为正式剧集路线。

Git：`main`，HEAD `d6ec38d`。工作区原有大量未提交修改，本轮保留，未提交或推送。

# Qwen3-TTS 本地配音接入与中文试听

2026-10-22，Asia/Shanghai。Qwen3-TTS 本地部署、声音工作台接入和真实中文试听技术验收 **Passed**。内容听审仍为 **NeedReview**，等待用户试听；发布保持 **Blocked**。分支 `main`，基线 `d6ec38d`，本轮源码与既有工作区改动均未提交。

## 中文试听

- 项目 28：Qwen3-TTS 本地中文试听 2026-10-22。
- 实际任务 1196：Succeeded，GPU Audio；完整任务 33.034 秒，其中模型加载约 2.787 秒、模型推理约 20.900 秒。
- WAV：`C:/install/AI/Data/Artifacts/project-28/audio/task-1196/v0001/v0001_qwen3_chinese_preview_0fbc4f5a5d26.wav`。
- 实际规格：12.88 秒、24000 Hz、单声道、PCM signed 16-bit；618284 字节。整段 FFmpeg 解码和浏览器播放至 ended 均 Passed。
- SHA-256：`0fbc4f5a5d2640af58080ce8984d8bfcc940aecc308f5795f730ef422d565d7e`。
- 音色 Vivian；指令：用温柔、自然的普通话讲述，语速稍慢，句间停顿清晰，像在讲一个校园故事。
- 文本：午后的阳光穿过树叶，落在安静的校园里。林夏拾起长椅上的红色笔记本，轻声喊道：同学，你的本子忘拿了。
- [声音工作台](http://127.0.0.1:18080/#voice)可直接选择历史任务 1196 试听，也可填写新文本。

PyTorch 峰值 allocated 4260.251 MiB、reserved 4510 MiB。独立整卡一秒采样 43 个，采样峰值 5853 MiB，最低空闲 6158 MiB；不是连续峰值测量。进程结束后的整卡使用约 1225 MiB，显存已释放。技术音量检测均值 -21.0 dB、峰值 -5.2 dB；这些指标不能替代用户对发音、情绪和节奏的听审。

缓存验证任务 1197 Succeeded，0.511 秒，推理记录 `cacheHit=true`；与1196 WAV字节哈希完全相同，没有再次运行模型推理。重复同一请求返回既有任务；同一幂等键改变文本返回409。

## 固定路线

- 模型：`Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`。
- 固定上游 revision：`0c0e3051f131929182e2c023b9537f8b1c68adfe`。
- 模型目录：`C:/install/AI/Models/TTS/Qwen3-TTS-12Hz-1.7B-CustomVoice`；两份权重约 4.52 GB，下载断点及 SHA-256 记录保存在模型目录。
- 运行环境：`C:/install/AI/Qwen3TTS/venv`，Python 3.13.2、qwen-tts 0.1.1、transformers 4.57.3、accelerate 1.12.0，复用现有 torch/torchaudio 2.11.0+cu130。
- 独立 venv 的 `.pth` 只读取现有 CUDA 依赖。安装不写入 ComfyUI 的环境；原 transformers 5.14.1 已复查保留。
- RTX 4070 12GB，BF16、PyTorch SDPA。没有安装 FlashAttention，不切换到其他 TTS 模型或云服务。
- 当前部署为 CustomVoice 预设音色和演绎指令，不包含 Base 声音复刻或 VoiceDesign。

## 安装与使用

准备命令：`powershell -NoProfile -ExecutionPolicy Bypass -File C:/install/AI/VideoStudio/scripts/prepare_qwen3_tts.ps1`。

该命令准备独立 venv，并以固定 revision 下载模型。大权重使用已有的分块断点下载器及 SHA-256 校验；现存不同文件会保留并报错。模型文件和依赖位于仓库外，不提交权重。

打开 `http://127.0.0.1:18080/#voice`，选择 Qwen3-TTS、本地音色、保存项目，填写配音文本与演绎指令后生成。每段最多 500 字符，指令最多 300 字符。默认 Vivian 中文女声，另有 Serena、Uncle Fu 及其他预设音色。生成完成后可在同页播放、下载 WAV 和查看最近任务。

Qwen 通过演绎指令调节语速、语气和声线；数值语速固定为 1、音高固定为 0，服务端会拒绝不支持的数值设置。Windows 系统语音仍可显式选择。角色的默认音色字段可保存 `qwen3:Vivian` 等标识；自动对白任务会带入镜头情绪字段。

## 任务与资源

- `/api/audio/tts` 写入正式 Audio 任务，Qwen 使用 GPU 资源类别，与视频共用跨进程 GPU 文件锁。Windows TTS 使用 CPU 队列。
- 提交时绑定引擎配置与推理代码的版本摘要，执行前检测漂移；每次推理前复核两份权重哈希。
- 执行前确认 ComfyUI 没有运行或等待任务，再释放闲置模型；子进程检查至少 6144 MiB 空闲显存。
- GPU 模型在每次任务的独立子进程中加载。完成、取消或超时后退出并释放显存，不常驻 GPU，不增加对外端口。取消 Qwen 不触发 ComfyUI interrupt。
- 合成强制离线。配置、音色或推理失败会明确报错，不回退系统语音、模型或云服务。
- 缓存包含文本、音色、演绎指令、固定模型与引擎版本；有效 WAV 与推理记录完成后才复用。
- 音频通过 FFprobe 和受控资产发布流程，生成独立推理 JSON 记录。任务成功与用户听审分别记录。

## 验证结果

- Passed：.NET 构建 0 警告/0 错误；Vue 构建；Python 编译及真实 CUDA 导入。
- Passed：15 项 Qwen 合约回归，包含缺失/漂移模型拒绝、无效音色、长度/参数限制、取消/超时杀死子进程树、超时与用户取消区分、ComfyUI 忙时拒绝。测试不生成模型音频。
- Passed：2 项页面夹具，验证提交演绎指令、试听入口和未部署时阻止生成。
- Passed：原 MiniMax 34 项、H3 27 项回归及跨进程 GPU 锁验证。
- Passed：两份实际模型权重SHA-256验证、离线真实队列生成1196、完整解码与浏览器完整播放；播放至12.88秒且ended=true，无媒体错误。
- Passed：17项真实API检查，包含幂等冲突、无效文本/指令/音色/参数/项目拒绝、不创建无效任务、GPU类别及版本绑定、旧Windows中文TTS真实预检、1197缓存复用与字节一致性。
- 首次真实页面测试Failed：通用任务列表把旧Failed任务排在前面，新配音未进入有限结果集。增加专用`/api/audio/history`后，原1196样本完整播放重测Passed；没有重复生成模型音频。
- Blocked：内容听审和发布许可仍等待人工确认。未做声音复刻或新视频生成，没有云调用或API Key要求。

证据目录：`C:/install/AI/Data/Qwen3Tts20261022`。`environment.json`为环境，`run.json`为实际任务/资产，`inference.json`为模型和耗时，`audio-probe.json`/`audio-volume.txt`为音频验证，`gpu-samples.jsonl`/`gpu-summary.json`为采样，`api-checks.json`为17项API结果，`browser-playback.json`/`voice-workbench.png`为完整播放和实际页面。实际试听runner为`tools/qwen3_tts/run_acceptance.py`，恢复先读取记录并查询1196，完成状态不会重复提交。

本地API已部署并恢复，最终API PID 17212、ComfyUI PID 33844；真实任务均已结束。原发布目录备份位于`Data/Deploy/BeforeQwen3Tts20261022`。数据库没有结构变更；安装没有改写既有ComfyUI/Python/FFmpeg或历史媒体。

## 官方资料

- [Qwen3-TTS 官方实现与模型说明](https://github.com/QwenLM/Qwen3-TTS)
- [固定模型版本](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/tree/0c0e3051f131929182e2c023b9537f8b1c68adfe)

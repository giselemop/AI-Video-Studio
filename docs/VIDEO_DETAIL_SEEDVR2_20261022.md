# 2026-10-22 视频细节优化（技术Passed，待用户审片）

用户授权在现有Qwen3配音校园10秒视频上实施保细节导出、SeedVR2短片试验及效果对比。原1198/1199/1200和1196 WAV保持。不得自动重跑H3或调用收费云服务。

恢复入口：`C:/install/AI/Data/SeedVR2Enhancement20261022/run.json`。真实任务均经过业务队列；GPU并发1和跨进程互斥继续生效。短片检查后决定整片修复是否可用；技术验收与内容审核分别记录。

## 部署与代码

- SeedVR2独立环境：`C:/install/AI/SeedVR2/venv`，仅通过.pth复用既有ComfyUI的CUDA运行库，不修改其环境。Python3.13.2、PyTorch2.11.0+cu130。
- 引擎：numz/ComfyUI-SeedVR2_VideoUpscaler，提交4490bd1f482e026674543386bb2a4d176da245b9。
- 权重：numz/SeedVR2_comfyUI，版本09ced71023636e9bc8cdf9cdecfb2625d1e691e8；3B FP8 3,391,544,696字节和VAE 501,324,814字节均下载并SHA256校验Passed。位于Models/upscale_models/SeedVR2；不进入Git。
- 配置config/seedvr2.json，准备脚本tools/video_detail/prepare.py，离线子进程tools/video_detail/restore.py。推理前再次校验引擎与权重、源文件；PNG中间结果后编码一次，AAC沿用源音频。默认混合强度0.65，逐镜头处理，避免跨切点传播纹理。
- 新VideoRestore预检/GPU队列任务，最多1080p/24FPS/240帧独立预览；禁止关联正式Episode/Shot/ProductionRun。版本摘要、源SHA、镜头边界和强度纳入提交参数。
- Concat独立预览支持singlePass=true，一次完成拼接、裁剪、缩放和声音混合。只混音时视频零起点采用流复制，非零起点保留归零兼容路径。

## 结果与使用

技术验收Passed。用户可打开[同步对照页](http://127.0.0.1:18080/video-detail-compare.html)，选择2秒动作或完整10秒，支持拖动同一帧、半速、局部放大及单条旁白。三栏为原1200、一次导出1201、最终修复1206。动作修复使用最终1205，对齐原片6.00–8.041667秒。

最终视频：`C:/install/AI/Data/Artifacts/project-30/video/task-1206/v0001/v0001_seedvr2_10s_complete_audio_debda17254c8.mp4`，SHA256 `debda17254c8f1e68b1243c3e189c5120b0d40285efe435f6901c50c366e6d6f`。

| 真实任务 | 用途 | 实际规格 | 秒 |
| --- | --- | --- | ---: |
| 1201 | 两原生源片一次编码并接入Qwen配音 | 1920×1080 / 24FPS / 240帧 / 10秒 | 11.687 |
| 1202 | 同源素材第6秒开始的动作样片 | 1920×1080 / 24FPS / 49帧 / 2.041667秒 | 5.690 |
| 1203 | SeedVR2样片推理 | 同上 | 252.740 |
| 1204 | SeedVR2整片推理，124/116两镜头 | 1920×1080 / 24FPS / 240帧 / 10秒 | 1262.216 |
| 1205 | 样片完整音轨无损换轨 | 49帧，保留1203视频每帧 | 3.738 |
| 1206 | 整片完整音轨无损换轨 | 240帧，保留1204视频每帧 | 14.956 |

1203/1204均只执行一次，未重新生成H3。GPU修复整片约21分2秒；每5秒设备采样的显存峰值：样片9226MiB、整片9424MiB（12GB RTX4070）。框架报告峰值分配6520.338MiB、峰值保留7616MiB，口径与整卡采样不同。原配音1196与源1198/1199/1200哈希全部保持。

抽帧中衣物、背包及建筑边缘更干净，部分树叶纹理更清晰；脸部仍有重建感，源片的手指/握书、背包变化和人物连续性没有得到语义纠正。检查了样片0/12/24/36/48帧，以及整片0/60/123/124/180/239帧。没有以锐度或技术QA评分替代真实感判断；时序自然度与听感仍NeedReview，发布Blocked。采用保守0.65混合并匹配原色调，不叠加强锐化，不把推测纹理当作真实恢复。未来生成源片仍应采用单人、单动作、稳定光照和缓慢镜头的提示词与分镜；本轮没有为此额外重跑H3。

## 音频缺包定位与修复

初版修复器同时限制视频帧数并混入流复制音频，导致视频结束时提前停止音频包输出。1203的AAC为原音轨前缀，PCM解码只有47616个24kHz样本，原动作样片为49000个样本。此项验收Failed，不能把其推理记录中的“source stream copy”当成完整性证据。

现包装器改为先编码纯画面，再单独无损混流并比较AAC载荷摘要。为保留已完成GPU结果，业务CPU队列1205/1206分别恢复1202/1201的完整AAC：修复前后视频帧MD5逐帧一致；AAC载荷逐字节一致。两原始推理结果保留作过程证据，预览页只使用最终完整音轨版。

完整台词保持音高1.32倍速、起点0.12秒。最终音频240000个24kHz样本/10秒；完整拟合旁白236977样本/9.874041667秒，无台词截断。与原Qwen拟合参考的相关系数0.999958041，峰值-5.278dB。音色/语气仍待用户听审。

## 验收证据

- `output-verification.json`：六个新任务均完整解码，240/49帧全部不同；原文件哈希保持、无损换轨视频帧一致、AAC完整及旁白比对Passed。
- `api-regression.json`：30项实际API检查Passed，覆盖版本/源SHA/GPU类别/独立预览/强度/边界帧/裁剪/换轨混参及拒绝POST不写任务。
- `browser-sample.json`、`browser-full.json`：3项真实浏览器测试Passed。最终三路均实际播放至10秒、ended=true、各解码240帧、无媒体错误；样片同步、拖动、放大和路径拒绝Passed。
- `Data/acceptance/delivery720_20261022_040759_896/report.json`：实际FFmpeg回归Passed，零起点混音保持视频帧，非零起点归零兼容、配音延时/音高/静音、49帧裁剪、禁止静帧补足、完整音轨无损换轨均通过。
- SeedVR2合约11项、Qwen3合约15项、MiniMax本地34项、H3合约27项，以及跨进程GPU锁与异常退出恢复Passed。Seed合约含真实子进程树取消、超时、无伪媒体发布，不运行GPU。
- .NET构建、Vue构建、Python编译、差异空白检查Passed。Vue保留现有大包提示。恢复检查没有新增任务。现场状态和源路径记录在run.json；模型、音频、视频与运行证据全部在仓库外。

## 维护与恢复

`GET /api/video-restore/status`返回部署状态和配置/包装器版本摘要；`GET /api/video-restore/comparison`只返回已存在的受控Artifacts路径。`VideoRestore`通过既有POST /api/tasks预检、GPU锁、空闲检查、子进程和资产发布执行。`Concat.singlePass`用于一次导出；`Concat.audioStreamCopyFrom`用于同规格、同时长、零起点的独立无损换轨，绑定两个源SHA，不与字幕、裁剪、音量或转码混用。

运行依赖记录在runtime.json，独立环境增量依赖固定在tools/video_detail/requirements.txt。权重准备使用prepare.py；已完成后只运行run_acceptance.py --stage check，禁止为“核验”重跑GPU。

接管时18080/8188已离线，先以关闭Worker恢复服务；发布目录已备份至Data/Deploy/BeforeSeedVr2_20261022_0330与BeforeSeedAudioFix_20261022_0408。最终API33496、Comfy监听实际进程以runtime-health.json为准；Worker启用、GPU/CPU并发各1、队列空闲。未改系统环境变量、数据库结构或远程发布。

分支main，HEAD d6ec38d076a8b0336d349c36df5c123f2c941ac8。本轮及先前脏工作保留，未提交/推送；待用户审片，不自动追加GPU或收费服务。

# LTX生成阶段60FPS本机实验

日期2026-10-18（Asia/Shanghai）；分支`main`、HEAD`d6ec38d`，既有未提交修改保留，本轮未提交/推送。

## 结论

技术Passed：当前RTX4070 12GB环境能够用已安装的LTX 2B模型，在60FPS生成条件下新生成305帧并直接保存MP4，无外挂运动补帧或旧视频加速。5秒短镜头已跑通，不等同于模型训练覆盖60FPS、所有场景均可靠或高分辨率60FPS已验收。

新样片复用项目25的校园楼首帧1161、同一提示词和seed2026101912，与原24FPS任务1163比较；视频为新生成，没有复用旧视频作为60FPS结果。内容仍`NeedReview`，发布`Blocked`。抽帧可见镜头推进和叶片移动，但部分叶片/建筑细节仍有生成模型的柔化及变形，不能仅按帧数判断画质提升。

## 官方资料与本机依据

- [MiniMax H3官方规格](https://github.com/MiniMax-AI/MiniMax-H3#system-overview)列出24FPS，本机H3节点也按24FPS/17k+5帧网格处理。本轮没有改H3帧率；增加等待时间本身不能改变其输出规格。
- [LTX官方仓库](https://github.com/Lightricks/LTX-Video#april-15th-2025-new-checkpoints-v096)记录默认30FPS且支持其他帧率；其[推理实现](https://github.com/Lightricks/LTX-Video/blob/main/ltx_video/pipelines/pipeline_ltx_video.py)在生成时使用frame_rate缩放时间位置坐标。这不是官方承诺所有模型在60FPS均保持质量。
- 已安装ComfyUI `nodes_lt.py`的LTXVConditioning将frame_rate传入正负条件，`comfy/ldm/lightricks/model.py`的时间位置计算使用`1/frame_rate`。本次将条件和保存帧率同时设60，LTXVImgToVideo长度305（8×38+1）。
- 官方仓库[Issue264](https://github.com/Lightricks/LTX-Video/issues/264)有用户报告48FPS时质量/运动恶化，仅作为风险线索，不能当作所有模型的定论；本次因此使用独立实验契约与实机样片验证。

## 具体改动

1. 新增`ltx-native60-experiment-v1`契约，文件`ltx_native60_experiment_api.json`，只允许512×320/60FPS/305帧、单首帧、实验用途，禁止自动用于正式发布。原24FPS契约不改。
2. 模型仍为已固定的`ltxv-2b-0.9.8-distilled-fp8.safetensors`与T5 FP8，模型哈希沿用原LTX契约，没有换模型、下载权重或调用云API。
3. 流程`LTXVConditioning(60) → SamplerCustom → VAEDecode → CreateVideo(60) → SaveVideo(MP4)`；直接输出避免WEBP毫秒时间刻度量化。工作流SHA-256 `fcc0d08049351a2162c70ab6e6d13f2a720e26902235341633aa79bcb964491d`。
4. 新增准备/可续跑工具`tools/ltx60`，所有生成和交付均通过已有API/GenerationQueue，保存任务ID、首帧哈希、探针与断点；重复运行保留结果，不自动重试失败任务。
5. 修复WorkflowCatalog按文件名把新路线误分类为Image的问题：已登记契约的类型优先，未知工作流仍按原规则推断。初次预检422未创建任务；修复构建/发布、重新扫描后原工作流ID1204为ImageToVideo，再执行成功。

## 实际结果

硬件RTX4070 12282MiB、约31.8GiB内存；ComfyUI0.31.0、torch2.11/cu130，GPU并发1；沿用lowvram和原显存配置。

| 任务 | 实际输出 | 耗时 | 显存 | 技术结果 |
| --- | --- | ---: | --- | --- |
| 1169 | 新生成512×320/60FPS/305帧，5.083333秒，静音MP4 | 50.805秒 | 队列采样6808MiB；独立2秒采样峰值7663MiB | Passed |
| 1170 | 单段裁至5.000秒、1280×720展示/60FPS/300帧 | 3.136秒 | CPU任务 | Passed |

1170只做空间放大、留黑边和裁去末尾5帧，未用运动补帧；源画面依然512×320，因此720p展示尺寸不代表原生720p细节。此次没有把旧10秒视频替换成新样片，也没有验证10秒/更高源分辨率的60FPS负载。

验证：

- 从实际MP4内嵌prompt核对生成length305、frame_rate60、CreateVideo fps60、VAEDecode直接连线，无RIFE/插帧节点；不仅检查容器FPS字段。
- FFprobe完整数帧与FFmpeg全片解码Passed；原生305个解码帧校验全部不同、相邻完全重复0。校验差异本身不能证明每帧运动自然或无视觉伪影。
- Chrome完整播放5秒，解码300帧、droppedVideoFrames=0、pageerror=0。
- 13个工作流契约自检Passed，含文件/模型哈希和Guide/实验生产阻断；`.NET Release`构建/发布0警告0错误。
- 实际API检查5项Passed：新60路线有效预检；新路线24FPS、121帧、错误尺寸，以及旧24路线60FPS，均HTTP422且任务列表未增加。确认目录扫描后已登记类型与契约一致。
- 准备及生成工具再次运行Passed，未重复提交任务。既有服务/媒体保留，当前LocalOnly回环模式和单GPU队列不改。

## 产物与复现

原生视频：`C:\install\AI\Data\Artifacts\project-25\video\task-1169\v0001\v0001_task_1169_task_1169_attempt_1_7a511251_00001__e23290a0ff90.mp4`。

5秒预览：`C:\install\AI\Data\Artifacts\project-25\video\task-1170\v0001\v0001_campus_native60_experiment_5s_0233ce8038e5.mp4`。

状态及原生prompt/探针：`C:\install\AI\Data\LtxNative6020261018\run.json`；2秒显存采样同目录`gpu-samples.json`，59个样本，不是硬件连续瞬时峰值。抽帧同目录`comparison_contact.png`。

实际API/浏览器验证摘要：忽略目录`logs/native60-20261018`，不含密码/Token/Cookie/Key。

```powershell
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/ltx60/prepare.py
# 新契约需要当前服务；准备后通过工作台扫描工作流，登记类型以契约为准。
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/ltx60/run_experiment.py
```

当前只把这条路线作为明确选择的本地实验，不修改原24FPS默认。更高FPS不能单独补回低分辨率素材的细节；是否采用应结合动态画面、动作和清晰度复核。本轮无需API Key，没有付费云调用。

# 同人物同台词：纯本地10秒三镜头样片

用户已批准先优化对白与人物反应，再制作女方近景、男方反打、双人收尾。全部推理通过现有本地业务队列；保留上一版样片和本轮各候选。

<!-- dialogue-three-shot-evidence:start -->
更新于 `2026-10-23T15:42:55.606059+00:00`。

当前阶段：`ReadyForUserPreview`；技术状态 `Passed`；内容 `NeedReview`；发布 `Blocked`。
完成验收，已可供用户观看。

项目 `34`，当前分支 `main`，HEAD `d6ec38d076a8b0336d349c36df5c123f2c941ac8`。分支和提交来自本次实际 Git 查询；不代表工作区已提交。

### 对白与三镜头安排

| 句 | 人物/声音 | 原台词 | 成片时间（秒） | 选用任务/候选 |
|---|---|---|---|---|
| 1 | female/qwen3:Vivian | 哟，约会回来了？ | 0.4–2.079 | 1253 / 3 |
| 2 | male/qwen3:Dylan | 哼，要你管。 | 2.299–3.818 | 1252 / 2 |
| 3 | female/qwen3:Vivian | 好啦，不逗你了。 | 4.158–6.237 | 1249 / 1 |
| 4 | male/qwen3:Dylan | 这还差不多。 | 6.437–7.556 | 1250 / 1 |

非统一换人间隔：`[0.22, 0.34, 0.2]` 秒；原速原音高。只允许裁去句子外部低电平边缘，内部发音与停顿保持。
本地 ASR 提供文字核查证据，不能证明情绪、音色或口型表演已经正确。

| 镜头 | 构图 | 成片区间（秒） | 原生生成帧数/时长 |
|---|---|---|---|
| 1 | 女方近景 | 0–2.208 | 57 / 2.28 秒 |
| 2 | 男方反打 | 2.208–4 | 46 / 1.84 秒 |
| 3 | 双人收尾 | 4–10 | 151 / 6.04 秒 |

人物参考来自原始1536×864首帧1216的确定性裁图，保留同一对虚构成年人物；没有生成新的多视角身份图，也没有复用旧视频冒充新生成。
原生视频为832×480、25FPS。最终720P/24FPS是重新编排、缩放及可选细节修复后的交付规格，不能称为原生720P。
三个全新v1工作流复用既有Wan2.1 I2V Q4、InfiniteTalk Multi Q8、LightX2V蒸馏LoRA、wav2vec2、UMT5和VAE。6步、CFG1、blockswap30，GPU串行；本轮未改变旧服务超时规则。

### 实际任务与资源

| 任务 | 类型/资源 | 服务状态 | 实际耗时（秒） | 结果证据 |
|---|---|---|---|---|
| 1247 | Audio/GPU | Succeeded | 21.305 | `audio/line-1-task.json` |
| 1248 | Audio/GPU | Succeeded | 14.655 | `audio/line-2-task.json` |
| 1249 | Audio/GPU | Succeeded | 15.644 | `audio/line-3-task.json` |
| 1250 | Audio/GPU | Succeeded | 14.034 | `audio/line-4-task.json` |
| 1251 | Audio/GPU | Succeeded | 15.427 | `audio/line-1-attempt-2-task.json` |
| 1252 | Audio/GPU | Succeeded | 15.044 | `audio/line-2-attempt-2-task.json` |
| 1253 | Audio/GPU | Succeeded | 14.795 | `audio/line-1-attempt-3-task.json` |
| 1254 | ImageToVideo/GPU | Succeeded | 429.543 | `shot1Attempt1TaskId-result.json` |
| 1255 | ImageToVideo/GPU | Succeeded | 414.23 | `shot2Attempt1TaskId-result.json` |
| 1256 | ImageToVideo/GPU | Succeeded | 377.473 | `shot2Attempt2TaskId-result.json` |
| 1257 | ImageToVideo/GPU | Succeeded | 883.894 | `shot3Attempt1TaskId-result.json` |
| 1258 | Concat/CPU | Succeeded | 1.596 | `canvas1TaskId-result.json` |
| 1259 | Concat/CPU | Succeeded | 1.378 | `canvas2TaskId-result.json` |
| 1260 | Concat/CPU | Succeeded | 2.916 | `canvas3TaskId-result.json` |
| 1261 | Concat/CPU | Succeeded | 4.519 | `assemblyTaskId-result.json` |
| 1262 | VideoRestore/GPU | Succeeded | 538.406 | `restoreTaskId-result.json` |
| 1263 | Concat/CPU | Succeeded | 5.816 | `finalTaskId-result.json` |

已记录GPU任务耗时合计 `2754.450` 秒；CPU合计 `16.225` 秒，含保留候选，不含未完成任务。
资源采样 `586` 条：整卡采样显存峰值 `11182` MiB，系统最低可用内存 `130` MiB。这是采样值，不能视为进程精确峰值或连续监控。
已有完整起止时间的GPU任务最大重叠数：`1`；未完成任务不计入该值。

### 交付、核验与限制

成片：`Artifacts/project-34/video/task-1263/v0001/v0001_dialogue_three_shot_local_10s_1b677efb8f9e.mp4`。
SHA256：`1b677efb8f9ee23b866bd157cfb5607fce4485ea7935fa0c4337b0639d2d44d1`。
最终业务任务：`1263`。

`delivery-verification.json`：`Passed`，仅覆盖 `Technical export/audio integrity only`。
实际解码帧数 `240`，独立帧哈希数 `240`，旧媒体保持核验数 `2`。

实际浏览器播放记录：`Passed`，ended=`True`，muted=`False`，volume=`100`。

音频空间处理为程序合成的轻微单声道室内脉冲响应，不是录制环境声或实测房间响应；没有额外加入动作拟音。

细微情绪、真实感、身份连续性、视线反应、牙齿与逐音节口型仍需观看试听；技术Passed不能替代内容人工判断。
初次与修复候选全部保留，不把未选用或失败候选重命名为通过。本轮没有发布或云推理授权。

恢复时先读取 `Data/DialogueThreeShot20261023/run.json` 和 `audio/run.json`，核对已有任务ID。ReadyForUserPreview后仅核验旧结果，不自动新增生成。
详细机器证据：`Data/DialogueThreeShot20261023/execution-summary.json`；媒体、工作流、资源采样和验收JSON保存在同目录。
<!-- dialogue-three-shot-evidence:end -->

人工内容意见可附在此处；脚本仅替换上方限定证据区块。


<!-- three-shot-visual-decisions:start -->
### 实际画面选择与保留限制

- 镜头1实际检查57帧，19/19抽样有一张完整女性面孔；右缘保留男方前景头肩，属于过肩近景。
- 男方初次1255虽然技术Succeeded，但抬眼朝屏幕右，未选。1256使用同人物近景参考的水平镜像构图及新seed修复，抬眼朝屏幕左回应，选入成片。镜像同时反转窗光和发缝，是本次试看片的空间连续性折中；不是生成了新的真实反面视角。
- 双人1257实际151帧，51/51抽样有两张脸；女方先说、男方后答，末句后嘴收住，保留眨眼和目光变化。最后约一秒男方看向旁边，动作动机和2.44秒反应尾段仍需用户看效果。
- 实际六时点、九对面部区域对照后选择SeedVR2强度0.25，切点53/96帧分段。细节收益较轻，未在检查区域发现明显新增口眼几何异常；牙齿和肤质仍有生成平滑感。
- 静态检查、ASR和音轨相关性不能证明音素同步或情绪自然度通过。内容保持NeedReview，不虚构自然度分数。
- 最终全片240帧实际解码且哈希均不同，四句导出缺失语音样本均0；真实浏览器10秒未静音播放到结尾及7项定位通过。完成后已实测恢复不新增任务，服务在线、两队列空闲。

详细证据位于Data/DialogueThreeShot20261023：shot-1/2/3-review.json、shot-2-attempt1-review.json、restoration-comparison、delivery-verification.json、browser-final-playback.json、browser-seek-checks.json、final-runtime-and-resume.json。

<!-- three-shot-visual-decisions:end -->

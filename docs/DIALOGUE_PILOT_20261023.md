# 双人对白口型样片：纯本地执行记录

用户授权：2026-10-23，先做8–10秒男女双人对白，人物、台词、情绪和口型对应，完成后实际展示。生成、语音识别、修复和合成都在本机运行；只从公开仓库下载代码和固定版本权重，无云推理、无付费API。

## 已复现的问题

上版1236关闭H3原声，并将独立Qwen对白放在预设时间点，没有音频驱动口型。台词“犯规/叫姐姐”合并了原片不同角色的对白，通用情绪指令覆盖所有句子。旧版音轨比对仅证明导出完整性，不证明语义、角色、情绪或口型通过。

## 本轮锁定

- 左侧女性：长深色卷发、米色针织外套/浅色上衣，Vivian；右侧男性：短黑发、轻胡茬、橄榄绿外套/深色T恤，Dylan。
- 1 女：哟，约会回来了？——含笑打趣。
- 2 男：哼，要你管。——佯装不服，避免真生气。
- 3 女：好啦，不逗你了。——温柔让步。
- 4 男：这还差不多。——轻松满意。
- 实际Qwen任务1237–1240，2.00/1.44/2.56/1.12秒；原速、无裁剪，包含间隔的独立男女分轨均9.64秒，无非静音重叠。
- 使用项目32首帧1216作为角色参考，确定性裁切为双人中近景。旧视频不作为新生成结果。

## 流程与门槛

1. 四句Qwen分别设置情绪，CPU本地Whisper检查文本；ASR只能验证读词，不能验证听感。
2. InfiniteTalk Multi Q8 + Wan2.1 I2V 480P Q4_K_M，以两路音频及人物左右区域约束生成新画面。先125帧/25FPS短测，再241帧/25FPS整段，单GPU队列、maxRetries=0。
3. 实际检查两位人物身份、轮流开口、倾听反应、嘴唇与声音关系。失败只修失败段，初次加最多两次定向修复；不把检查路由通过当作口型通过。
4. 内容可继续后，业务队列进行最终合成与适量细节处理；技术/内容/发布状态分别记录。原1236保持不覆盖。

## 固定环境和依赖

- Windows，RTX4070 12281MiB，系统RAM32GB；main/d6ec38d076a8b0336d349c36df5c123f2c941ac8，保留既有脏改动，不提交/推送。
- 已有ComfyUI0.31.0、Python3.13.2、Torch2.11.0+cu130、Qwen3-TTS和FFmpeg复用。
- 新增ComfyUI-WanVideoWrapper固定提交088128b224242e110d3906c6750e9a3a348a659b；原环境包清单已存Data/DialoguePilot20261023/comfy-packages-before.txt。
- 新增VideoStudioDialogue节点：人物区域掩码；复用现有scaled UMT5的原生编码和磁盘缓存；先释放文字编码器再加载视频模型，减少CPU内存同时驻留。
- 五项模型来源、revision、尺寸和SHA256见Data/DialoguePilot20261023/model-manifest.json。部分传输经断点范围下载完成后才校验、发布文件。
- 新ASR为faster-whisper-small CPU INT8，原始官方转换仓库Systran/faster-whisper-small固定revision536b0662742c02347bc0e980a01041f333bce120。

## 当前状态与恢复

项目33，四项TTS任务已Succeeded；音频角色分轨/覆盖/混合完整性Passed。首次GPU短测1241实际输出153帧/6.12秒，因预期125帧而正确Failed；未修改失败状态。通过真实业务CPU裁切任务1242得到精确5.0秒/125帧，已逐帧对照角色说话切换；42/42抽样均检测到两张脸。新v2工作流在CreateVideo前增加ImageFromBatch精确帧裁切，旧v1合同已退役到Data/DialoguePilot20261023/legacy-windowed-contracts.json。原图表、实际Comfy历史和原始失败输出保留。完整任务1243运行中，内容和发布尚未通过。

恢复先读`C:/install/AI/Data/DialoguePilot20261023/run.json`和已有任务详情；模型下载用bootstrap.py断点继续，配音/视频用run.py已记录任务ID恢复，提交结果不明确时禁止重复提交。五项模型缺失或哈希错误时不提交推理。不得把旧媒体作为本轮生成证明。

上游资料：[InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk)、[WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper)、[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)。模型宣称不等于本机验收结果。


## 短测观察与技术修复

- 1241 Comfy prompt03309f43-99e4-4dd4-84c8-4d69f274ec33真实完成采样，原生153帧，应用帧数QA正确拒绝；不把失败记录改成Succeeded。
- 1242复用这段本轮新生成的输出，CPU队列裁取前125帧，未追加GPU推理。
- 观察表：女方0.48秒开口、约0.96秒停顿、1.92秒继续；男方2.88/3.84秒开口；男方说完闭口，女方4.8秒接话。脸/衣服/房间/手部保持稳定。嘴部地标仅作辅助，不作音素级准确率。
- 实际样本见Data/DialoguePilot20261023/inspection-125/contact.jpg、speaking-faces.jpg及review.json。
- 仅两个新exact工作流的GPU时限为120分钟，CPU/普通GPU/VideoRestore原时限不变。两版合同自测、队列租约静态回归及实际重启后任务持续可读均Passed。
- 完整样片沿用832×480/25FPS源参数；短测已接近12GB显存与32GB内存余量，先解决声画对应，再做保守720p细节处理。


<!-- pilot-delivery:start -->
## 实际最终交付

- 文件：`C:\install\AI\Data\Artifacts\project-33\video\task-1246\v0001\v0001_two_person_dialogue_local_9.5s_8931528782f6.mp4`
- SHA256：`8931528782f6389cc76c5693eb11a9b2a87af6482383255b52e84cf75526c053`
- 实测1280×720、24FPS、228帧、9.5秒，四句台词均完整原速；末句8.78秒结束，仅去掉0.14秒静音尾部。
- 技术验收Passed：全片解码、逐句及完整音轨相关性、实际浏览器从头到尾未静音播放；旧1236/参考片/旧run哈希保持。
- GPU任务按实际起止记录最大并发1；GPU合计3218.804秒，含保留的初次失败短测。约5秒采样整卡峰值11461MiB、最低可用RAM325MiB。
- 混音按句平衡音量，第三句保留较轻语气；添加极低电平本地生成室内底噪和轻微早期反射，不改变对白时机和语速。
- 声画精细效果保留人工复核，内容NeedReview、发布Blocked；不把路由或地标数值当成音素准确率。
- 分支main，HEAD d6ec38d076a8b0336d349c36df5c123f2c941ac8，未提交/推送；既有脏改动保留。

| 任务 | 阶段 | 实际状态 | 秒 |
| --- | --- | --- | --- |
| 1237 | line1TaskId | Succeeded | 34.637 |
| 1238 | line2TaskId | Succeeded | 14.424 |
| 1239 | line3TaskId | Succeeded | 16.600 |
| 1240 | line4TaskId | Succeeded | 13.789 |
| 1241 | video125TaskId | Failed | 942.125 |
| 1242 | testTrimTaskId | Succeeded | 1.514 |
| 1243 | video241TaskId | Succeeded | 1697.664 |
| 1244 | canvasTaskId | Succeeded | 4.091 |
| 1245 | restoreTaskId | Succeeded | 499.565 |
| 1246 | finalTaskId | Succeeded | 6.206 |

恢复使用`tools/dialogue_pilot/run.py --stage check`；Ready状态只读核验现有路径与SHA，不生成新任务。原生测试1241保持Failed；实际5秒结果来自CPU裁切1242，其余本轮成功任务分别可追溯。
<!-- pilot-delivery:end -->

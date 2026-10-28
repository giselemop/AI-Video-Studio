# H3原生1080p校园实验

日期：2026-10-19至20（Asia/Shanghai）。用户明确授权在本机试生成一段原生1080p样片；本次为默认12GB规则的单独实验例外，不修改原480p/768p/LTX路线。分支main，HEAD d6ec38d；保留既有未提交修改，不提交/推送。

## 当前真实状态

修复后的1178已Succeeded，技术Passed：原生1920×1088采样后上下各裁4行，实际交付1920×1080、24FPS、124帧、视频5.166667秒，H.264及原生音轨、独立WAV可用。实际抽帧和浏览器呈现可见向入口靠近及枝叶变化；枝叶仍有涂抹和局部细节重绘，砖缝/窗框也有几何不稳，不能将输出像素增加等同于有效细节或商业模型质量。内容NeedReview、发布Blocked。

首轮1177采样及解码后在保存节点失败，记录保留为Failed，未改为成功。当前实验已完成；接续先读中央Data的H3Native108020261019/active-attempt.json与attempt-2/run.json，并查询真实队列，不能删除报告或重新提交已完成任务。不自动追加第三轮。

## 固定规格与输入

- 本机RTX4070 12282MiB、约31.8GiB系统内存，既有H3 FL2VA Q4_0、Qwen Q2_K_M、FP16视频VAE及FP32音频VAE，固定四模型清单/哈希及加载器版本不变。GPU并发1，CPU并发1，最低可用显存1024MiB，无收费云API，无新模型下载。
- 项目26，profile `native1080`，工作流1319：`minimax_h3_local_1088_i2v_api.json`。原生条件1920×1088、124帧、24FPS、20步、seed2026101841。ImageCrop上下各裁4行，直接输出1920×1080；没有成片空间超分或运动补帧。交付视频约5.166667秒，H.264 CRF16，保留原生音轨及独立WAV。
- 明确复用1173已选首帧：SHA256 `534d788b55e535cdb813ab80a766971d88f81d7ee073f636a122e873b3d1177e`。该首帧源于SD1.5合成图，经RealESRGAN x2准备为1376×768，不能称为原生1080p摄影素材。视频生成画布独立为1920×1088，不能将输入参考的预处理混同于成片超分。
- 与旧运动版1176对照：同一首帧/seed，镜头前移描述从约两米改为约一米，枝叶从强风运动改为较慢大簇摆动；取消“natural motion blur”，新增短曝光观感和清晰枝叶轮廓提示。提示词是意图，不是真实快门参数，不能保证消除模型重绘/运动模糊。
- 本轮同时改变分辨率、运动提示词和编码质量；不能把输出差异全部归因于分辨率，不能将实际像素数量等同于有效细节或与商业模型等效。

## 执行保护与代码

- 只对显式native1080开放1920×1088；普通H3继续限制32对齐、最大1376×768、124帧和24FPS。受管profile/工作流/固定参数混用会被拒绝；模型哈希、源码与中央工作流一致性、首帧追踪、正式生产禁入保持。
- `ComfyUiClient.PatchWorkflow`保留native1080的ImageCrop尺寸，防止任务height=1088覆盖交付裁切height=1080。H3 QC按最终1920×1080、24FPS、124帧检查，另记原生画布及裁切审计。
- 首轮原生1080服务期限120分钟；修复后独立期限180分钟；原视频30分钟及CPU期限不变。自动重试0，OOM不自动降帧数/分辨率。新脚本有文件锁、稳定幂等键和提交结果未知保护；先查询已保存任务再接续。
- 原VAEDecode保留：本机H3 VAE内部有自己的时空分块，通用VAEDecodeTiled参数会被H3实现忽略，不能将切换通用节点当作已验证的显存优化。
- `tools/minimax/run_native1080.py`生成、规格/全片解码/内嵌graph核验及保留旧片哈希；`review_native1080.py`生成新旧实际抽帧和像素变化诊断；后者不是画质打分。
- `web/public/h3-native1080-compare.html`新旧并排播放，明确分辨率、提示词同时变化。真实媒体测试两项Passed；夹具和实际生成结果分开记录。

## 当前已完成检查

- .NET Release构建和发布Passed，0警告/0错误；H3回归24项、MiniMax固定路线26项Passed。
- Vue生产构建Passed，既有PURE注释及大chunk提示保留；6项MiniMax UI夹具Passed，含默认480p保持与显式native1080/裁切提示。夹具不写真实队列。
- 新Python脚本编译Passed；6项真实API预检Passed：允许native画布，拒绝错工作流、错profile、1080未对齐条件、60FPS和121帧。预检不提交GPU任务。
- 启动前API/Comfy均离线、服务最新任务1176 Succeeded；恢复既有环境，确认两队列无任务后只提交1177。Comfy新日志单独保存于 `logs/native1080-20261019`，原输出和日志保留。

实际生成和浏览器播放现已完成，详细结果如下；内容NeedReview、发布Blocked。当前无需API Key。

## 首轮保存故障与修复

首轮1177已执行全部H3采样、音视频解码、裁切及CreateVideo节点，最终SaveVideo报 `missing required positional argument: codec`。API预检通过不能证明V3动态输入的嵌套对象能正确展开；原设置误把execute接收的对象格式当作API graph格式。已改为codec=h264、codec.encoding=re-encode、codec.encoding.crf=16三个展开字段，并加入native1080策略拒绝错误嵌套对象。原中央工作流SHA256 acbf10e191ef9b666d38c11f6f639dc85b51c2030b73e773bab41b0589e84689已备份至attempt-1/failed-workflow.json；新工作流SHA256 ab75326f3825760d40f52e65279595b88fd28dcfe2baac1fc41e9cc8ee7c6288。

新增tools/minimax/test_save_video_protocol.py，在CPU上复现错误并通过实际Comfy V3输入展开/SaveVideo执行，写入124帧、1920×1080、24FPS及音轨的编码夹具，FFprobe核验Passed。夹具在Data/acceptance，仅为协议测试，不是用户校园视频。队列finally的free_memory会令Comfy清空节点缓存，无法补存首轮画面；查询确认1177 Failed且两队列空闲后，才通过原业务API创建第二轮1178。没有手改任务状态、直接提交Comfy prompt或用旧视频冒充新样片。新run --attempt 2先验证前次任务真实Failed并核对当前编码协议夹具；仍保留稳定幂等键、提交未知保护和maxRetries=0。

首轮独立资源采样3347个，显存峰值11910MiB、最低可用内存30MiB，均为约2秒采样值。失败Comfy历史在failed-comfy-history.json，原run.json/resource-samples.json保持；新资源/报告在attempt-2。修复构建/发布及24项H3、26项MiniMax回归Passed，Comfy进程未重启，前次失败没有被改为成功。

## 第二轮真实结果与画质检查

- 1178开始于2026-10-20 01:32:29.168，结束于02:59:05.038，服务时长5195.870秒（86分35.870秒）。与首轮6855.795秒合计12051.665秒（3小时20分51.665秒），不含排查/发布/两轮间隙。修复只改变保存协议和执行时限；两轮速度差不能归因于编码修复，缓存、系统负载和内存状态未控制。
- 整卡约2秒采样2532个，峰值11852MiB；队列采样峰值11842MiB。最低采样可用系统内存14MiB，加载阶段内存压力很大；这些不是连续瞬时峰值，也不是仅本进程占用。完成后GPU已空闲、服务与Comfy队列无运行/待执行任务。
- 实际数帧124、24/1、1920×1080、视频5.166667秒，完整解码Passed；内嵌graph核对1920×1088原生条件、裁切坐标、20步/seed/首帧哈希及CRF16展开字段，未接入成片超分或补帧。H.264视频码率约36.3Mbps，不能把更大码率当作画质结论。
- 新旧各124个解码帧且各不相同。新灰度相邻帧平均变化13.8941，旧768p运动版12.9575；0.5秒与4.5秒差61.1894/57.3234。仅为像素变化诊断，不是画质分、动作自然度分或提升百分比。
- 0.5/2.5/4.5秒联系图和完整2.5秒帧中可见前移，枝叶仍有涂抹、纹理重绘，局部砖缝和窗框不稳定。分辨率、提示词、编码同时变化，不能把差异全部归因于分辨率；未认定达到公开视频或Seedance同等质量。
- 两项真实浏览器检查Passed：实际尺寸/时长、循环回绕、播放/暂停、同步定位、实际呈现3.5秒帧、无JS错误及非法路径拒绝。截图在attempt-2/browser-comparison.png，联系图在native1080-contact.png。
- 完成后再次运行run_native1080.py --attempt 2，只查询1178及已有产物；前后最近任务ID序列一致，无新GPU提交（resume-check.json Passed）。原首帧/1174/1175/1176均保留，比较前后哈希核对；默认本地路线不变。
- 最终Vue生产构建Passed，既有PURE注释和大chunk提示仍在；修复后的.NET构建/发布0警告0错误、24项H3及26项MiniMax回归Passed；新脚本编译、完整有声1080p CPU编码夹具Passed。6项MiniMax UI夹具与6项实际预检在本轮通过，最后的已验证说明文案更新后重新构建。

视频：`C:\install\AI\Data\Artifacts\project-26\video\task-1178\v0001\v0001_task_1178_task_1178_attempt_1_a2eaccfc_00001__eb6327de9b52.mp4`。

WAV：`C:\install\AI\Data\Artifacts\project-26\audio\task-1178\v0001\v0001_native_audio_task_1178_d580daa4aae4.wav`。

新视频SHA256：`eb6327de9b5291baa16e51476822e60d6288d551c4abe25cc6bf27619cb97d15`；旧1176 SHA256：`bee4b38f85cbb1418fe1cfc638d316476c46fb853c7984f4030f195e5b3c0319`。

对照地址：[http://127.0.0.1:18080/h3-native1080-compare.html?before=Artifacts%2Fproject-26%2Fvideo%2Ftask-1176%2Fv0001%2Fv0001_task_1176_task_1176_attempt_1_e1f16d1d_00001__bee4b38f85cb.mp4&after=Artifacts%2Fproject-26%2Fvideo%2Ftask-1178%2Fv0001%2Fv0001_task_1178_task_1178_attempt_1_a2eaccfc_00001__eb6327de9b52.mp4](http://127.0.0.1:18080/h3-native1080-compare.html?before=Artifacts%2Fproject-26%2Fvideo%2Ftask-1176%2Fv0001%2Fv0001_task_1176_task_1176_attempt_1_e1f16d1d_00001__bee4b38f85cb.mp4&after=Artifacts%2Fproject-26%2Fvideo%2Ftask-1178%2Fv0001%2Fv0001_task_1178_task_1178_attempt_1_a2eaccfc_00001__eb6327de9b52.mp4)。

当前CPU/编码修复、真实生成及播放均已完成；只有本次约5秒校园短镜头通过技术验收，运动自然度、内容和声音仍等待用户观看。无需API Key，不自动继续新的GPU实验。

最终工作区检查Passed：main/HEAD d6ec38d，193个未提交路径保持；23个本轮相关文件高置信秘密扫描无命中，git diff --check通过，所有未跟踪文件递归检查未发现新媒体或权重。四个原始输入/视频哈希复核一致；数据库、Comfy及FFmpeg在线，两队列空闲。检查证据为attempt-2/workspace-check.json；本轮未提交/推送。

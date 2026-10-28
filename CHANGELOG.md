<!-- character-turn-repair-20261027:start -->
> 2026-10-27：林安左转回正定向修复已交付，原任务1550、新项目53/任务1551。沿用人物版本3、已批准参考36、同H3工作流和种子；原生864×480/24FPS/124帧。19项媒体来源及两个真实浏览器完整播放Passed；25时点试片检查可见左转、停顿、回正，转幅接近侧脸，人物细节和自然度NeedReview、发布Blocked。仅1次定向修复，无新模型/新人物版本/人工批准/云调用；原片及双人剧情待审检查点保留。恢复Data/CharacterTurnRepair20261027/run.json，completed=true禁止重复提交。 [验收报告](docs/CHARACTER_TURN_REPAIR_20261027.md)、[视频对照](http://127.0.0.1:18080/character-turn-repair.html)。
<!-- character-turn-repair-20261027:end -->

<!-- character-single-preview-20261027:start -->
> 2026-10-27：用户新请求的独立单人动作试片已交付，项目52/任务1550，林安旧版#3、已批准正面参考36；864×480/24FPS/124帧，技术Passed，助手动作检查Failed（实际眨眼和头部回正，定向左转未明显命中），人工内容NeedReview、发布Blocked。仅一个新视频，无新图/新版本/模型/云调用；原双人剧情检查点与保持待审指示不变。恢复Data/CharacterSinglePreview20261027/run.json，completed=true禁止重复生成。 [验收报告](docs/CHARACTER_SINGLE_PREVIEW_20261027.md)、[本次视频](http://127.0.0.1:18080/character-single-preview.html)。
<!-- character-single-preview-20261027:end -->

<!-- character-scene-20261027:start -->
> 2026-10-27: Fixed-room scene snapshots and explicit Shot bindings delivered for project51/episode36. Four real keyframes1522–1525: file/provenance Passed; three content inspections Failed, one PreviewInspection Passed. 46.5% protected background is pixel-identical to original1514; no identity or semantic score implied. User explicitly requested review hold. No new repair image, H3 clip or composite submitted; content NeedReview/publication Blocked. Backend24, initial API25, current regression45, media71, frontend5 groups and browser13 checks Passed. main/d6ec38d, uncommitted. No new models/cloud calls; independent character-repair work preserved. [Acceptance](docs/CHARACTER_SCENE_CONTINUITY_20261027.md). Checkpoint Data/CharacterScene20261027/run.json, generationHold.active=true; do not auto-resume.
<!-- character-scene-20261027:end -->

<!-- character-prompt-repair-20261027:start -->
> 2026-10-27：人物参考提示词统一为character-anatomy-v2，7人63槽逐张目检，16张新修复候选＋47张原图。24个真实本地任务/8张方向失败候选保留排除；556项媒体来源、100项跨语言提示词、12项实际API、16项人物库自测及63图真实浏览器加载Passed。技术/助手可见缺陷检查Passed；细节内容NeedReview，发布Blocked。无自动批准、新库冻结、新模型、云调用或视频；旧原图/检查点/5个不可变版本保留。新图在候选中待用户复核，旧拒绝版本不会被伪装成可用。恢复Data/CharacterReferenceRepair20261027/run.json，completed=true禁止重复生成。见[验收报告](docs/CHARACTER_PROMPT_REPAIR_20261027.md)、[63图汇总](http://127.0.0.1:18080/character-reference-repair.html)。
<!-- character-prompt-repair-20261027:end -->

<!-- character-story-20261027:start -->
> 2026-10-27：人物参考库与剧情流程增量开发及有限真实验证已交付。技术Passed，人工内容NeedReview，发布Blocked。010/011已由管理员执行并实测就绪；项目50/集34固定林安#4、周言#5，4个基础视频＋定向修复及预览任务1521完成技术检查。执行中重启1516沿用原Comfy执行，无重复生成。旧版本/媒体/五人原检查点保留；40张扩充候选待审、缺5个前侧槽位，未批准或批量试片。无新模型/云付费/发布；自动实施已完成，无周期重跑。见[验收与待审清单](docs/CHARACTER_STORY_ACCEPTANCE_20261027.md)、[四镜头播放](http://127.0.0.1:18080/character-story-preview.html)。
<!-- character-story-20261027:end -->

<!-- character-reference-pack-20261026:start -->
> 2026-10-26: Completed project47 reference packs: LinAn v3 and ZhouYan v2 each freeze three face close-ups and six full-body angles, with independent view/framing and immutable wardrobe/body snapshots. 122 live API, 214 media/provenance, 19 browser UI checks and two complete browser playbacks Passed; content NeedReview and publication Blocked. GPU concurrency1; no new models/cloud calls. Existing versions/artifacts retained. Data/CharacterReferencePack20261026/run.json completed=true prevents duplicate generation. [Acceptance](docs/CHARACTER_REFERENCE_PACK_20261026.md).
<!-- character-reference-pack-20261026:end -->

<!-- character-library-20261026:start -->
> 2026-10-26：两个人物模型库与视频调用已完成技术验收，项目46。林安/周言各两张新参考，复用不可变人物版本；四个双视角镜头及一条真实工作台提交的新版本视频全部Succeeded，均864×480/24FPS/124帧。73项实际API与55项媒体/来源核验Passed，五条真实浏览器完整播放Passed。人物自然度仍需人工复核，发布Blocked。无新模型、无云调用、GPU并发1；原媒体与模型保留。入口[人物库](http://127.0.0.1:18080/#character-library)、[验收样片](http://127.0.0.1:18080/character-library-preview.html)。恢复Data/CharacterLibrary20261026/run.json，completed=true禁止重复提交。见[实施与验收记录](docs/CHARACTER_LIBRARY_20261026.md)。
<!-- character-library-20261026:end -->

<!-- dialogue-eye-hair-20261025:start -->
> 2026-10-25纠正：项目43女方7.9–8.1秒侧脸眼部浅色块/头发双边内容复核Failed，原技术Passed不等于画面正确。项目44保守修复已完成，1366×768/24FPS/240帧；女方双人镜头固定眼睛、头发和头部，仅保留原对白嘴部动作。目标眼发复核与技术Passed，完整自然度仍需复核，发布Blocked。原声/字幕/53与96帧切点/旧版和模型保留。对比http://127.0.0.1:18080/dialogue-eye-hair.html；恢复Data/DialogueEyeHair20261025/run.json，completed=true禁止重复提交。见[执行记录](docs/DIALOGUE_EYE_HAIR_20261025.md)。
<!-- dialogue-eye-hair-20261025:end -->

<!-- dialogue-stable-768-20261025:start -->
> 2026-10-25：项目43稳定768p完整十秒已完成，1366×768/24FPS/240帧，技术Passed；整体表演仍需用户复核，发布Blocked。修复开头连眨和4秒姿态跳变，确定性小样57帧重复像素一致；身体/手/手机偏静仍保留为限制。原声、四句字幕、53/96帧切点、旧版和模型保留。对比http://127.0.0.1:18080/dialogue-stable.html；恢复Data/DialogueStable20261025/run.json，completed=true禁止重复提交。见[执行与验收记录](docs/DIALOGUE_STABLE_768_20261025.md)。
<!-- dialogue-stable-768-20261025:end -->

<!-- dialogue-sync-full-20261025:start -->
> 2026-10-25：项目42完整十秒口型与双人回应，阶段ReadyForUserPreview。已完成，技术Passed，内容NeedReview，发布Blocked；新对比http://127.0.0.1:18080/dialogue-sync-full.html。全程本地、GPU并发1，项目40十秒版及模型保留。恢复Data/DialogueSyncFull20261025/run.json，先查已登记任务，禁止重复提交。见[执行记录](docs/DIALOGUE_SYNC_FULL_20261025.md)。
<!-- dialogue-sync-full-20261025:end -->

<!-- dialogue-sync-20261025:start -->
> 2026-10-25：项目41口型与双人回应小样，阶段ReadyForUserPreview。已完成，技术Passed，内容NeedReview，发布Blocked；新对比http://127.0.0.1:18080/dialogue-sync.html。全程本地、GPU并发1，项目40十秒版及模型保留。恢复Data/DialogueSync20261025/run.json，先查已登记任务，禁止重复提交。见[执行记录](docs/DIALOGUE_SYNC_20261025.md)。
<!-- dialogue-sync-20261025:end -->

<!-- dialogue-visual-20261025:start -->
> 2026-10-25：项目40十秒对话画面升级，阶段ReadyForUserPreview。已完成，技术Passed；内容NeedReview，发布Blocked。原四句对白/声轨/字幕、53/96帧切点和旧版本保留，原队列恢复。新对比：http://127.0.0.1:18080/dialogue-visual.html。恢复Data/DialogueVisual20261025/run.json，先查已登记任务，禁止重复提交；见[执行记录](docs/DIALOGUE_VISUAL_20261025.md)。
<!-- dialogue-visual-20261025:end -->

<!-- visual-targeted-20261024:start -->
> 2026-10-24定向画面修复小样已交付，项目39，任务1322–1325：局部眨眼残差、同条件H3分时段闭口、源频段皮肤回补。技术与真实页面Passed；眨眼闭合及中段表情改善，皮肤收益较轻，内容NeedReview，发布Blocked。全本地、无新增模型，旧模型/版本/成片保全；原队列恢复。恢复Data/VisualTargeted20261024/run.json，只读不重生成。见[验收记录](docs/VISUAL_TARGETED_20261024.md)、[本机新对比](http://127.0.0.1:18080/visual-targeted.html)。
<!-- visual-targeted-20261024:end -->

<!-- visual-validation-20261024:start -->
> 2026-10-24画面小验证包已交付，项目38。六张新Klein关键帧、H3首帧/首尾双帧动作对照、两秒LivePortrait重演及选片QHD对照已完成。文件技术与真实页面验收Passed；身份、自然度和画面偏好NeedReview，发布Blocked。LP使用旧自有生成素材驱动，不是新真人表演；QHD为后期超分。旧模型元数据与冻结原片SHA保全，原队列已恢复此前状态。恢复Data/VisualValidation20261024/run.json，仅核验，不重复生成。见[执行与验收记录](docs/VISUAL_VALIDATION_20261024.md)，[本机对比](http://127.0.0.1:18080/visual-validation.html)。
<!-- visual-validation-20261024:end -->

<!-- face-acting-20261024:start -->
> 2026-10-24：项目37同人物参考/表情重建已交付，最终任务1306实际2560×1440/24FPS/240帧/10秒。两秒原声短测、三镜头重生成、逐镜头SeedVR2与原AAC完整接回已执行；技术Passed，人物自然度与口型仍待用户复核，发布Blocked。恢复Data/FaceActing20261024/run.json为ReadyForUserPreview，只核验、不重复生成；原版、旧2K和旧肤质小样保留。 见[本轮记录](docs/FACE_ACTING_20261024.md)。
<!-- face-acting-20261024:end -->

<!-- skin-pilot-20261024:start -->
> 2026-10-24：项目36两秒局部肤质与跨帧稳定小样已交付，最终任务1281实际2560×1440/24FPS/48帧/2秒。取原片5–52帧，完整保留“哟，约会回来了？”，原版/当前2K/优化版使用同一原声片段；技术Passed，肤质收益较轻、内容待用户复核，发布Blocked。原嘴部/眼睛/非皮肤区域在编码前逐像素保持；不宣称恢复真实毛孔。恢复Data/SkinPilot20261024/run.json为ReadyForUserPreview，仅核验、不重复提交。 见[本轮记录](docs/SKIN_PILOT_20261024.md)。
<!-- skin-pilot-20261024:end -->

<!-- seedvr2-dialogue-2k-20261024:start -->
> 2026-10-24：项目35，同人物/同四句台词的10秒三镜头 SeedVR2 逐镜头2K修复，目标2560×1440（QHD）/24FPS/240帧，阶段：成片与对比可供用户观看。技术Passed；内容待用户复核，发布Blocked。原1263与声轨、切点保留，无新增表演或配音；不是原生2K生成或H3官方再生成。恢复Data/Dialogue2KSeedVR220261024/run.json，按已登记任务续接，不重复提交。 见[本轮记录](docs/SEEDVR2_DIALOGUE_2K_20261024.md)。
<!-- seedvr2-dialogue-2k-20261024:end -->

<!-- h3-regenerate-2k-audit-20261024:start -->
> 2026-10-24：H3-Regenerate-2K 纯本地可部署性核查 Passed；官方模块尚未开源，现有 Full 2K Workflow 实际调用认证云 API，因此官方本地接入与同人物/同台词 10 秒三镜头 2K 样片 Blocked。补查社区 MMH3Tools 为非官方复现，需更高版本 ComfyUI/Ref2VA 等，未在本机执行，不能声称等效或可运行。本轮 GPU/云推理/权重下载均 0；原 1263 和既有源码/工作流保留。证据 Data/H3Regenerate2KAudit20261024/audit.json。见[核查报告](docs/H3_REGENERATE_2K_AUDIT_20261024.md)。
<!-- h3-regenerate-2k-audit-20261024:end -->

<!-- dialogue-three-shot-20261023:start -->
> 2026-10-23交付：项目34同人物、同四句台词的纯本地三镜头样片，最终任务1263实际1280×720/24FPS/240帧/10秒。先调整Qwen逐句语气与非统一停顿，再生成女近景、男反打、双人收尾；原生832×480/25FPS，720P为后期交付。最终技术和真实浏览器完整播放Passed；情绪/人物反应/精细口型仍待用户复核，发布Blocked。GPU任务耗时合计2754.450秒（含保留候选），采样显存峰值11182MiB。恢复Data/DialogueThreeShot20261023/run.json为ReadyForUserPreview，仅核验、不重提。 见[本轮记录](docs/DIALOGUE_THREE_SHOT_20261023.md)。
<!-- dialogue-three-shot-20261023:end -->

<!-- dialogue-pilot-20261023:start -->
> 2026-10-23交付：项目33双人对白样片，最终任务1246实际1280×720/24FPS/228帧/9.5秒，全程本地Qwen分角色/逐句情绪、InfiniteTalk双音轨及人物区域驱动、细节处理和混音字幕。四句完整原速对白、解码/音轨/真实浏览器完整播放Passed；内容待用户复核、发布Blocked。初次短测1241帧数Failed保留，CPU1242精确裁取；v2保存前裁帧已修复。恢复Data/DialoguePilot20261023/run.json为ReadyForUserPreview，只核验、不重提。 见[本轮记录](docs/DIALOGUE_PILOT_20261023.md)。
<!-- dialogue-pilot-20261023:end -->

<!-- douyin-reference-20261023:start -->
> 2026-10-23交付：项目32男女双人客厅剧情，最终任务1236实际1280×720/24FPS/744帧/31秒，六段H3原生1376×768/20步、实际尾帧续接，11句Qwen男女声原速完整接入。完整解码、逐句音轨比对和真实浏览器完整播放Passed。开场改为回家后落座，衣服/站位跟随实际新角色；精细肢体与口型仍NeedReview，发布Blocked。恢复Data/DouyinReference20261023/run.json为ReadyForUserPreview，仅核验现有文件/任务，不自动重生成。见[本轮记录](docs/DOUYIN_REFERENCE_20261023.md)。
<!-- douyin-reference-20261023:end -->

<!-- realistic-i2v-resume-20261022:start -->
> 2026-10-23 delivered: Pure-local realistic preview technical Passed. Project31 final1215 is1920x1080/24FPS/240frames/10s with complete Qwen narration. Reference1211, controlled20/30-step sources1212/1213, selected30-step actual-tail continuation1214, and single-pass final all Succeeded. Full decode, audio correlation and real browser playback Passed. Content NeedReview, publication Blocked; hands/skin remain imperfect. Three video jobs12h13m43.198s, CPU export5.886s. Sampled VRAM11867MiB/minimum available RAM22MiB. API27676/Comfy29860 healthy, queues idle. Prior media preserved; main/d6ec38d, uncommitted. Resume Data/RealisticI2V20261022/run.json ReadyForUserPreview; verify existing assets only. See[report](docs/REALISTIC_I2V_20261022.md).
<!-- realistic-i2v-resume-20261022:end -->

<!-- realistic-i2v-20261022:start -->
> History: The2026-10-22 reference blocker was resolved after explicit user continuation. Final1215 was delivered2026-10-23; the current delivery status above is authoritative.
<!-- realistic-i2v-20261022:end -->

<!-- seedvr2-20261022:start -->
> 2026-10-22: Video detail optimization Passed technically. Project30 delivers task1206: 1920x1080, 24FPS, 240 frames, 10 seconds with complete Qwen narration. One-pass export1201 and SeedVR2 GPU trials1203/1204 preserve the old sources. An audio packet tail defect was fixed by lossless CPU remux1205/1206; decoded video frames and AAC payloads match their respective sources. Full restoration1262.216s; sampled device peak9424MiB. Actual API30 and browser3 checks Passed. Content NeedReview; publication Blocked. Resume Data/SeedVR2Enhancement20261022/run.json (ReadyForUserPreview); verification submits no new task. API33496, Worker enabled, idle queues. main at d6ec38d076a8b0336d349c36df5c123f2c941ac8; existing dirty work preserved, no commit/push. See [report](docs/VIDEO_DETAIL_SEEDVR2_20261022.md).
<!-- seedvr2-20261022:end -->

# AI Video Studio 变更记录

<!-- qwen3-video-20261022:start -->
> 2026-10-22：新增Concat音轨tempo及预检/执行验证，原音频作为独立资产保留。全新1198/1199画面经1200合成准确10秒，接入1.32倍速的完整Qwen旁白。新增声画预览页和实际帧/音轨/浏览器验证、来源与恢复证据；技术Passed，内容NeedReview。 见[本轮记录](docs/QWEN3_VIDEO_10S_20261022.md)。
<!-- qwen3-video-20261022:end -->

<!-- qwen3-tts-20261022:start -->
> 本地配音增加Qwen3-TTS 1.7B-CustomVoice、声音工作台、演绎指令、受GPU互斥保护的离线推理、版本绑定与缓存、音频试听/下载及配音历史。项目28/任务1196实际生成和播放Passed；1197缓存验证Passed。 详见[本地配音报告](docs/QWEN3_TTS_LOCAL_20261022.md)。
<!-- qwen3-tts-20261022:end -->

<!-- campus-story-20261021:start -->
> 2026-10-21：校园剧情《遗落的笔记本》项目27已生成并通过技术验收（Passed）。五段新视频1189/1190/1191/1193/1194均Succeeded，以真实尾帧逐段续接；CPU合成1195 Succeeded，实际1920×1080、24FPS、620帧/25.833333秒，含5段本地中文System.Speech旁白和烧录字幕。H3原生1920×1088仅上下各裁4行，无超分/插帧/旧样片填充。完整解码、2项真实浏览器测试（完整播放/五章节跳转/路径拒绝）、接续不重提及旧1178/1180哈希核对Passed。成片已ReadyForUserPreview，内容仍NeedReview、发布Blocked：远景手部交接部分遮挡，精细脸部/手指仍有AI痕迹，末段推进不明显、离场短暂。五段视频GPU任务合计7小时49分28.199秒，合成73.823秒。所有服务改动已部署，API18736/Comfy33844、两队列空闲；采样监控已退出。恢复只读Data/H3CampusStory20261021/run.json并查1195，两个runner已验证不新增任务。不自动追加GPU或收费云任务，无需API Key。见[成片与完整证据](docs/H3_CAMPUS_STORY_20261021.md)。
<!-- campus-story-20261021:end -->

<!-- refined1080-20261020:start -->
> 2026-10-20：首帧1179及优化视频1180均Succeeded。视频实际1920×1080、24FPS/124帧、5.166667秒，原生声轨及WAV，技术Passed，生成179分4.963秒（原180分钟时限内）。固定原模型/种子/20步/编码，改善合成首帧并简化镜头运动；中段部分叶片更可辨，末段仍有涂抹及建筑形变，内容NeedReview、发布Blocked。15契约/新脚本编译/Vue构建/实际解码与graph/2项真实播放/幂等接续/旧文件哈希Passed；原1178等媒体和报告保留，两队列空闲，无重复GPU、云调用或Key需求。当前实验完成，先读Data/H3Refined108020261020/run.json并查1180，不自动追加新任务。见[本轮记录](docs/H3_REFINED1080_COMPARISON_20261020.md)。
<!-- refined1080-20261020:end -->

<!-- native1080-20261019:start -->
> 2026-10-20 03时：原生1080p实验1178已Succeeded，1920×1088生成后上下各裁4行，实际1920×1080/24FPS/124帧、5.166667秒，原生音轨及独立WAV，技术Passed，耗时5195.870秒（86分35.870秒）。整卡约2秒采样2532个，显存峰值11852MiB，最低可用内存14MiB。实际可见前移和枝叶变化，树叶仍有涂抹与局部重绘，画质提升有限；内容NeedReview、发布Blocked。首轮1177因保存协议错误Failed的记录完整保留，修复后完整1080p/有声CPU编码、24项H3/26项MiniMax、6项UI夹具、2项真实播放、全片解码、元数据及幂等接续Passed；未重复GPU提交。当前实验完成，读active-attempt.json与attempt-2/run.json；不自动追加第三轮，原480p/768p/LTX/TTS保留，无云调用/无需Key。见[完整记录](docs/H3_NATIVE1080_EXPERIMENT_20261019.md)。
<!-- native1080-20261019:end -->

> 2026-10-19 09时：新增校园运动take1176、可续跑/运动诊断工具及并排循环预览页；同首帧/seed下原生768p/24FPS/124帧、独立WAV技术Passed，耗时1711.713秒。两项实际浏览器检查、Vue构建、Python编译、runner锁/接续Passed；原1174/1175保留，内容NeedReview、发布Blocked。见[动态记录](docs/H3_CAMPUS_MOTION_20261019.md)。

> 2026-10-19：增加明确H3 480p/768p规格、首帧准备契约、接续/采样/检查工具和同步对照页。真实1174/1175分别输出1376×768与864×480、24FPS/124帧及独立WAV，技术Passed；9项实际预检、7项浏览器/UI测试、22项MiniMax/15项H3/14个契约和构建Passed。补齐两个受管工作流的OOM参数保护与审计摘要分支；原默认、本地路线保留。内容待审，未调用云API。见[详细记录](docs/H3_NATIVE768_QUALITY_20261018.md)。

> 2026-10-18 后续：独立LTX生成条件60FPS实验1169及交付1170技术Passed，5秒/60FPS新样片已生成，无外挂补帧。工作流扫描改为优先采用已登记契约类型，初次图片误分类422已修复；构建/发布、13契约、5项实际预检与浏览器播放Passed。内容待审。见[记录](docs/LTX_NATIVE60_EXPERIMENT_20261018.md)。

> 2026-10-18 21时：增加固定Real-ESRGAN x2plus模型/工作流、sourceVideo契约、可续跑真实队列工具与滑动对照页；1166–1168实际增强/交付Passed，保留原片。新增12契约自检、5项预检及实际浏览器播放证据；内容待复核。H3权重与声画1165已完成，原下载未完成文字保留为历史阶段。见[增强记录](docs/AI_UPSCALE_CAMPUS_20261018.md)。

> 2026-10-18：生成全新10秒静音校园预览（任务1160–1164）；Concat新增可选精确交付参数并经真实300帧验证。修复Windows进度文件短暂访问冲突，下载回归7项Passed。见[样片记录](docs/CAMPUS_PREVIEW_20261018.md)。

> 2026-10-18：按用户要求增加仅回环免登录；MiniMax本地H3实验入口、固定模型/工作流、续传下载、版本记录与音轨提取已实施。真实SD1.5首帧/系统TTS/LTX通过；LTX帧数契约已升级v2并复测。H3模型与声画验收仍Blocked，云API未启用。见[本轮报告](docs/MINIMAX_LOCAL_INTEGRATION_20261018.md)。

> 2026-09-11 新预览：项目22、任务1089/1090/1091真实生成；720p展示版已导出，但变脸/非预期嘴部动作及动作未完成导致内容Failed、发布Blocked。详见[本轮证据](docs/NEW_PREVIEW_20260911.md)。

> 2026-09-08 H3第二批：提交预检及QA参数修正、Episode规格传递、增强音轨保留已改动；H3夹具14项和720p有声/无声实际后期测试Passed。未部署或GPU生成；许可地域确认、业务队列联调和内容审核未通过。见 [接入报告](docs/H3_INTEGRATION_BATCH2_20260908.md)。

> 当前历史入口为根目录 变更记录.md。本文件保留已有版本式变更摘要；新的重要开发节点先记录到中文变更记录，避免维护两套动态历史。

本文件记录已落地并有测试证据的阶段变化；规划内容写入 `NEXT_STAGE.md`，不在这里伪装成已完成。

## 0.5.7 - 2026-09-12 - 发布候选绑定与角色/模型版本门禁（代码 Passed，发布闭环保留）

- 导出必须明确 `candidateId`；候选快照锁定整片、镜头、字幕、音频、封面、角色审核版本和文件哈希，排队、worker 开始、最终落盘及发布后分别复核；来源变化会使旧候选过期，同一来源的 Ready 候选不会重复创建，候选版本使用幂等键和唯一键冲突重试并在冲突后再次查重。
- 许可证据、AI 披露、契约探针、模型实际权重哈希/解析路径和运行依赖指纹改为非空且绑定校验；同名模型多路径、异常追踪路径 fail closed。
- 角色审核改为登录身份并追加历史；资产变更或撤回批准会使关联镜头/整集回到 NeedReview；QA 重试保存原任务来源快照、原任务类型并使用确定性幂等键，继承原路线、角色和动作，只按失败原因修改对应参数，替代路线必须显式选择且不继承原通过结论。
- 验证：后端/前端构建、10/10 契约自检、候选快照/重试行为回归和边界静态回归通过；009 迁移、真实 GPU 输出、人工审片、浏览器业务 E2E 和正式发布仍未验收。

## 0.5.4 - 2026-08-13 - P0 边界加固与任务内核（代码 Passed，运行门禁保留）

- 统一 Data/Models/Workflows 受控路径、上传媒体探针、重解析点拒绝和原子媒体发布；FFmpeg/ComfyUI/TTS 输出不会直接覆盖最终文件。
- LLM 出站增加 provider/host allowlist、HTTPS/loopback、DNS 私网阻断、请求/响应上限、禁止重定向和脱敏审计。
- 队列领取、心跳和 deadline 使用 MySQL `NOW(3)`；进度/错误按 Worker fencing；生产批次幂等键冲突返回 Conflict；GPU 执行增加 Windows 命名信号量 `Local\\AI-Video-Studio-GPU`。
- 备份脚本增加转储非空和 SHA-256 manifest 检查，但本轮未执行备份写入、迁移或恢复。
- 验证：后端 0 warning/0 error、前端构建 Passed、资产/LLM/队列/幂等/外部进程/阶段 0 静态回归 Passed；数据库最小权限、ComfyUI 在线、真实 GPU/音频 Episode 和人工验收仍待验证。

## 0.5.3 - 2026-08-12 - 本机管理员安全边界（Passed）

- 新增首次本机管理员初始化、PBKDF2-SHA512 密码哈希、HttpOnly Strict 会话、CSRF、精确本机 CORS、持久会话和安全审计。
- 业务 API 改为默认拒绝匿名调用；前端在登录后携带会话和 CSRF 令牌执行写操作。
- 验证：release build、隔离认证/首次初始化回归、认证边界下的文本/任务预检回归和 Playwright 6/6 均 Passed。

## 0.5.2 - 2026-08-12 - 任务提交前校验与后台验收修正（Passed）

- 新增通用任务、A/B、重试、重新执行和旧式拼接的提交前校验；缺失 ControlNet 姿态图、LoRA、关联对象、输入文件或 TTS 音色会在写入/重入队前以 HTTP 422 拒绝。
- 创建/更新镜头会验证项目-Episode 归属和同集镜头号唯一性，重复镜头号返回 HTTP 409。
- 修正无首帧时的前端工作流选择，并将 Episode 输出空状态 E2E 改为选择真正没有历史正式版本的集数。
- 验证：.NET build 0 warnings/0 errors；任务预检和文本完整性 PowerShell 回归 Passed；Playwright 6/6 Passed（含快速项目切换）；Vue production build Passed。

## 0.4.3 - 2026-08-09 - 真实感优先默认路线（Passed with constraint）

- 新建镜头默认选择 Wan2.2 TI2V-5B；未指定工作流的图生视频任务也优先使用 Wan2.2，LTX 仅作为文件缺失时的兼容回退。
- 保留 49 帧首测和参考图比例自动匹配，避免已验证的竖图转横幅首段脸部块状伪影。
- 本阶段不启动全量训练；角色 LoRA/适配器只在基础模型和画幅匹配仍无法保持身份时再进入专项验证。

## 0.4.3 - 2026-08-10 - 系统级验收与本地条件通过

- 真实跑通 `Keyframe → I2V → Enhance → QA → Episode Render → Master`，并新增 `docs\SYSTEM_ACCEPTANCE_REPORT.md`。
- 修复 VideoReview 后续 Enhance、工作流阶段匹配、Episode 输出文件名、QA 导出门禁，以及本地 CORS/媒体路径/前端状态保护。
- 本轮结论为本机单用户 `Conditional Go`；认证、幂等租约、恢复演练、音频闭环和多人/公网发布仍为 No-Go。

## 0.4.2 - 2026-08-09 - Wan2.2 TI2V-5B 可选工作流（Passed with constraint）

- 新增 `05_wan22_ti2v_5b_api.json`，面向 RTX 4070 12GB 的低分辨率图生视频试跑。
- 前端镜头对话框支持选择图生视频工作流；Wan2.2 自动给出 640×352、73 帧建议值。
- 服务端支持将任务 FPS 写入视频输出节点，并识别 `text_encoders` 模型目录。
- 三份模型已完整校验，真实任务 69/70/71 成功；比例匹配的 320×416 竖幅输出抽帧稳定。
- 512×320 横幅输出在竖幅参考图上仍出现首段块状伪影，因此 LTX 仍保持默认，Wan2.2 只作为比例匹配后的可选链路。

## 0.4.1 - 2026-08-09 - 对话上下文迁移（Passed）

- 将此前项目对话中的目标、关键决策、5 秒 I2V 参数、角色一致性边界、验收规则和修复摘要迁移到 `docs\CONVERSATION_CONTEXT.md`。
- 未迁移任何 MySQL 密码、API Key、Token 或其他敏感配置。

## 0.4.0 - 2026-08-09 - 长期项目基线（Passed）

- 增加 `AGENTS.md`，固定架构、路径、显存、数据库、验收、恢复和完成协议。
- 增加 `PROJECT_STATE.md`，记录实际运行时、数据库、模型、任务和验收证据。
- 重写根 README 与 `docs` 文档，消除“数据库未配置”等旧状态，统一详细文档入口。
- 增加安全的 `config\config.example.json`；真实本地配置仍仅使用未跟踪的 `config\local.env`。
- 增加 `.gitignore`，排除密码、日志、备份、构建产物、模型、媒体和机器特定文件。
- 初始化本地 Git 仓库并在最终验收时检查 staged 文件、秘密扫描和提交内容。

## 0.3.0 - 2026-08-09 - Video QA 与发布闸门

- 增加 Technical/Shot/Episode QA、评分、问题帧、人工审核、Episode 锁定和 Master/QA 报告导出。
- 增加 QA 自动回炉上限和定向参数变更记录。
- 完成真实 3-shot Episode、QA 和 Master 导出验收。

## 0.2.0 - 2026-08-09 - Production Pipeline

- 增加剧本分析、Prompt 版本、关键帧候选、I2V、任务依赖、恢复、TTS、SRT、SFX/BGM 和 Episode 合成。
- 固定 RTX 4070 12GB 的 GPU 并发 1、显存门禁和 OOM 降参策略。

## 0.1.0 - 基础系统

- 建立 Vue 3 + Element Plus 工作台、.NET 8 API、MySQL 结构、ComfyUI/FFmpeg 本地目录和基础资产/任务管理。

## 0.4.4 - 2026-08-10 - Episode result viewer (Passed)

- Added formal Episode output states, version history, source snapshots, progress/error reporting and duplicate-render protection.
- Added stale detection for ordered videos, narration/SFX/BGM tracks, subtitles and output settings without overwriting the prior version.
- Added a project-workspace player dialog with version selection, media metadata, download and re-render actions.
- Added a Playwright regression (`npm run test:e2e`) through the Vite `18081` proxy; it passes 2/2 and caught/fixed the player-dialog click defect. Verified live V4 metadata and the not-ready render rejection path.

## 0.5.0 - 2026-08-11 - 人物质量优化基线与稳定默认路线

- 扫描并记录现有图片模型、I2V 工作流、提示词、参考图、LoRA/节点缺口、画幅、显存和运行时，不重新安装环境。
- 增加静态人物质量 v2、角色 Master Reference v2、全身实验、LTX v2 实验和 LTX v3 稳定工作流；全身重复人物候选被拒绝，不进入角色 Master。
- 增加质量实验/Golden Sample/Repair Run 数据表与 API、I2V Preflight、参数归一化和质量结果写回。
- VideoStudio 新建镜头默认选择 v3 人物 I2V；工作流页显示 `I2V_SubtleMotion_v3` 等已验证预设。
- 后处理默认关闭去闪烁和插帧，改为安全缩放、补边和转码；20 个连续静态任务 20/20 成功。

## 0.5.1 - 2026-08-11 - I2V 尾帧参考约束与回归门禁

- 修复服务端未覆盖 `SamplerCustom.noise_seed` 的问题，回归脚本新增实际种子和输出 SHA-256 多样性检查。
- 将有人物参考的 LTX v3 `LTXVAddGuide` 默认约束帧从第 36 帧调整为第 72 帧，覆盖生产提交、QA 回炉、前端排队、预设和工作流文件。
- 同种子 20 次配对回归从 1 个脸部拒绝/平均 94.14 提升为 0 个拒绝/平均 95.15，20 个输出均不同；RTX 4070 12GB 峰值 11988 MiB。
- 保持 3 秒、320×416、73 帧、锁定镜头和人工复核门禁；未安装新模型或整套环境。

## 0.5.5 - 2026-09-07 - 阶段 0 接管复核与原子发布句柄修复

- 复核本机 RTX 4070 12GB、VideoStudio/ComfyUI/MySQL/FFmpeg 运行状态、认证门禁、Git dirty 状态、模型/工作流规模和历史代表片内容质量。
- 修复 ComfyUI 下载与资产上传在 Windows 原子发布前的文件句柄释放边界；增加真实原子下载回归。
- 后端/前端构建、边界静态回归、原子下载回归和隔离服务 health 冒烟通过；历史样片内容审核仍失败，受保护业务回归和新样片生产仍阻塞。

## 0.5.6 - 2026-09-08 - QA人工Override门禁与固定能力基准

- 修复自动 QA Rejected 镜头人工 Passed 时未强制检查 `OverrideHardFailure` 的门禁缺陷；现在必须显式Override并填写复核说明。
- 新增 `VS-FIXED-CAPABILITY-001` 固定能力基准定义，覆盖 12 类身份、动作、接触、对白、遮挡、光照和连续性用例。
- 后端构建和 P0 静态回归通过；真实基准运行、人工内容审核和发布资格仍待认证门禁解除。
- 前端人工审核弹窗同步提交 `overrideHardFailure`，自动 QA Rejected 时强制填写人工复核说明；前端生产构建通过。
- Episode 级 Approved 同步强制自动 QA Rejected 的显式 Override 和复核说明，避免整集门禁绕过。


<!-- campus-umbrella-20261026 -->
> 2026-10-26：项目45《伞向你倾斜》10秒校园新样片已完成，任务1419，实际1376×768/24FPS/240帧。技术与完整浏览器播放Passed；手部/道具细节NeedReview，原生对白语义Unverified，正式发布Blocked。恢复Data/CampusUmbrella20261025/run.json，completed=true，禁止重复提交；一次性续接定时任务已删除。见[本轮记录](docs/CAMPUS_UMBRELLA_20261026.md).


<!-- character-story-15s-20261028 -->
> 2026-10-28：《窗边等候》已续成15秒有声试片：原片1555、续片1562/1563，Qwen旁白1557–1559、本地原创器乐1560，最终合成1565。技术、来源、全片解码和浏览器播放Passed；人物细节、音色及整体听感仍NeedReview，发布Blocked。双人场景保持待审。[详细记录](docs/CHARACTER_STORY_15S_20261028.md)。


<!-- character-wide-cutaway-20261028 -->
> 2026-10-28：《窗边等候》增加无人窗边环境切镜：关键帧1566、H3视频1567、最终成片1572；8.75–10.25秒插入，保留原15秒音轨与字幕。技术和浏览器播放Passed；窗格/房间布局不完全一致，内容和听感NeedReview，发布Blocked；双人待审状态不变。[详细证据](docs/CHARACTER_WIDE_CUTAWAY_20261028.md)。


<!-- character-fullbody-story-20261028 -->
> 2026-10-28：《窗边等候》新增林安全身远景，关键帧1575、H3视频1576、16.5秒成片1581；原生视频后段出现文字而Failed，仅截取检查过的前1.5秒。保留原窗景和旁白来源，第三句后移1.5秒，配乐略放慢。成片技术和浏览器播放Passed；面部、手指、窗格及新补裤鞋NeedReview，发布Blocked；被拒参考与双人待审状态不变。[详细记录](docs/CHARACTER_FULLBODY_STORY_20261028.md)。

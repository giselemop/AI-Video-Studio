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

# AI Video Studio 当前项目状态（兼容详细快照）

<!-- qwen3-video-20261022:start -->
> 2026-10-22：Qwen中文配音＋新生成10秒视频已完成，技术Passed。项目29任务1198/1199新生成，1200合成；实际1920×1080、24FPS、240帧、10秒，原始1196完整配音以1.32倍速保持音高接入，未截台词。真实解码、音轨一致性、浏览器完整播放和恢复无重复提交Passed。内容NeedReview、发布Blocked。Data/Qwen3Video20261022/run.json为ReadyForUserPreview；当前API32200、Comfy33844及MySQL在线，队列空闲。 见[本轮记录](docs/QWEN3_VIDEO_10S_20261022.md)。
<!-- qwen3-video-20261022:end -->

<!-- qwen3-tts-20261022:start -->
> 2026-10-22：Qwen3-TTS 1.7B-CustomVoice 已本地部署并接入声音工作台，技术验收 Passed。项目28任务1196生成12.88秒、24kHz/单声道/PCM16中文WAV，任务33.034秒、推理20.900秒；整卡43个一秒采样峰值5853MiB。任务1197以0.511秒复用缓存，WAV字节一致。15项合约、17项真实API、2项页面夹具和真实浏览器完整播放通过；Windows TTS、MiniMax/H3及跨进程GPU互斥回归通过。内容听审仍NeedReview，待用户试听；不据此批准发布。 详见[本地配音报告](docs/QWEN3_TTS_LOCAL_20261022.md)。
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

> 2026-10-19 09时：运动新版1176技术Passed，1376×768/24FPS/124帧、5.166667秒及独立WAV，用时1711.713秒；实际前移、近树位移及枝叶变化明显，内容NeedReview、发布Blocked。真实循环/实际呈现帧/同步定位等两项浏览器检查、构建、编译、锁与幂等接续Passed；独立约2秒采样828个、峰值10653MiB，队列9473MiB。原视频/首帧保留，无新云调用。见[动态记录](docs/H3_CAMPUS_MOTION_20261019.md)。

> 2026-10-19：H3原生1376×768校园1174及864×480对照1175已完成，各24FPS/124帧、原生音轨和独立WAV；同首帧/提示词/种子/20步，分别1686.670/563.191秒，技术Passed。完整解码、真实同步播放、9项实际API检查、22项MiniMax/15项H3/14个契约及7项浏览器/UI测试Passed。显式768p选项已部署，原480p/LTX/TTS不变；内容NeedReview、发布Blocked。续接不重复GPU提交，无云调用/无需Key。见[记录](docs/H3_NATIVE768_QUALITY_20261018.md)。

> 2026-10-18 后续：LTX独立60FPS生成实验1169 Passed（512×320、305帧、50.805秒），1170交付5秒/720p展示/60FPS/300帧。模型条件与直接保存同为60，无外挂补帧，独立采样峰值7663MiB；内容待审、发布Blocked。原24FPS路线保留；下方“尚未验证60FPS”为此前超分阶段快照。见[记录](docs/LTX_NATIVE60_EXPERIMENT_20261018.md)。

> 2026-10-18 21时：Real-ESRGAN两倍超分1166/1167及交付1168 Passed，10秒720p/30FPS/300帧；原片/源素材未改，滑动对照与真实浏览器播放Passed，内容待复核、发布Blocked。12个契约及5项实际预检Passed。60FPS运动补帧滤镜可用，本轮没有60FPS成片或原生60FPS验证。见[增强记录](docs/AI_UPSCALE_CAMPUS_20261018.md)。

> 2026-10-18 校园预览：项目25/任务1160–1164真实生成10秒720p静音LTX视频，技术Passed；内容待用户观看、发布Blocked。H3不作为本片生成路线。见[样片记录](docs/CAMPUS_PREVIEW_20261018.md)。

> 2026-10-18：本机免登录、四个H3模型校验及真实声画1165技术Passed，864×480/24FPS/124帧，独立WAV已登记。内容审核与发布仍Blocked。当前无需API Key。见[MiniMax报告](docs/MINIMAX_LOCAL_INTEGRATION_20261018.md)及中文项目状态；下方为历史记录。

> 2026-09-11 新预览：项目22、任务1089/1090/1091真实生成；720p展示版已导出，但变脸/非预期嘴部动作及动作未完成导致内容Failed、发布Blocked。详见[本轮证据](docs/NEW_PREVIEW_20260911.md)。

> 2026-09-08 H3第二批：提交预检及QA参数修正、Episode规格传递、增强音轨保留已改动；H3夹具14项和720p有声/无声实际后期测试Passed。未部署或GPU生成；许可地域确认、业务队列联调和内容审核未通过。见 [接入报告](docs/H3_INTEGRATION_BATCH2_20260908.md)。

> 当前动态状态以根目录 项目状态.md 为唯一维护源。本文件保留此前英文状态快照与详细验收证据；如本文件下方的历史数字与中文档案冲突，以实际代码、可验证运行结果和中文档案为准。

> 状态来源：实际源代码、运行中的本地服务、MySQL、ComfyUI、FFmpeg/FFprobe、真实生成任务和回归脚本。密码、Token 和 API Key 永不写入本文件。

## 最新动态核验覆盖

2026-08-09 19:26 API 核验：2 个项目、2 个 Episode、17 个 Shot、2 个角色、7 个场景、32 个资产、3 个模型、0 个 LoRA、8 个工作流、3 个 QA 预设；68 个任务中 63 个 Succeeded、3 个历史缺失输入失败夹具、2 个 Cancelled，无 Pending/Running 任务。详见 中文项目状态和本轮验收标准。

2026-08-12 实时校正：健康检查为 MySQL、ComfyUI、FFmpeg 可用，当前 7 个项目、19 个 Episode、148 个 Shot、13 个角色、23 个场景、724 个资产、0 个运行中任务。通用任务、A/B、重试、重新执行与旧式拼接均有提交前校验；无效 ControlNet/LoRA/关联/音色在写入或重入队前返回 422，重复镜头号返回 409。文本完整性接口回归和角色编辑 E2E 已通过；本机单管理员认证、CSRF、精确 CORS、会话和安全审计也已通过隔离回归。完整音频 Episode、多 worker 竞态、资产版本恢复、数据库恢复和 LAN/公网安全验收仍未完成。

2026-08-13 P0 增量校正：资产路径、LLM 出站、队列租约/幂等和外部产物边界已完成代码级第一阶段回归。数据库只读状态为 Cancelled 55、Failed 20、Succeeded 889，无 Pending/Running；最近 API 只读冒烟数据库在线、认证未初始化、ComfyUI 离线。只读探针仍显示 `root@%`、`require_secure_transport=0`、`bind_address=*`；正式迁移、最小权限、备份恢复、真实多 worker/GPU/音频 Episode 和人工验收仍未完成。

## 1. 当前阶段

- 项目：`AI Video Studio`
- 阶段：本地 AI 短剧生产链 + Video QA 发布闸门 + 长期维护基线
- 阶段状态：`Passed`（已验收核心生产链；长期增强仍按 `NEXT_STAGE.md` 排队）
- 对话上下文：已迁移到 `docs\CONVERSATION_CONTEXT.md`；敏感凭据未迁移。
- 最后核验日期：2026-08-09
- 项目根目录：`C:\install\AI\VideoStudio`
- 服务地址：`http://127.0.0.1:18080`
- ComfyUI：`http://127.0.0.1:8188`
- Git：已初始化本地仓库，当前分支 `main`，无 remote；长期基线提交为 `f5a98b9`（后续文档提交以 `git log -1 --oneline` 为准）。

## 2. 硬件与运行时基线

| 项目 | 当前实测/配置 |
| --- | --- |
| 系统 | Windows 11 64 位 |
| CPU | Intel Core i5-13600KF |
| 内存 | 32 GB（ComfyUI `/system_stats` 返回约 34.16 GB 总内存） |
| GPU | NVIDIA GeForce RTX 4070，12 GB |
| GPU 分配器 | `cuda:0 NVIDIA GeForce RTX 4070 : cudaMallocAsync` |
| ComfyUI Python | `C:\install\Python\python.exe`，`embedded_python=false` |
| ComfyUI Python 版本 | 3.13.2（健康检查返回值） |
| PyTorch | `2.11.0+cu130` |
| ComfyUI 版本字段 | `/system_stats` 的 `comfyui_version=0.31.0`；健康探针另返回 ComfyUI 服务版本字段 3.13.2，后续以接口原始字段为准 |
| FFmpeg | `C:\install\FFmpeg\bin\ffmpeg.exe` |
| FFprobe | `C:\install\FFmpeg\bin\ffprobe.exe` |
| C: 可用空间 | 最近检查约 222.66 GB |

最近一次健康检查中 GPU 总显存约 12281 MiB、空闲约 11018 MiB，利用率为 0；数据库、ComfyUI、FFmpeg 均在线。

## 3. 代码与数据现状

- 后端：`server\VideoStudio.Server.csproj`，.NET 8 Web，MySqlConnector 2.3.5。
- 前端：`web`，Vue 3 + Element Plus + Vite；发布后的静态页面由后端提供。
- 数据库：MySQL 8，`ai_video_studio`，当前 schema 34 张表；基础结构 + `002_production_pipeline.sql` + `003_video_qa.sql` 已应用。
- 当前数据库记录（最近核验）：9 个项目、7 个 Episode、14 个 Shot、2 个角色、7 个场景、15 个资产、3 个模型、0 个 LoRA、8 个工作流、3 个 QA 预设。新增的 3 个 `Production Pipeline Test` 项目和 5 个测试 Shot 是本次回归留下的可识别测试数据，没有删除既有业务记录。
- 任务状态（最近核验）：无 Running 任务，43 个 Succeeded；历史回归故意留下的失败夹具任务必须与当前产品故障区分。
- TTS：`/api/audio/voices` 可用，返回 Windows System.Speech 音色；实际音频仍按具体 Episode 需要验收。
- LLM：支持本地规则解析及已配置时的 OpenAI-compatible/DeepSeek/OpenAI 适配器；没有外部 Key 时不阻断本地规则解析。

## 4. 已验收能力

- 项目、Episode、角色、场景、Shot、资产的 CRUD 和参考图路径边界。
- 剧本保存、版本、规则/LLM 分析、角色/场景匹配、缺失资产草稿。
- Prompt 七段组合、编辑、锁定、历史和回滚。
- 工作流/模型/LoRA 扫描；当前真实 LoRA 目录为空，不能把 LoRA 能力描述为已安装。
- SD1.5 人物关键帧、LTX 2B FP8 I2V、ComfyUI 任务提交/轮询/下载/取消。
- RTX 4070 单 GPU 队列、显存门禁、暂停/恢复、取消、重试、依赖和服务重启恢复。
- FFmpeg 去闪烁/插帧/增强、SRT、Windows TTS、SFX/BGM 上传与 Episode 合成接口。
- Technical QA、Shot QA、Episode QA、人工审核、Approved 锁定、Master 导出和 QA 报告。
- 角色资产库、场景资产库、动作/电影镜头工作流入口已在生产模型中保留；严格身份控制模型尚未安装。

## 5. 最近真实验收证据

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 后端构建 | Passed | `dotnet build server\VideoStudio.Server.csproj --no-restore`，0 warnings/0 errors |
| 前端构建 | Passed | `npm run build`；仅有 Vite chunk 体积提示 |
| PowerShell 脚本语法 | Passed | scripts 目录 AST 检查 |
| 生产流水线回归 | Passed | `logs\production_pipeline_test.json`；health/文件/数据库/RuleBased 5 Shot 分析全部通过 |
| 技术/QA 夹具 | Passed | `C:\install\AI\Data\QA\TestCases\20260809_122530`，9/9 |
| 队列回归 | Passed | 暂停/恢复/取消/重试通过；缺失输入夹具按预期最终 Failed |
| QA 自动回炉 | Passed | Shot 11，第一次 73.05、第二次 85.35，使用不同 seed，最多两轮后停止 |
| 真实 3-shot Episode | Passed | Episode score 91.11，Approved/locked；技术 QA 100 |
| Master 导出 | Passed | `C:\install\AI\Data\Output\Release\Acceptance 3Shot 20260809_104019\Episode001` |

## 6. 已知限制与下一步

- 当前视频路线按输入类型分流：无人物参考时保留画幅匹配的低分辨率 Wan2.2；有人物参考时默认使用已验证的 LTX v3 人物稳定 Draft；最终增强仍受 12GB 硬件上限约束并由 FFmpeg 输出 1080P。
- 当前 `loras=0`，没有 IP-Adapter/ControlNet/角色 LoRA 资产；人物长镜头身份一致性仍依赖参考图、Prompt、seed 和镜头设计。
- 目前没有独立的 .NET 单元测试项目；真实验收依靠 API/PowerShell/FFprobe/ComfyUI/数据库链路脚本。建立自动化测试项目是 P1/P2 任务，不得把现有脚本称为完整单测覆盖。
- 前端是单页工作台，核心 UI 已可用；后续若修改 UI，必须通过真实浏览器操作验证按钮、刷新、状态恢复和错误提示，不能只通过编译。
- 任务表中存在历史失败夹具记录（例如缺失输入测试）；它们用于证明失败处理，不等同于当前未处理的产品失败。

## 6.1 Wan2.2 TI2V-5B 接入状态（2026-08-09，Passed with constraint）

- 已新增质量优先 API 工作流 `C:\install\AI\Workflows\05_wan22_ti2v_5b_api.json`；新建人物镜头默认选择 `12_ltx_face_stable_v3_api.json`，无角色参考仍可选择 Wan2.2。
- 已完成服务端 FPS 参数补丁、文本编码器模型分类和镜头工作流选择器；Wan2.2 新镜头先使用 49 帧，并按参考图自动匹配 320×416、512×320 或 384×384。
- Wan2.2 模型资产已完整校验：主模型 9,999,658,848 字节、UMT5 FP8 6,735,906,897 字节、VAE 1,409,400,960 字节；ComfyUI 0.31.0 已真实加载。
- 真实任务 69/70/71 均成功，峰值显存分别为 11,580/11,874/11,954 MiB；任务 71 使用 320×416 与竖幅参考图匹配，FFprobe 通过，抽帧未见任务 69/70 的首段块状伪影。
- 横幅 512×320 与竖幅参考图比例不匹配时，即使增加到 20 steps 仍有首段伪影；因此质量优先默认路线要求参考图与输出画幅匹配，LTX 仅作为异常回退，不把不匹配的横幅任务当作已验收质量路径。

## 7. 当前未阻塞项

核心生产链和本地服务当前没有外部 `Blocked` 项。角色 IP-Adapter/LoRA、OpenPose/ControlNet、口型同步和多 GPU 属于后续能力，不计入本阶段已验收核心。

## 8. 2026-08-10 系统级验收接管结果

- 本地监督范围内完成真实 `Keyframe → I2V → Enhance → Shot QA → Episode QA → Render → Master` 链路；项目 13、Episode 11、Shot 34 的最终 Render 85 与 QAExport 86 成功。
- 修复 VideoReview 无后续增强动作、工作流阶段误配、Episode 非法输出文件名、QA 导出状态门禁、CORS/媒体路径/异常边界、菜单刷新、必填校验和删除确认。
- 当时结论为 `Conditional Go`：仅允许本机单用户人工复核；认证/RBAC/CSRF、任务幂等租约、多 Worker、LLM SSRF 边界、迁移恢复和音频完整回归仍未完成。
- 详细证据见 `docs\SYSTEM_ACCEPTANCE_REPORT.md`；历史失败任务保留，不能把失败数量直接等同于当前缺陷。

## 9. 2026-08-10 真实三项目生产压力测试

- 已建立并保留 3 个 `TEST` 项目：A `id=14`、B `id=15`、C `id=16`；合计 15 集、120 个镜头、9 个角色、15 个场景。每集均有连续剧情状态、角色/场景约束和 8 镜头生产数据。
- 42 个角色/场景参考图任务成功；关键帧任务 254 成功、3 个取消（A EP02 已补齐新候选，旧取消记录保留），I2V 10 成功，未发生 CUDA OOM。GPU 队列实际维持 `gpuConcurrency=1`。
- 关键帧工作流已修正为场景关键帧 `workflowId=7`，Wan I2V 保持 `workflowId=87`；英文提示 A/B 探针优于原始中文长提示，但中文模型语义跟随和角色一致性仍不达发布标准。
- A EP01 已完成真实 `I2V → Enhance → TTS/SRT → EpisodeRender → Episode QA`；正式 V4 规格为 60 秒、1920×1080、30 FPS、音频 60 秒，技术 QA Passed；内容 QA Rejected（57.93），不可发布。
- 本轮新增修复：QA 回炉独立 Enhance、Episode 目标时长/音频补齐、TTS 空文件和无效缓存拒绝；详见 `docs\REAL_PRODUCTION_TEST_REPORT.md` 和 `docs\FIX_HISTORY.md`。
- 当前结论：`Conditional Go / TEST only`。其余 14 集已完成关键帧级真实生产，但尚未完成可发布 I2V/增强/音频/成片闭环；不得把 `ImageReview` 或 `Completed` 技术状态当作内容通过。

## 11. 2026-08-10 第一阶段可靠性、参考图和 TTS 改造

- 已接入任务幂等键、请求指纹、state version、worker 租约、心跳、deadline、超时状态和 `task_events`；迁移前备份为 `backup\\20260810_221931`。
- 队列已拆分为 CPU 单并发与 GPU 单并发；GPU 任务运行期间 CPU TTS 已实际成功执行。
- 角色/场景参考图已进入 ComfyUI 的 LoadImage/LTXVAddGuide；新增参考关键帧工作流，并对无法消费参考图的工作流 fail closed。
- 中文 TTS 增加真实 WAV + FFprobe 预检，生产启动在音频生成前阻断不合格音色；候选关键帧改为显式选择。
- 本地证据详见 `docs\\IMPLEMENTATION_2026-08-10.md`；当时认证/RBAC/CSRF、统一资产 manifest、outbox/reconciler 和完整恢复演练仍未完成。

## 10. Episode Result Viewer (2026-08-10, Passed)

- The project workspace now exposes a single formal Episode output entry with Empty, Rendering, Ready, Failed and Stale states, version history, actual media metadata, failure feedback and a player/download dialog.
- Episode render requests freeze their source-video snapshot, preserve new outputs as versions, reject duplicate active renders, and reject Episodes whose shots do not have playable formal videos.
- Staleness is evaluated against ordered video sources, narration/SFX/BGM tracks, subtitles and output settings, while retaining the prior playable version.
- Live API evidence for TEST A EP01 reports V4: 60 seconds, 1920×1080, 30 FPS, audio present, 8/8 sources ready and four retained versions. The output is now correctly Stale when its source snapshot differs. .NET and Vue production builds passed.
- `npm run test:e2e` now passes 2/2 through the Vite `18081` proxy with local Chrome, covering the player/version history and not-ready render rejection. The wider browser matrix remains pending.

## 12. 2026-08-11 人物质量优化与 RTX 4070 稳定性回归

- 已完成本地 AI 栈核验：SD1.5 静态人物、LTX 2B FP8 人物 I2V、Wan2.2 TI2V-5B、文本编码器、VAE、ComfyUI 和 FFmpeg 均来自现有环境；LoRA、ControlNet、IP-Adapter、FaceDetailer/ADetailer 和独立人脸修复模型当前为 0。
- 已建立 Project 17 / Character 15 的成年虚拟人物质量实验集、单脸 Master、三分之四参考、半身构图参考、Golden Samples 和质量实验记录。
- 静态基线与 I2V A/B 已实际生成并抽帧：3 秒锁定镜头可用，5 秒转头/推镜/走路暂不达默认门槛；v2 实验工作流低于旧版稳定结构，v3 已复现旧版最佳 3 秒结果。
- 当前人物 I2V 默认：`12_ltx_face_stable_v3_api.json`、320×416、73 帧、约 3.042 秒、24 FPS、guide 0.45、`guideFrameIndex=72`、small motion、锁定镜头；5 秒必须显式实验参数并人工复核。
- 连续 20 个静态任务（625～644）20/20 成功，平均约 6.16 秒，最大任务显存峰值 3355 MiB，最低任务记录空闲显存 8926 MiB；安全增强任务 645 输出 1920×1080/24 FPS，默认关闭插帧和去闪烁。
- 详细证据：`docs\CURRENT_AI_STACK_2026-08-11.md`、`docs\BASELINE_REPORT_2026-08-11.md`、`docs\AI_QUALITY_OPTIMIZATION_REPORT_2026-08-11.md`、`docs\REPAIR_STRATEGY.md`。
- 当前结论仍为 `Conditional Go / TEST only`：人物 I2V 必须经过 Preflight 和人工复核，不能把 CPU 代理分数当作自动发布许可。

## 13. 2026-08-11 I2V 尾帧约束修复与有效回归

- 修复 `SamplerCustom.noise_seed` 未被服务端覆盖的问题；回归脚本现在检查 ComfyUI 历史中的实际种子，并检查视频/中帧 SHA-256 多样性。
- 修复前同种子配对基线任务 677～696：20/20 生成成功，但 1 个脸部拒绝，平均 94.14，最低 92.77。
- 将单个 `LTXVAddGuide` 的默认约束从第 36 帧移至第 72 帧；同输入、同种子（920500～920519）任务 721～740：20/20 成功、0 拒绝、平均 95.15、最低 92.88、20/20 唯一视频哈希，峰值 11988 MiB。
- 服务端生产提交、QA 回炉、前端排队、质量预设和 `12_ltx_face_stable_v3_api.json` 已同步 `guideFrameIndex=72`；部署后任务 741 通过，ComfyUI 实际 `frame_idx=72`、`noise_seed=920801`。
- 当前仍不代表 5 秒复杂动作或完整身份控制已通过；LoRA/IP-Adapter/ControlNet/FaceDetailer 未安装，人物结果保持人工复核。

## 14. 2026-08-13 P0 边界加固与任务内核

- `AssetPathPolicy` 统一 Data/Models/Workflows 解析、上传媒体探针、重解析点/外部路径拒绝和临时文件原子发布；静态回归 1360 个 Data 文件、7 个恶意候选 Passed。
- LLM 出站增加 provider/host allowlist、HTTPS/loopback、DNS 私网阻断、大小/超时限制、禁止重定向和脱敏审计；真实 provider 和密钥库迁移未验证。
- 任务领取/心跳/deadline 使用 MySQL `NOW(3)`；进度/错误按 Worker fencing；生产批次幂等键冲突返回 Conflict；对应静态回归 Passed。
- FFmpeg、ComfyUI 下载/输入复制、字幕和 TTS 输出均先写临时文件再发布；`scripts/backup.ps1` 增加非空与 SHA-256 manifest 检查但未执行备份写入。
- `.NET build` 0 warning/0 error、Vue build Passed、PowerShell UTF-8 ParseInput 和秘密形态扫描 Passed；无 Commit/Push，未修改业务表。

## 2026-09-07 接管复核

- 阶段 0 已按当前现场重新核对；硬件、监听服务、`/api/health`、ComfyUI 版本、认证门禁、Git dirty 状态和历史代表片事实以 `docs/PHASE0_EXECUTION_REPORT_20260907.md` 为准。
- 修复 Windows 下 ComfyUI 输出下载和资产上传在原子移动前的文件句柄释放边界；真实原子下载回归和隔离 Release 服务 health 冒烟通过。
- 历史样片内容审核仍失败；受保护业务接口、真实业务队列、人工审片和新样片发布资格未通过，不能写成生产完成。

## 2026-09-08 P0质量门禁与固定能力基准

- 修复自动 QA Rejected 镜头人工 Passed 的 `OverrideHardFailure` 强制门禁；后端构建 0 warning/0 error，P0 静态回归 Passed。
- 建立 `VS-FIXED-CAPABILITY-001`，固定 12 个与剧情无关的身份、动作、接触、对白、遮挡、光照和相邻镜头连续性用例；当前为 `DefinedNotRun`。
- 认证门禁、真实GPU验证、人工内容审片和发布资格仍未闭环。

## 2026-09-12 末次收口验收

- 已修复候选导出绑定、原任务重试来源快照、模型权重强制重哈希、同源 Ready 去重和来源 asset/manifest 血缘锁定；代码/夹具回归、后端与前端构建、发布目录更新均 Passed。
- 运行态已复核：18080 健康，数据库/ComfyUI/FFmpeg 在线，RTX 4070 空闲约 11GB，Comfy 队列和数据库 Pending/Running 均为 0；匿名受保护入口仍返回 401。
- 009 仍未落库：候选包与角色审核表不存在；应用账号 `ai_video_studio_app@127.0.0.1` 只有 DML 权限。需单独授权维护窗口，不能给运行账号长期 DDL 权限。
- 本阶段不能宣称真实 GPU 输出、角色人工批准、许可证/AI 披露闭环、浏览器业务 E2E、候选 Ready 或正式发布通过；浏览器适配器故障和未登录均保持 Blocked。


<!-- campus-umbrella-20261026 -->
> 2026-10-26：项目45《伞向你倾斜》10秒校园新样片已完成，任务1419，实际1376×768/24FPS/240帧。技术与完整浏览器播放Passed；手部/道具细节NeedReview，原生对白语义Unverified，正式发布Blocked。恢复Data/CampusUmbrella20261025/run.json，completed=true，禁止重复提交；一次性续接定时任务已删除。见[本轮记录](docs/CAMPUS_UMBRELLA_20261026.md).


<!-- character-story-15s-20261028 -->
> 2026-10-28：《窗边等候》已续成15秒有声试片：原片1555、续片1562/1563，Qwen旁白1557–1559、本地原创器乐1560，最终合成1565。技术、来源、全片解码和浏览器播放Passed；人物细节、音色及整体听感仍NeedReview，发布Blocked。双人场景保持待审。[详细记录](docs/CHARACTER_STORY_15S_20261028.md)。


<!-- character-wide-cutaway-20261028 -->
> 2026-10-28：《窗边等候》增加无人窗边环境切镜：关键帧1566、H3视频1567、最终成片1572；8.75–10.25秒插入，保留原15秒音轨与字幕。技术和浏览器播放Passed；窗格/房间布局不完全一致，内容和听感NeedReview，发布Blocked；双人待审状态不变。[详细证据](docs/CHARACTER_WIDE_CUTAWAY_20261028.md)。


<!-- character-fullbody-story-20261028 -->
> 2026-10-28：《窗边等候》新增林安全身远景，关键帧1575、H3视频1576、16.5秒成片1581；原生视频后段出现文字而Failed，仅截取检查过的前1.5秒。保留原窗景和旁白来源，第三句后移1.5秒，配乐略放慢。成片技术和浏览器播放Passed；面部、手指、窗格及新补裤鞋NeedReview，发布Blocked；被拒参考与双人待审状态不变。[详细记录](docs/CHARACTER_FULLBODY_STORY_20261028.md)。

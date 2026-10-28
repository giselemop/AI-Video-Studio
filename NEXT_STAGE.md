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

# AI Video Studio 下一阶段任务

<!-- qwen3-video-20261022:start -->
> Passed：用户要求的Qwen配音＋全新10秒视频已完成，1200可供观看。下一步由用户确认声音表现、动作与视觉连续性；内容NeedReview、发布Blocked。恢复只核对Data/Qwen3Video20261022/run.json、1200及已保存SHA；恢复前后近期任务和数据库计数不变，无新的生成待执行。 见[本轮记录](docs/QWEN3_VIDEO_10S_20261022.md)。
<!-- qwen3-video-20261022:end -->

<!-- qwen3-tts-20261022:start -->
> Qwen3-TTS本地配音接入与技术验收Passed。下一步由用户试听任务1196（Vivian，12.88秒），确认满意的声音表现后再用于剧集；当前内容NeedReview、发布Blocked。已有真实试听与1197缓存证据，恢复时查询Data/Qwen3Tts20261022/run.json，不重复提交新推理。 详见[本地配音报告](docs/QWEN3_TTS_LOCAL_20261022.md)。
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

> 2026-10-19 09时：新768p运动1176技术与播放Passed，前移/近树位移/枝叶变化已观察到，当前等待用户复核自然度、几何和声音；发布Blocked。恢复先读H3Motion20261019/run.json，报告已ReadyForUserPreview，原1174/1175保留，不重复提交或自动扩展新实验，无需Key。见[动态记录](docs/H3_CAMPUS_MOTION_20261019.md)。

> 2026-10-19：原生768p校园1174和480p1175对照技术/播放Passed，首帧/提示词优化与显式规格选择已交付。当前等待用户观看动态效果和原生声音，内容NeedReview、发布Blocked；不自动新建GPU实验。原路线保留，无需API Key。10秒连续原生768p、768p/60FPS及复杂人物内容仍未验证，需分别明确范围后实测。见[记录](docs/H3_NATIVE768_QUALITY_20261018.md)。

> 2026-10-18 后续：LTX生成条件60FPS与新生成305帧已通过真实1169，1170提供5秒60FPS预览；当前待用户审核动态效果。源512×320，长片/更高清源/其他场景尚需独立验证，不设为默认；MiniMax H3仍按官方24FPS路线。见[记录](docs/LTX_NATIVE60_EXPERIMENT_20261018.md)。

> 2026-10-18 21时：校园超分及同步对照已交付（1166–1168，10秒/720p/30FPS/300帧，技术Passed）。待用户观看动态效果；60FPS补帧可以作为后续对照，本轮未输出，模型原生60FPS未验证。见[增强记录](docs/AI_UPSCALE_CAMPUS_20261018.md)。

> 2026-10-18：四个H3模型及真实声画1165技术Passed，下一步审核身份/动作/中文声音/口型。免登录、首帧/系统TTS/LTX相关回归Passed；旧LTX帧数错误已修复。云API未启用，无需Key。详见[MiniMax报告](docs/MINIMAX_LOCAL_INTEGRATION_20261018.md)和中文待办。

> 2026-09-11 新预览：项目22、任务1089/1090/1091真实生成；720p展示版已导出，但变脸/非预期嘴部动作及动作未完成导致内容Failed、发布Blocked。详见[本轮证据](docs/NEW_PREVIEW_20260911.md)。

> 2026-09-08 H3第二批：提交预检及QA参数修正、Episode规格传递、增强音轨保留已改动；H3夹具14项和720p有声/无声实际后期测试Passed。未部署或GPU生成；许可地域确认、业务队列联调和内容审核未通过。见 [接入报告](docs/H3_INTEGRATION_BATCH2_20260908.md)。

> 当前任务权威入口为根目录 待办事项.md。本文件保留已展开的路线图、任务编号和验收细节；新增或关闭任务时先更新中文待办，再按需同步本文件。

本文件只记录可以实际开发和验收的任务。当前核心生产链已 `Passed`；以下任务不能把规划能力写成已安装能力，也不能跳过真实测试直接改为完成。

## 执行顺序

| ID | 优先级 | 任务 | 当前状态 | 验收状态 |
| --- | --- | --- | --- | --- |
| TASK-001 | P0 | 长期项目基线、文档、Git 和秘密边界 | 已执行 | Passed |
| TASK-002 | P0 | 可重复的 API/队列回归入口 | 已完成并加入输出多样性门禁 | Passed |
| TASK-003 | P1 | 角色身份一致性资产与控制工作流 | 第一阶段完成；完整身份控制验收未完成 | Pending |
| TASK-004 | P1 | 场景参考与跨镜头一致性 | 资产/参考图已存在，自动比较不足 | Pending |
| TASK-005 | P1 | Pose/Motion/Camera 控制 | 仅保留工作流入口，未完成动作模型验收 | Pending |
| TASK-006 | P1 | TTS、字幕和音频混音的真实 Episode 回归 | 接口可用，需补完整语音成片证据 | Pending |
| TASK-007 | P2 | 资产版本、保留和可恢复清理 | 当前依赖人工管理 | Pending |
| TASK-008 | P2 | .NET 单元/集成测试项目 | 当前主要是 API/PowerShell/媒体真实回归 | Pending |
| TASK-009 | P2 | 基于真实指标的模型/工作流推荐 | 当前为目录扫描 + 固定 4070 预设 | Pending |

## 2026-08-12 任务可靠性与验收校正

- `TASK-002` 新增了任务提交前回归：通用任务、A/B、重试、重新执行和旧式拼接在写入/入队前验证输入、路径、关联、资源类别、工作流、模型和 TTS；该项为 `Passed`，但不替代双 worker 竞态和恢复压力测试。
- `TASK-003` 的 IP-Adapter/ControlNet 已有节点与接口级证据，LoRA 仍为空；任务状态保持 `Pending`，不能将其升级为跨动作、跨场景身份一致性通过。
- `TASK-006` 的中文 TTS 实际预检为 `Passed`，但完整音频 Episode 仍为 `Pending`。
- `TASK-008` 已有 Playwright 6/6（含项目/分集快速切换）和 PowerShell 回归；仍需 .NET 测试项目、刷新恢复、窄屏、键盘、危险操作和 CI。

## 2026-08-12 本机管理员安全边界

- 原 P0 本机认证、默认拒绝、CSRF、精确 CORS 和安全审计已完成并通过隔离接口回归、首次初始化/重启回归及 Playwright 6/6。
- 当前实现刻意保持单一 `Administrator` 本机角色和回环监听；它不是多用户 RBAC、TLS 或 LAN/公网发布证明。
- 下一 P0 顺序调整为：统一资产路径/上传下载边界、显式迁移与恢复证据、双 worker 竞态与恢复矩阵；多用户角色和网络发布另行评估。

## 2026-08-13 P0 边界加固与任务内核检查点

- `AssetPathPolicy` 已覆盖 Data/Models/Workflows 受控解析、上传媒体探针、重解析点和原子发布；静态恶意候选回归 Passed。
- LLM 出站已具备 provider/host allowlist、HTTPS/loopback、DNS 私网阻断、请求/响应上限、禁止重定向和脱敏审计；真实 provider 仍待验证。
- 任务领取/心跳/deadline 使用 MySQL `NOW(3)`，进度/错误按 Worker fencing，生产批次幂等键冲突返回 Conflict；GPU 执行使用 Windows 命名信号量 `Local\\AI-Video-Studio-GPU`；静态回归 Passed，真实多 Worker/恢复矩阵仍待验证。
- FFmpeg、ComfyUI 下载/输入复制、字幕和 TTS 采用临时文件成功后原子发布；备份脚本增加非空与 SHA-256 manifest 检查但未执行写入。
- 当前仍保持本机受监督 `Conditional Go`、LAN/公网 `No-Go`；数据库最小权限/迁移/恢复、ComfyUI 在线、真实 GPU/音频 Episode 和人工验收是后续门槛。

## TASK-001：长期项目基线

- 目标：让新会话能从实际代码、运行时和验收证据恢复，而不是依赖聊天历史。
- 实施：维护 `AGENTS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`docs`、`.gitignore`、本地 Git 和验收/修复记录。
- 验收：秘密、模型、媒体、备份和构建产物不进入 Git；文档中的数据库/ComfyUI/模型状态与健康检查一致；构建、API 健康和已有真实验收回归通过。
- 风险：根目录历史文档重复或过时。处理：详细文档以 `docs` 为源，根文档只作入口或项目级状态。

## TASK-002：可重复回归入口

- 目标：在不重新生成已 Passed Shot 的情况下，快速验证服务、数据库、剧本解析、队列状态机和 QA 夹具。
- 实施：保留 `scripts\test_production_pipeline.ps1`、`scripts\qa_test.ps1`、队列回归脚本；为每次运行写时间戳报告，明确真实生成开关。
- 验收：无 `-RunRealGeneration` 时能检查 health、文件、数据库和至少 5 个 Shot 分析；QA 夹具 9/9 通过；队列回归覆盖提交、暂停、恢复、取消、重试、依赖和恢复；失败夹具不能被删除或伪装成功。
- 风险：测试会向本地 MySQL 写入测试项目。处理：使用明确测试名称、保留证据，不删除既有业务数据。

## TASK-003：角色身份一致性

- 目标：同一角色在不同动作/场景中保持脸、发型、服装和比例。
- 当前差距：数据库有角色资产和身份锚点，但当前扫描到的 LoRA 为 0，未安装 IP-Adapter/ControlNet。
- 实施：先建立每个角色 10-20 张经过人工筛选的参考集和版本号，再选择 12GB 可运行的 SD1.5 LoRA 或轻量 IP-Adapter；增加 reference/identity 权重字段和可回滚工作流，不自动下载未知模型。
- 验收：同一角色 10 个动作、5 个场景生成测试；脸/发型/服装/比例的人工评分达到项目阈值，失败只重生成失败 Shot；两次自动回炉必须改变相关因素并记录 QA 分数。
- GPU 门槛：不得引入默认需要 24GB 以上显存的方案；每次先单人半身、固定光线、低分辨率验证。

## TASK-004：场景一致性

- 目标：驾驶室、车厢、城市等场景在不同镜头保持布局和关键物件关系。
- 实施：给 `Scenes` 建立参考集/版本；在工作流中显式区分 scene reference、camera prompt 和 shot prompt；保存场景版本到 Shot。
- 验收：一个场景至少 5 个景别和 3 个镜头运动，人工检查主体布局、色调和关键物件；只回炉失败 Shot，不重做已 Passed 镜头。

## TASK-005：动作与镜头控制

- 目标：走路、转身、挥手、拿物体以及推拉/跟随/环绕镜头可重复生成。
- 实施：在确认模型和节点兼容后增加 OpenPose/ControlNet/Motion 工作流；保持动作输入、camera motion、seed 和帧数可审计。
- 验收：单人 5 秒镜头至少完成转头、走路、挥手三类测试；动作完成度、人物漂移、镜头运动分别评分；显存峰值不超出 12GB 稳定范围。
- 风险：自定义节点或模型缺失。缺少实际文件时标记 `Blocked`，不能用静态视频或 Mock 结果替代。

## TASK-006：音频成片回归

- 目标：验证人物音色、对白、旁白、SRT、SFX/BGM 和 Episode 混音能在真实输出中闭环。
- 实施：使用已在线的 Windows System.Speech，创建两个角色和一集含对白/旁白/音效的短片，检查缓存命中、时间轴、字幕编码和音量。
- 验收：音频可播放、SRT UTF-8、字幕不越界不重叠、对白优先于 BGM、Master 可被 FFprobe 解码；任一失败按 TTS/FFmpeg/字幕类别修复后复测。

## TASK-007：资产版本和恢复

- 目标：让角色、场景、参考图、Prompt、工作流和输出可追踪、可回滚、可恢复。
- 实施：增加不可变版本号、引用关系、软删除/保留策略和备份恢复演练；禁止直接删除生产输出。
- 验收：修改资产后旧 Shot 仍能还原生成时版本；恢复备份后项目/任务/QA 报告可读取；清理操作有日志且不误删模型/媒体。

## TASK-008：自动化测试层

- 目标：把当前脚本/API 真实回归补成可维护的 .NET 单元和集成测试。
- 实施：先覆盖路径安全、状态机、重试策略、参数降级、QA 分数边界和迁移兼容性；外部 ComfyUI/FFmpeg 使用可验证的测试夹具，但不得把夹具结果冒充生产生成。
- 验收：测试可在本地重复运行，失败能定位模块；修改队列/Shot/数据库后相关回归自动执行。

## TASK-009：指标驱动推荐

- 目标：根据真实显存峰值、耗时、失败原因和 QA 分数推荐工作流/参数。
- 实施：从 `generation_tasks`、`generation_results`、QA 记录计算成功率和资源峰值；推荐必须带硬件上限和证据时间。
- 验收：推荐结果可解释、不会推荐缺失模型或 24GB 方案；换工作流后能回归健康、单图、5 秒 I2V、QA 和 Episode 合成。

## TASK-010：Wan2.2 TI2V-5B 低显存 A/B 验证（Passed with constraint）

- 当前状态：Passed with constraint。
- 目标：在 RTX 4070 12GB 上先用 512×320 或比例匹配的 320×416、49 帧、24 FPS 生成同一张参考图，和现有 LTX 结果对比脸部、眼睛、嘴部、发型漂移与峰值显存。
- 通过条件：模型文件完整、ComfyUI 工作流能真实完成、输出可由 FFprobe 解码、任务日志记录实际参数/耗时/显存；视觉结论只基于抽帧复核。任务 69/70/71 已满足，其中任务 71 使用匹配的 320×416 竖幅输入。
- 结论：比例匹配的竖幅短片可用；比例不匹配的横幅任务仍有首段脸部伪影，后续若要做横幅默认链路，需要增加裁切/填充预处理并重新验收。

## 明确暂不启动

在没有新硬件或完整验收证据前，不启动需要 24GB 以上显存的高分辨率 Wan/Flux 链路、多 GPU/远程 Worker、自动 AI 导演、自动角色 LoRA 训练、高级口型同步、自动音效生成和公网管理页面。当前无人物参考保留低分辨率、画幅匹配的 Wan2.2 路线；有人物参考默认使用已验证的 LTX v3 人物稳定 Draft。

## 2026-08-10 系统级验收门禁

本轮真实单镜头与 Episode 链路已通过，但整体仍为 `Conditional Go`。在 `TASK-P0-SEC-01`、`TASK-01`、`DATA-01` 和 LLM 出站边界完成并重新验收前，保持 loopback-only，不开放局域网/公网；音频闭环、资产版本恢复、并发稳定性和自动化浏览器测试继续按本文件的 P1/P2 项推进。详见 `docs\SYSTEM_ACCEPTANCE_REPORT.md`。

## 2026-08-10 真实生产压力测试结论

- 3 个 TEST 项目、15 集、120 镜头已真实入库并完成关键帧压力生产；A EP01 完成了真实 I2V、增强、字幕、Episode Render 和 Episode QA。
- 当前最高优先级不是继续盲目扩大 I2V 数量，而是修复中文提示语义、参考图注入/角色一致性和中文 TTS 空 WAV；这三项未通过前，不扩大到全季成片交付。
- 正式预览链路已可读取实际规格；A EP01 V4 通过技术规格 QA，但 Episode 内容 QA 仍 Rejected，保持 TEST-only。
- 详细结果、任务数量、抽帧结论和未解决项见 `docs\REAL_PRODUCTION_TEST_REPORT.md`。

## Completed checkpoint — Episode result viewer (2026-08-10)

- Formal Episode output status, version history, source snapshot, duplicate-render protection, stale-result indication and player/download UI are now implemented and API-verified.
- The first browser E2E is now Passed via the Vite `18081` proxy (`npm run test:e2e`, 2/2). Keep `TASK-P1-TEST-01` open for refresh recovery, responsive interaction and the remaining business flows.

## 2026-08-11 人物质量优化 checkpoint

- `TASK-003` 已完成第一阶段的可回归版本：角色单脸 Master、静态候选、I2V Preflight、v3 稳定 Draft、Golden Samples 和 Repair Strategy 已落地；不把缺失的 LoRA/IP-Adapter/FaceDetailer 描述为已安装。
- `TASK-009` 已开始使用真实 `generation_results.quality_score/qc_json`、任务耗时和显存峰值；20 个静态连续任务通过，人物 I2V 5 秒复杂动作仍保持实验状态。
- 下一步顺序：补充真实人物 5 秒单变量实验 → 继续完善角色/场景版本引用 → 只有在当前 3 秒尾帧约束仍不足时，才评估轻量身份控制模型；不重新安装整套环境。

## 2026-08-11 I2V 尾帧稳定性修复 checkpoint

- `TASK-002` 已固化为可重复回归入口：`scripts\test_quality_v3_i2v_regression.ps1` 会执行 Preflight、真实 I2V、抽帧、脸部代理检查、实验记录，并校验 `noise_seed` 生效、视频哈希多样性和无脸部硬性拒绝。
- 修复服务端没有覆盖 `SamplerCustom.noise_seed` 的问题；历史 20 个重复输出保留，不作为有效随机回归结论。
- 发现单个参考约束点在第 36 帧会让部分种子在尾帧出现眼部重影；将已验证默认约束点移到第 72 帧（73 帧视频的尾帧前），同种子配对回归任务 721～740 达到 20/20 成功、0 脸部拒绝、平均 95.15、20/20 输出不同、最大显存 11988 MiB。
- 已同步默认工作流 `12_ltx_face_stable_v3_api.json`、服务端生产/QA 回炉、前端排队参数和 `I2V_SubtleMotion_v3` 预设；仍保持 RTX 4070 12GB、320×416、73 帧、3 秒、锁定镜头和人工复核门禁。
- 任务 003 仍不能标记完成：LoRA、IP-Adapter、ControlNet、FaceDetailer/ADetailer 和独立人脸修复模型仍未安装；10 动作/5 场景的身份一致性人工验收尚未完成。

## 2026-08-11 继续执行 TASK-003：身份控制与 5 秒复杂动作边界

- 5 秒复杂动作已完成真实边界测试但未通过：745/746 出现手部穿脸、服装幻觉和脸部局部伪影；继续保持“单一克制动作 + 锁定镜头 + 3 秒优先”的生产门禁。
- 10 动作 × 5 场景静态身份基线已有效完成，报告：`logs/identity_consistency_matrix_20260811_232134_final.json`。50/50 成功、0 脸部代理拒绝；CPU 代理结果仍需人工抽帧确认。
- IP-Adapter Plus 已接入并通过单任务实际验收（任务 902 / 工作流 712）；ControlNet OpenPose 已接入并通过节点图流 smoke（任务 903 / 工作流 713）。缺少姿态图时任务 904 被阻断。
- LoRA 选择和动态 `LoraLoader` 入口已实现，但 `Models/loras` 当前为空，尚未安装或训练角色 LoRA，因此 LoRA 质量验收仍 Pending。
- 已完成：用工作流 13 的 IP-Adapter 版本重跑完整 10×5 矩阵；结果见下方 TASK-003 结果更新。

## 2026-08-11 TASK-003 结果更新

- IP-Adapter 完整矩阵已完成：报告 `logs/identity_consistency_matrix_20260811_233807_final.json`，50/50 成功、0 脸部代理拒绝、参考相似度代理均值 97.17、最低 96.44、50 个唯一哈希；相对静态基线均值提升 1.35、最低值提升 1.79。
- 因此 TASK-003 可标记为 `Passed with constraint`：静态身份控制和 IP-Adapter 代理门禁通过，但仍要求人工抽帧；5 秒复杂 I2V、真实 OpenPose 作用效果和角色 LoRA 仍不得自动放行。
- 默认推荐顺序固定为：IP-Adapter 生成静态关键帧 → 人工确认五官/眼睛/嘴型 → 3 秒 `12_ltx_face_stable_v3` I2V → 通过后再做 5 秒单动作；ControlNet 需要真实姿态图，LoRA 需要本地已筛选文件。

## 最终烟囱回归

- 任务 957 已验证默认 3 秒 I2V 仍可用：320×416、73 帧、guide 72、small motion，脸部代理 96.02、身份漂移代理 3.60、帧伪影代理 0%、显存峰值 10728 MiB；首/中/尾帧已落盘并保留人工复核要求。
- 交付边界保持不变：IP-Adapter 用于静态身份锁定，I2V 继续采用已验证的 3 秒稳定 Draft；5 秒复杂动作、真实 OpenPose 视觉效果、角色 LoRA 训练与 FaceDetailer/ADetailer 仍是后续实验项。

## 2026-09-07 阶段 0 接管复核后的门槛

- 先取得用户本地后台登录并完成受保护业务接口回归；不得绕过认证。
- 在登录门禁解除前，继续进行不依赖业务写入的候选模型许可/兼容性核查、固定基准集设计、报告整理和原子文件边界回归。
- 认证后只做少量短片段真实 GPU 验证，先检查加载、采样、解码、身份和动作内容，再决定是否进入 30～45 秒剧情样片。
- 历史《第三轨录音》保持 Failed；在人工内容审核通过前，不得生成发布资格或公开上传结论。

## 2026-09-08 固定基准与QA门禁后的下一步

- 使用 `docs/PHASE1_FIXED_BENCHMARK_20260908.json` 作为统一基准；认证后先运行 C01～C04，记录资源峰值和首/中/尾帧。
- 自动 QA Rejected 只有在真实人工复核、显式 Override 和说明齐全时才允许人工 Passed；不允许备注单独放行。
- C01～C04 未通过前，保持复杂动作、三维角色、正式对白和剧情样片 `Blocked`。

## 2026-09-12 末次收口后的下一步

- [Blocked] 由授权维护身份完成 009 的备份校验、增量迁移和接口复核；运行账号保持仅 DML。
- [Blocked] 管理员手动登录后，执行真实 API 和可见浏览器回归，建立隔离测试角色并提交真实参考图审核。
- [Unverified] 使用同一已批准角色、固定路线/槽位/seed 生成一条短片，保存请求、规范化参数、Comfy promptId、权重/槽位哈希、原片、抽帧、探针和后处理文件；先验收首尾参考、帧数和动作。
- [Blocked] 人工内容审核和许可证/AI 披露确认通过前，不创建正式 Ready 候选、不导出母版、不公开发布。


<!-- campus-umbrella-20261026 -->
> 2026-10-26：项目45《伞向你倾斜》10秒校园新样片已完成，任务1419，实际1376×768/24FPS/240帧。技术与完整浏览器播放Passed；手部/道具细节NeedReview，原生对白语义Unverified，正式发布Blocked。恢复Data/CampusUmbrella20261025/run.json，completed=true，禁止重复提交；一次性续接定时任务已删除。见[本轮记录](docs/CAMPUS_UMBRELLA_20261026.md).


<!-- character-story-15s-20261028 -->
> 2026-10-28：《窗边等候》15秒有声成片1565可供用户听看；人物、动作、音色和混音仍需人工判断，发布Blocked。下一步不自动重新生成已完成任务。[验收记录](docs/CHARACTER_STORY_15S_20261028.md)。


<!-- character-wide-cutaway-20261028 -->
> 2026-10-28：《窗边等候》增加无人窗边环境切镜：关键帧1566、H3视频1567、最终成片1572；8.75–10.25秒插入，保留原15秒音轨与字幕。技术和浏览器播放Passed；窗格/房间布局不完全一致，内容和听感NeedReview，发布Blocked；双人待审状态不变。[详细证据](docs/CHARACTER_WIDE_CUTAWAY_20261028.md)。


<!-- character-fullbody-story-20261028 -->
> 2026-10-28：《窗边等候》新增林安全身远景，关键帧1575、H3视频1576、16.5秒成片1581；原生视频后段出现文字而Failed，仅截取检查过的前1.5秒。保留原窗景和旁白来源，第三句后移1.5秒，配乐略放慢。成片技术和浏览器播放Passed；面部、手指、窗格及新补裤鞋NeedReview，发布Blocked；被拒参考与双人待审状态不变。[详细记录](docs/CHARACTER_FULLBODY_STORY_20261028.md)。

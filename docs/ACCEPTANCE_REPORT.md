<!-- character-turn-repair-20261027:start -->
> 2026-10-27：林安左转回正定向修复已交付，原任务1550、新项目53/任务1551。沿用人物版本3、已批准参考36、同H3工作流和种子；原生864×480/24FPS/124帧。19项媒体来源及两个真实浏览器完整播放Passed；25时点试片检查可见左转、停顿、回正，转幅接近侧脸，人物细节和自然度NeedReview、发布Blocked。仅1次定向修复，无新模型/新人物版本/人工批准/云调用；原片及双人剧情待审检查点保留。恢复Data/CharacterTurnRepair20261027/run.json，completed=true禁止重复提交。 [验收报告](CHARACTER_TURN_REPAIR_20261027.md)、[视频对照](http://127.0.0.1:18080/character-turn-repair.html)。
<!-- character-turn-repair-20261027:end -->

<!-- character-single-preview-20261027:start -->
> 2026-10-27：用户新请求的独立单人动作试片已交付，项目52/任务1550，林安旧版#3、已批准正面参考36；864×480/24FPS/124帧，技术Passed，助手动作检查Failed（实际眨眼和头部回正，定向左转未明显命中），人工内容NeedReview、发布Blocked。仅一个新视频，无新图/新版本/模型/云调用；原双人剧情检查点与保持待审指示不变。恢复Data/CharacterSinglePreview20261027/run.json，completed=true禁止重复生成。 [验收报告](CHARACTER_SINGLE_PREVIEW_20261027.md)、[本次视频](http://127.0.0.1:18080/character-single-preview.html)。
<!-- character-single-preview-20261027:end -->

<!-- character-scene-20261027:start -->
> 2026-10-27：项目51/集36固定阅读室场景版本、分镜显式绑定与待审界面已部署。真实关键帧1522–1525共4张，技术Passed；1522/1523方向、1525手部Failed，1524仅PreviewInspection Passed。区域外46.5%背景像素与原1514完全一致，不能据此判定人物/剧情合格。用户明确“保持待审”，拒绝来源与旧版本保留；新补图、H3视频和合成Blocked，未自动续跑。24项后端、25项首轮API、45项当前回归、71项媒体来源、5组前端、13项浏览器检查Passed。main/d6ec38d，未新增提交，无新模型/云调用；独立人物修复任务不重复。 [本轮证据](CHARACTER_SCENE_CONTINUITY_20261027.md)。新视频参数/解码/动态连续性/播放均Blocked（未执行），不能用上轮检查替代。
<!-- character-scene-20261027:end -->

<!-- character-prompt-repair-20261027:start -->
> 2026-10-27：人物参考提示词统一为character-anatomy-v2，7人63槽逐张目检，16张新修复候选＋47张原图。24个真实本地任务/8张方向失败候选保留排除；556项媒体来源、100项跨语言提示词、12项实际API、16项人物库自测及63图真实浏览器加载Passed。技术/助手可见缺陷检查Passed；细节内容NeedReview，发布Blocked。无自动批准、新库冻结、新模型、云调用或视频；旧原图/检查点/5个不可变版本保留。新图在候选中待用户复核，旧拒绝版本不会被伪装成可用。恢复Data/CharacterReferenceRepair20261027/run.json，completed=true禁止重复生成。见[验收报告](CHARACTER_PROMPT_REPAIR_20261027.md)、[63图汇总](http://127.0.0.1:18080/character-reference-repair.html)。
<!-- character-prompt-repair-20261027:end -->

<!-- character-story-20261027:start -->
> 2026-10-27：技术及有限四片/合成/执行中恢复Passed；最终内容NeedReview、发布Blocked。人工锚点/新版本批准待用户操作，五人候选未入库。 详见[本轮验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。
<!-- character-story-20261027:end -->

<!-- character-reference-pack-20261026:start -->
> 2026-10-26：人物九图参考包已补齐，项目47。林安v3、周言v2各3张面部近景＋6张全身，独立保存视角、景别和造型；旧版本与原视频保留。122项API、214项媒体/来源、19项实际页面检查及两条全身短片完整播放Passed。文件技术Passed，人物一致性/表演NeedReview，发布Blocked。GPU并发1，无新模型、无云调用。恢复Data/CharacterReferencePack20261026/run.json，completed=true禁止重复提交。见[人物库](http://127.0.0.1:18080/#character-library)、[九图与样片](http://127.0.0.1:18080/character-reference-pack.html)、[本轮验收](CHARACTER_REFERENCE_PACK_20261026.md)。
<!-- character-reference-pack-20261026:end -->

<!-- dialogue-eye-hair-20261025:start -->
> 2026-10-25纠正：项目43女方7.9–8.1秒侧脸眼部浅色块/头发双边内容复核Failed，原技术Passed不等于画面正确。项目44保守修复已完成，1366×768/24FPS/240帧；女方双人镜头固定眼睛、头发和头部，仅保留原对白嘴部动作。目标眼发复核与技术Passed，完整自然度仍需复核，发布Blocked。原声/字幕/53与96帧切点/旧版和模型保留。对比http://127.0.0.1:18080/dialogue-eye-hair.html；恢复Data/DialogueEyeHair20261025/run.json，completed=true禁止重复提交。见[执行记录](DIALOGUE_EYE_HAIR_20261025.md)。
<!-- dialogue-eye-hair-20261025:end -->

<!-- dialogue-stable-768-20261025:start -->
> 2026-10-25：项目43稳定768p完整十秒已完成，1366×768/24FPS/240帧，技术Passed；整体表演仍需用户复核，发布Blocked。修复开头连眨和4秒姿态跳变，确定性小样57帧重复像素一致；身体/手/手机偏静仍保留为限制。原声、四句字幕、53/96帧切点、旧版和模型保留。对比http://127.0.0.1:18080/dialogue-stable.html；恢复Data/DialogueStable20261025/run.json，completed=true禁止重复提交。见[执行与验收记录](DIALOGUE_STABLE_768_20261025.md)。
<!-- dialogue-stable-768-20261025:end -->

<!-- dialogue-sync-full-20261025:start -->
> 2026-10-25：项目42完整十秒口型与双人回应，阶段ReadyForUserPreview。已完成，技术Passed，内容NeedReview，发布Blocked；新对比http://127.0.0.1:18080/dialogue-sync-full.html。全程本地、GPU并发1，项目40十秒版及模型保留。恢复Data/DialogueSyncFull20261025/run.json，先查已登记任务，禁止重复提交。见[执行记录](DIALOGUE_SYNC_FULL_20261025.md)。
<!-- dialogue-sync-full-20261025:end -->

<!-- dialogue-sync-20261025:start -->
> 2026-10-25：项目41口型与双人回应小样，阶段ReadyForUserPreview。已完成，技术Passed，内容NeedReview，发布Blocked；新对比http://127.0.0.1:18080/dialogue-sync.html。全程本地、GPU并发1，项目40十秒版及模型保留。恢复Data/DialogueSync20261025/run.json，先查已登记任务，禁止重复提交。见[执行记录](DIALOGUE_SYNC_20261025.md)。
<!-- dialogue-sync-20261025:end -->

<!-- dialogue-visual-20261025:start -->
> 2026-10-25：项目40十秒对话画面升级，阶段ReadyForUserPreview。已完成，技术Passed；内容NeedReview，发布Blocked。原四句对白/声轨/字幕、53/96帧切点和旧版本保留，原队列恢复。新对比：http://127.0.0.1:18080/dialogue-visual.html。恢复Data/DialogueVisual20261025/run.json，先查已登记任务，禁止重复提交；见[执行记录](DIALOGUE_VISUAL_20261025.md)。
<!-- dialogue-visual-20261025:end -->

<!-- visual-targeted-20261024:start -->
> 2026-10-24定向画面修复小样已交付，项目39，任务1322–1325：局部眨眼残差、同条件H3分时段闭口、源频段皮肤回补。技术与真实页面Passed；眨眼闭合及中段表情改善，皮肤收益较轻，内容NeedReview，发布Blocked。全本地、无新增模型，旧模型/版本/成片保全；原队列恢复。恢复Data/VisualTargeted20261024/run.json，只读不重生成。见[验收记录](VISUAL_TARGETED_20261024.md)、[本机新对比](http://127.0.0.1:18080/visual-targeted.html)。
<!-- visual-targeted-20261024:end -->

<!-- visual-validation-20261024:start -->
> 2026-10-24画面小验证包已交付，项目38。六张新Klein关键帧、H3首帧/首尾双帧动作对照、两秒LivePortrait重演及选片QHD对照已完成。文件技术与真实页面验收Passed；身份、自然度和画面偏好NeedReview，发布Blocked。LP使用旧自有生成素材驱动，不是新真人表演；QHD为后期超分。旧模型元数据与冻结原片SHA保全，原队列已恢复此前状态。恢复Data/VisualValidation20261024/run.json，仅核验，不重复生成。见[执行与验收记录](VISUAL_VALIDATION_20261024.md)，[本机对比](http://127.0.0.1:18080/visual-validation.html)。
<!-- visual-validation-20261024:end -->

<!-- face-acting-20261024:start -->
> 2026-10-24：项目37同人物参考/表情重建已交付，最终任务1306实际2560×1440/24FPS/240帧/10秒。两秒原声短测、三镜头重生成、逐镜头SeedVR2与原AAC完整接回已执行；技术Passed，人物自然度与口型仍待用户复核，发布Blocked。恢复Data/FaceActing20261024/run.json为ReadyForUserPreview，只核验、不重复生成；原版、旧2K和旧肤质小样保留。 见[本轮记录](FACE_ACTING_20261024.md)。
<!-- face-acting-20261024:end -->

<!-- skin-pilot-20261024:start -->
> 2026-10-24：项目36两秒局部肤质与跨帧稳定小样已交付，最终任务1281实际2560×1440/24FPS/48帧/2秒。取原片5–52帧，完整保留“哟，约会回来了？”，原版/当前2K/优化版使用同一原声片段；技术Passed，肤质收益较轻、内容待用户复核，发布Blocked。原嘴部/眼睛/非皮肤区域在编码前逐像素保持；不宣称恢复真实毛孔。恢复Data/SkinPilot20261024/run.json为ReadyForUserPreview，仅核验、不重复提交。 见[本轮记录](SKIN_PILOT_20261024.md)。
<!-- skin-pilot-20261024:end -->

<!-- seedvr2-dialogue-2k-20261024:start -->
> 2026-10-24：项目35，同人物/同四句台词的10秒三镜头 SeedVR2 逐镜头2K修复，目标2560×1440（QHD）/24FPS/240帧，阶段：成片与对比可供用户观看。技术Passed；内容待用户复核，发布Blocked。原1263与声轨、切点保留，无新增表演或配音；不是原生2K生成或H3官方再生成。恢复Data/Dialogue2KSeedVR220261024/run.json，按已登记任务续接，不重复提交。 见[本轮记录](SEEDVR2_DIALOGUE_2K_20261024.md)。
<!-- seedvr2-dialogue-2k-20261024:end -->

<!-- h3-regenerate-2k-audit-20261024:start -->
> 2026-10-24：H3-Regenerate-2K 纯本地可部署性核查 Passed；官方模块尚未开源，现有 Full 2K Workflow 实际调用认证云 API，因此官方本地接入与同人物/同台词 10 秒三镜头 2K 样片 Blocked。补查社区 MMH3Tools 为非官方复现，需更高版本 ComfyUI/Ref2VA 等，未在本机执行，不能声称等效或可运行。本轮 GPU/云推理/权重下载均 0；原 1263 和既有源码/工作流保留。证据 Data/H3Regenerate2KAudit20261024/audit.json。见[核查报告](H3_REGENERATE_2K_AUDIT_20261024.md)。
<!-- h3-regenerate-2k-audit-20261024:end -->

<!-- dialogue-three-shot-20261023:start -->
> 2026-10-23交付：项目34同人物、同四句台词的纯本地三镜头样片，最终任务1263实际1280×720/24FPS/240帧/10秒。先调整Qwen逐句语气与非统一停顿，再生成女近景、男反打、双人收尾；原生832×480/25FPS，720P为后期交付。最终技术和真实浏览器完整播放Passed；情绪/人物反应/精细口型仍待用户复核，发布Blocked。GPU任务耗时合计2754.450秒（含保留候选），采样显存峰值11182MiB。恢复Data/DialogueThreeShot20261023/run.json为ReadyForUserPreview，仅核验、不重提。 见[本轮记录](DIALOGUE_THREE_SHOT_20261023.md)。
<!-- dialogue-three-shot-20261023:end -->

<!-- dialogue-pilot-20261023:start -->
> 2026-10-23交付：项目33双人对白样片，最终任务1246实际1280×720/24FPS/228帧/9.5秒，全程本地Qwen分角色/逐句情绪、InfiniteTalk双音轨及人物区域驱动、细节处理和混音字幕。四句完整原速对白、解码/音轨/真实浏览器完整播放Passed；内容待用户复核、发布Blocked。初次短测1241帧数Failed保留，CPU1242精确裁取；v2保存前裁帧已修复。恢复Data/DialoguePilot20261023/run.json为ReadyForUserPreview，只核验、不重提。 见[本轮记录](DIALOGUE_PILOT_20261023.md)。
<!-- dialogue-pilot-20261023:end -->

<!-- douyin-reference-20261023:start -->
> 2026-10-23交付：项目32男女双人客厅剧情，最终任务1236实际1280×720/24FPS/744帧/31秒，六段H3原生1376×768/20步、实际尾帧续接，11句Qwen男女声原速完整接入。完整解码、逐句音轨比对和真实浏览器完整播放Passed。开场改为回家后落座，衣服/站位跟随实际新角色；精细肢体与口型仍NeedReview，发布Blocked。恢复Data/DouyinReference20261023/run.json为ReadyForUserPreview，仅核验现有文件/任务，不自动重生成。见[本轮记录](DOUYIN_REFERENCE_20261023.md)。
<!-- douyin-reference-20261023:end -->

<!-- realistic-i2v-resume-20261022:start -->
> 2026-10-23最终交付：纯本地写实优化技术Passed，项目31最终1215为1920×1080/24FPS/240帧/10秒，完整Qwen中文旁白；首帧1211、同条件20步1212/30步1213对比、选30步实际尾帧续接1214、一次合成均Succeeded。完整解码/音轨比对/真实浏览器全程播放Passed；手指和肤质仍NeedReview、发布Blocked。三段GPU共12小时13分43.198秒，CPU合成5.886秒；5秒显存采样峰值11867MiB、最低可用RAM22MiB。API27676/Comfy29860在线、队列空闲，原B/C和音视频SHA保持。main/d6ec38d，未提交。恢复Data/RealisticI2V20261022/run.json为ReadyForUserPreview，只核验现有任务，不自动追加生成。见[完整记录](REALISTIC_I2V_20261022.md)。
<!-- realistic-i2v-resume-20261022:end -->

<!-- realistic-i2v-20261022:start -->
> 历史：2026-10-22首帧阶段曾Blocked，后经用户明确要求继续，已在2026-10-23完成新1215成片；当前状态与恢复方式以上方交付记录为准。
<!-- realistic-i2v-20261022:end -->

# AI Video Studio 强制验收报告

<!-- seedvr2-20261022:start -->
> 2026-10-22视频细节技术验收Passed：最终1206全解码240个不同帧，1920×1080/24FPS/10秒；原文件SHA保持，换轨视频帧一致、完整AAC载荷一致，旁白参考相关系数0.999958041。11项SeedVR2合约、30项实际API、3项真实浏览器、FFmpeg媒体回归及GPU锁/恢复Passed。浏览器三栏实际ended=true、各240解码帧、无错误。内容NeedReview、发布Blocked。初版音轨缺包Failed证据与1205/1206修复保留，不能把原1203/1204推理回执当成完整音频证据。见[完整验收](VIDEO_DETAIL_SEEDVR2_20261022.md)。
<!-- seedvr2-20261022:end -->

<!-- qwen3-video-20261022:start -->
> 2026-10-22：项目29配音视频技术Passed。1198/1199全新生成、1200合成22.103秒，实际1920×1080/24FPS/240帧/10秒；完整解码240帧、240个不同哈希。完整Qwen配音含延迟9.8740417秒，未截断，与最终音轨相关系数0.999940，峰值-5.237dB/RMS -21.207dB。CPU媒体回归、4项真实预检、27项H3回归、2项真实浏览器检查及恢复无重复提交Passed。内容NeedReview、发布Blocked。 见[本轮记录](QWEN3_VIDEO_10S_20261022.md)。
<!-- qwen3-video-20261022:end -->

<!-- qwen3-tts-20261022:start -->
> 2026-10-22：Qwen3-TTS 1.7B-CustomVoice 已本地部署并接入声音工作台，技术验收 Passed。项目28任务1196生成12.88秒、24kHz/单声道/PCM16中文WAV，任务33.034秒、推理20.900秒；整卡43个一秒采样峰值5853MiB。任务1197以0.511秒复用缓存，WAV字节一致。15项合约、17项真实API、2项页面夹具和真实浏览器完整播放通过；Windows TTS、MiniMax/H3及跨进程GPU互斥回归通过。内容听审仍NeedReview，待用户试听；不据此批准发布。 详见[本地配音报告](QWEN3_TTS_LOCAL_20261022.md)。
<!-- qwen3-tts-20261022:end -->

<!-- campus-story-20261021:start -->
> 2026-10-21：校园剧情《遗落的笔记本》项目27已生成并通过技术验收（Passed）。五段新视频1189/1190/1191/1193/1194均Succeeded，以真实尾帧逐段续接；CPU合成1195 Succeeded，实际1920×1080、24FPS、620帧/25.833333秒，含5段本地中文System.Speech旁白和烧录字幕。H3原生1920×1088仅上下各裁4行，无超分/插帧/旧样片填充。完整解码、2项真实浏览器测试（完整播放/五章节跳转/路径拒绝）、接续不重提及旧1178/1180哈希核对Passed。成片已ReadyForUserPreview，内容仍NeedReview、发布Blocked：远景手部交接部分遮挡，精细脸部/手指仍有AI痕迹，末段推进不明显、离场短暂。五段视频GPU任务合计7小时49分28.199秒，合成73.823秒。所有服务改动已部署，API18736/Comfy33844、两队列空闲；采样监控已退出。恢复只读Data/H3CampusStory20261021/run.json并查1195，两个runner已验证不新增任务。不自动追加GPU或收费云任务，无需API Key。见[成片与完整证据](H3_CAMPUS_STORY_20261021.md)。
<!-- campus-story-20261021:end -->

<!-- refined1080-20261020:start -->
> 2026-10-20：首帧1179及优化视频1180均Succeeded。视频实际1920×1080、24FPS/124帧、5.166667秒，原生声轨及WAV，技术Passed，生成179分4.963秒（原180分钟时限内）。固定原模型/种子/20步/编码，改善合成首帧并简化镜头运动；中段部分叶片更可辨，末段仍有涂抹及建筑形变，内容NeedReview、发布Blocked。15契约/新脚本编译/Vue构建/实际解码与graph/2项真实播放/幂等接续/旧文件哈希Passed；原1178等媒体和报告保留，两队列空闲，无重复GPU、云调用或Key需求。当前实验完成，先读Data/H3Refined108020261020/run.json并查1180，不自动追加新任务。见[本轮记录](H3_REFINED1080_COMPARISON_20261020.md)。
<!-- refined1080-20261020:end -->

<!-- native1080-20261019:start -->
> 2026-10-20 03时：原生1080p实验1178已Succeeded，1920×1088生成后上下各裁4行，实际1920×1080/24FPS/124帧、5.166667秒，原生音轨及独立WAV，技术Passed，耗时5195.870秒（86分35.870秒）。整卡约2秒采样2532个，显存峰值11852MiB，最低可用内存14MiB。实际可见前移和枝叶变化，树叶仍有涂抹与局部重绘，画质提升有限；内容NeedReview、发布Blocked。首轮1177因保存协议错误Failed的记录完整保留，修复后完整1080p/有声CPU编码、24项H3/26项MiniMax、6项UI夹具、2项真实播放、全片解码、元数据及幂等接续Passed；未重复GPU提交。当前实验完成，读active-attempt.json与attempt-2/run.json；不自动追加第三轮，原480p/768p/LTX/TTS保留，无云调用/无需Key。见[完整记录](H3_NATIVE1080_EXPERIMENT_20261019.md)。
<!-- native1080-20261019:end -->

> 2026-10-19 09时：运动新版1176一次Succeeded，实际1376×768/24FPS/124帧、5.166667秒、原生音轨及独立WAV，全片解码/内嵌prompt/哈希Passed；1711.713秒。约2秒采样828个，峰值10653MiB，队列9473MiB。实际可见前移与枝叶变化；循环回绕、同步定位和实际呈现3.5秒帧等两项浏览器检查Passed，重跑不新增任务。内容自然度/几何/声音NeedReview，发布Blocked，未以像素变化幅度充当质量分数。见[动态记录](H3_CAMPUS_MOTION_20261019.md)。

> 2026-10-19：H3原生768p校园1174（1376×768，1686.670秒）与480p对照1175（864×480，563.191秒）均24FPS/124帧、5.166667秒视频、原生音轨和独立WAV，完整数帧/解码Passed。内嵌prompt核对相同首帧哈希/提示词/种子/20步，无成片超分或补帧；9项真实API检查、7项浏览器/UI验证、22项MiniMax/15项H3回归、14个契约及构建Passed。独立约2秒采样显存峰值10426/10565MiB，非连续峰值。内容NeedReview、发布Blocked；首帧源于合成图超分，未验证Seedance同等质量。见[完整记录](H3_NATIVE768_QUALITY_20261018.md)。

> 2026-10-18 后续60FPS：真实1169在LTX生成条件60FPS下直接保存512×320/305帧MP4，50.805秒，305个解码帧校验各异；1170为5.000秒/1280×720展示/60FPS/300帧。完整解码、13个契约、5项实际预检、浏览器300帧播放且无丢帧/JS错误Passed。2秒采样峰值7663MiB，队列采样6808MiB。未证明所有动作/场景的60FPS质量，内容NeedReview、发布Blocked；H3仍24FPS。见[实验报告](LTX_NATIVE60_EXPERIMENT_20261018.md)。

> 2026-10-18 21时更新：本地Real-ESRGAN x2plus工作流真实任务1166/1167、最终交付1168均Succeeded，实际10.000秒/1280×720/30FPS/300帧；12个工作流契约、5项真实API预检、全片解码、原片哈希不变及同步浏览器播放Passed。H3任务1165与独立WAV也已生成，技术Passed；两项内容复核/发布仍Blocked。60FPS滤镜可用，不代表已完成60FPS成片或原生生成验证。见[增强报告](AI_UPSCALE_CAMPUS_20261018.md)。

> 2026-10-18 校园预览：真实任务1160–1164均Succeeded，最终10.000秒/1280×720/30FPS/300帧，FFmpeg全片解码与5项实际交付预检Passed；静音LTX预览，内容NeedReview、发布Blocked。下载原子替换回归7项Passed。见[详细记录](CAMPUS_PREVIEW_20261018.md)。

> 2026-10-18：本机免登录、安全负向检查、17项MiniMax契约/16项免登录/5项下载/4项前端mock回归、11个工作流契约及构建Passed。真实首帧1156、中文TTS1158、LTX视频1159 Passed；1157帧数Failed已修复并保留。H3实际模型/声画与内容发布仍Blocked。证据见[本轮报告](MINIMAX_LOCAL_INTEGRATION_20261018.md)，mock/合成夹具不代表H3内容通过。

> 2026-09-11 新预览：项目22、任务1089/1090/1091真实生成；720p展示版已导出，但变脸/非预期嘴部动作及动作未完成导致内容Failed、发布Blocked。详见[本轮证据](NEW_PREVIEW_20260911.md)。

> 2026-09-08 H3第二批：提交预检及QA参数修正、Episode规格传递、增强音轨保留已改动；H3夹具14项和720p有声/无声实际后期测试Passed。未部署或GPU生成；许可地域确认、业务队列联调和内容审核未通过。见 [接入报告](H3_INTEGRATION_BATCH2_20260908.md)。

验收时间：2026-08-09\
验收范围：本地数据库、项目生产链路、ComfyUI I2V、FFmpeg 增强、Shot/Episode QA、回炉、发布和 UI。

## 2026-08-12 本机管理员安全边界

状态：仅限受监督回环使用 Passed。

- 匿名业务 API、错误凭据、恶意 Origin、缺少 CSRF、撤销会话和登出后的访问均被服务端拒绝。
- 首次初始化只保存 PBKDF2-SHA512 校验值，重启后可登录，不保存明文密码。
- 登录、登出与写请求审计保留 actor、requestId、路径和结果，不记录密码或原始会话令牌。
- 验证：release build、隔离认证/初始化重启回归、认证边界下文本和预检回归、Playwright 6/6。

本项不证明 LAN/公网、TLS、多用户 RBAC、数据库恢复、资产路径边界或多 worker 任务竞态。

## 最终结论

阶段状态：**Passed**

所有核心验收项：**Passed**\
未保留 Failed 项：0\
未保留 Blocked 项：0

本报告只记录已经实际执行并重新验证的结果。内容质量中的人物身份、动作语义和场景连续性仍由人工复核确认；当前 CPU QA 不冒充未安装的视觉身份模型。

## 验收矩阵

| 功能 | 状态 | 实际验收证据 |
|---|---|---|
| 编译与发布 | Passed | .NET 8 构建 0 警告/0 错误；Vue production build Passed；发布脚本已检查原生退出码 |
| 服务健康 | Passed | HTTP 18080；数据库在线；ComfyUI 在线；FFmpeg 可用；RTX 4070，12281 MiB 总显存，检查时约 11018 MiB 空闲 |
| 数据库与 Migration | Passed | 已备份后应用 `002_production_pipeline`、`003_video_qa`；34 张表；QA preset 3；generation preset 3 |
| 项目/人物/场景/Episode/Shot CRUD | Passed | 独立 CRUD 回归创建、修改、读取、删除均通过；清理只针对本次临时数据 |
| 5 秒 I2V | Passed | 真实 Episode 4 的 I2V tasks 14、15、16；121 frames、24 FPS；3 个任务全部成功 |
| 1080P/30FPS 增强 | Passed | Enhance tasks 17、18、19；输出均为 1920x1080、30 FPS、约 4.9 秒 |
| 三镜头 Episode | Passed | Project 4 / Episode 4 / Shot 6、7、8；3 个真实镜头均完成生成、增强和人工复核 |
| Shot QA | Passed | Shot QA tasks 20、21、22；三镜头最终均 Passed，分数均 90.60，开放问题 0 |
| Episode QA | Passed | Episode QA task 23；整体分数 91.11；人工复核后 Approved，`qaLocked=true` |
| Episode 合成 | Passed | Render task 24；1920x1080、30 FPS、14.7 秒，输出可解码 |
| Master 导出 | Passed | Export task 26；Master、封面、QA_REPORT.md、QA_REPORT.json 均存在且非空 |
| Master 技术 QA | Passed | 分数 100；H.264；1920x1080；30 FPS；无黑帧；解码错误 0；突变比例 0 |
| QA 夹具 | Passed | `qa_test.ps1` 9/9 通过：正常、黑帧、短视频、分辨率、时序、损坏、缺音频、字幕超时、末日列车成片 |
| 自动回炉 | Passed | Shot 11 实际执行两轮 `ShotQA → I2V → Enhance → ShotQA`；两次 Seed 不同；`qa_retry_count=2` 后无第三轮 |
| 任务队列回归 | Passed | 暂停/恢复/取消/重试通过；取消 task 46 成功；缺失输入 task 47 按预期失败且 attempts=2 |
| UI 验收 | Passed | Chrome 实际打开质量验收页；数据库/ComfyUI/GPU 状态正确；Approved Episode、锁定状态和 Master 导出按钮正确显示 |
| 文档与日志 | Passed | `install_log.txt`、本报告、`FIX_HISTORY.md`、QA 报告均已生成 |

## Wan2.2 TI2V-5B 质量优先默认链路验收（2026-08-09）

| 项目 | 结果 | 实际证据 |
|---|---|---|
| 模型完整性 | Passed | Wan 主模型 9,999,658,848 字节；UMT5 FP8 6,735,906,897 字节；Wan VAE 1,409,400,960 字节 |
| ComfyUI 加载 | Passed | ComfyUI 0.31.0；UNETLoader 已列出 wan2.2_ti2v_5B_fp16.safetensors；RTX 4070 12GB |
| 真实 GPU 任务 | Passed | 任务 69/70/71 均 Succeeded；任务 71 为 320×416/49 帧/20 steps，31.647 秒，峰值 11,954 MiB |
| 视频可解码 | Passed | 任务 71 FFprobe：320×416、49 帧、约 2.009 秒、约 24.39 FPS |
| 脸部稳定性 | Passed with constraint | 竖幅参考图与 320×416 输出比例匹配时抽帧稳定；512×320 横幅比例不匹配时任务 69/70 首段出现块状伪影 |
| 默认链路 | Passed with constraint | 无人物参考仍可使用画幅匹配的 Wan2.2；有人物参考的新镜头默认使用已验证的 LTX v3 3 秒 Draft，并要求参考图与输出画幅匹配 |

## Git 与长期维护基线

- 分支：`main`
- 基线提交：`f5a98b9 chore: establish long-term AI Video Studio baseline`
- Remote：无（未创建或猜测远程仓库）
- staged 文件检查：Passed；未包含 `config/local.env`、真实凭据、模型、媒体、备份、日志、发布产物或前端依赖。
- 后续文档修订提交后，以 `git log -1 --oneline` 作为最新提交证据。

## 三镜头真实产物

项目：`Acceptance 3Shot 20260809_104019`\
Episode：`Three Shot Acceptance Episode`\
Master：

`C:\install\AI\Data\Output\Release\Acceptance 3Shot 20260809_104019\Episode001\Acceptance 3Shot 20260809_104019_Episode_001_MASTER.mp4`

封面与报告位于同一目录。Master 文件大小约 13.8 MB，技术 QA 分数 100。

抽帧人工复核文件：

- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_1.png`
- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_2.png`
- `C:\install\AI\Data\QA\AcceptanceFrames\three_shot\shot_3.png`

## 自动回炉边界证据

Shot 11 使用故意不满足 Episode 输出分辨率的测试条件，验证的是回炉机制本身，不是业务成片。任务 39—45 全部执行成功，链路为：

`ShotQA → I2V → Enhance → ShotQA → I2V → Enhance → ShotQA`

两次回炉 Seed 分别为 `287263580`、`482466601`，均不同。数据库日志同时记录了：原始 `Rejected` 状态、原始 QA 分数、修改的 Seed、新视频路径、新增强 QC 分数和新 QA 分数。第二次 QA 后达到上限，未创建第三个 I2V 任务。

## 已闭环修复的问题

以下问题均已完成“发现 → 定位 → 修复 → 重新测试 → Passed”：

- MySQL 凭据缺失：配置后完成备份、Migration、健康检查、CRUD 和真实任务测试。
- 备份脚本目标路径为空：改为明确的 `--result-file`，并对数据库不存在场景安全跳过 SQL dump。
- MySQL 初始化输入、JSON seed、索引长度：改为客户端 `source`、`JSON_OBJECT` 和前缀索引。
- `Guid` 格式化运行错误：清理全部非法插值格式并重新发布。
- 5 秒默认参数：从 73 frames 修正为 121 frames / 24 FPS，真实输出约 4.96 秒。
- MySQL `TINYINT(1)` 布尔读取错误：修复后锁定/解锁/禁止重新生成回归通过。
- Episode 音频查询排序字段错误：修复后 Episode render Passed。
- 发布目录被运行服务锁定且脚本误报成功：修复退出码检查，停止服务后重新发布并健康回归。
- QA 回炉复用 Seed、缺少增强和再次 QA、已完成任务被误判为活动任务：改为不同 Seed，记录完整回炉元数据，自动执行增强和再次 QA，并只把 Pending/Running 视为活动任务。

## 证据文件

- 安装与闭环日志：`C:\install\install_log.txt`
- 修复记录：`C:\install\AI\VideoStudio\docs\FIX_HISTORY.md`
- QA 汇总：`C:\install\AI\VideoStudio\logs\qa_test_report.json`
- QA 夹具目录：`C:\install\AI\Data\QA\TestCases\20260809_111257`
- 数据库备份：`C:\install\AI\VideoStudio\backup\20260809_100930`

## 长期项目基线接管验收

| 功能 | 状态 | 实际结果 |
|---|---|---|
| 项目规则与状态文档 | Passed | `AGENTS.md`、`PROJECT_STATE.md`、`NEXT_STAGE.md`、`CHANGELOG.md` 已创建/更新，内容按实际代码与运行时核对 |
| 文档一致性 | Passed | 根目录文档改为入口，详细说明统一到 `docs`；旧的“数据库未配置”结论已清除 |
| Git 安全边界 | Passed | `.gitignore` 排除 `config/local.env`、日志、备份、模型、媒体、发布产物和依赖；提交前执行 staged 文件检查 |
| 构建与脚本静态检查 | Passed | .NET 0 警告/0 错误、Vue build Passed、PowerShell AST Passed |
| 生产流水线回归 | Passed | `test_production_pipeline.ps1` health/文件/数据库/5 Shot RuleBased 分析通过；报告位于 `logs\production_pipeline_test.json` |
| QA 夹具回归 | Passed | `qa_test.ps1` 9/9 通过，最新目录为 `C:\install\AI\Data\QA\TestCases\20260809_122530` |

### 接管期间发现并修复

第一次运行生产流水线回归时，`Call-Api` 将 JSON 数组作为单对象返回，导致项目筛选为空并请求 `/api/projects//episodes`，真实结果为 HTTP 404。修复脚本的数组枚举后，重新执行同一回归入口，health、文件、数据库和 5 Shot 分析全部 Passed。此项已写入 `docs\FIX_HISTORY.md`，没有把失败删除或改名。

## 2026-08-10 真实生产压力测试门禁

本轮新增 `docs\REAL_PRODUCTION_TEST_REPORT.md`。3 个 TEST 项目共 15 集、120 镜头已真实入库，关键帧压力任务真实完成，A EP01 已生成实际 60 秒/1920×1080/30 FPS Episode 预览；技术 QA Passed，但 Episode 内容 QA Rejected（57.93）。

关键结论：

- 关键帧工作流误用已修复为 `workflowId=7`，Wan I2V 使用 `workflowId=87`；英文场景提示 A/B 通过，中文/混合长提示仍存在严重语义错配。
- 通过 FFprobe 的“可播放”不能替代人物一致性、场景一致性和剧情匹配；本轮明确保持人工复核和 TEST-only。
- TTS 无效 WAV、QA 回炉增强丢失、Episode 时长/音频不足均已发现并修复校验/合成逻辑；现有历史空音频和失败任务保留用于证据。
- 其余 14 集尚未完成全套 I2V/增强/正式 Episode，不能宣称全季交付或发布。

## 2026-08-10 Episode result viewer

| Item | Result | Evidence |
| --- | --- | --- |
| Backend and Vue builds | Passed | .NET build: 0 warnings/0 errors; Vue production build completed |
| Formal output lookup | Passed | TEST A EP01 returns V4, 60 seconds, 1920×1080, 30 FPS, audio and four retained versions; current source changes correctly mark it Stale |
| Not-ready render rejection | Passed | Episode 22 returns HTTP 400 with all eight missing formal-video shots |
| Browser UI automation | Passed | `npm run test:e2e` uses Vite `18081` proxy and local Chrome; 2/2 cover player/version history and not-ready render rejection |

## 2026-08-11 AI 人物质量专项

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 本地 AI 栈与模型扫描 | Passed | `docs\CURRENT_AI_STACK_2026-08-11.md`；ComfyUI 3.13.2、RTX 4070、现有 SD1.5/LTX/Wan/编码器/VAE |
| 静态人物 Baseline | Passed with limitation | 任务 598～610；正常脸可生成，但跨构图身份不稳定；全身任务 609/610 拒绝 |
| I2V A/B | Passed with limitation | 任务 611～618；3 秒可用，5 秒动作均需人工/部分拒绝；v2 不优于旧版 |
| v3 稳定默认复现 | Passed with manual review | 任务 624；94.19、0% 代理伪影、仍标记 NeedReview |
| I2V Preflight | Passed | Shot 168：角色参考、640×832 首帧、320×416、73 帧、3.042 秒、GPU 全部通过 |
| 连续 20 任务 | Passed | 任务 625～644：20/20 成功、0 失败、最大记录峰值 3355 MiB |
| 安全增强 | Passed | 任务 645：1920×1080/24 FPS，默认 `deflicker=false`、`interpolate=false` |

专项结论：当前可作为本机 TEST-only 的人物 Draft 生产默认；不批准 5 秒复杂动作、全身 Master 或无人审查的自动发布。

## 2026-08-12 任务提交与后台文本验收

| 验收项 | 结果 | 实际证据 |
| --- | --- | --- |
| 提交前拒绝无效任务 | Passed | `test_task_submission_preflight.ps1` 验证缺失 ControlNet 姿态图、缺失 LoRA、不存在项目、无效 TTS 音色均返回 HTTP 422，且不产生新任务 |
| 重试/重新执行防绕过 | Passed | 历史失败通用任务的 `/retry` 与 `/rerun` 在恢复/创建前再次预检，均返回 HTTP 422 |
| 镜头数据完整性 | Passed | 重复镜头号创建返回 HTTP 409；项目、Episode 与 Shot 关系由服务端验证 |
| 后台中文文本 | Passed | `test_text_integrity.ps1` 覆盖 13 个接口；角色资产编辑弹窗 Playwright 回归不含连续问号，疑似乱码输入被拒绝 |
| 页面回归 | Passed | `npm run test:e2e`：6/6；同时验证有历史成片、未就绪合成阻断、真正空成片状态、发布门禁、角色文本和快速切换时的旧响应隔离；实际浏览器复核确认角色编辑中文与空成片弹层 |
| 可构建与重新发布 | Passed | .NET build 0 warnings/0 errors；Vue production build Passed；重新发布后 MySQL、ComfyUI、FFmpeg 健康 |

本节只证明本机受监督环境的提交防护和页面回归。认证/RBAC/CSRF、统一资产路径、隔离恢复、完整音频 Episode、多 worker 竞态和 LAN/公网发布仍未执行或未完成，不能据此扩大发布范围。

## 2026-08-13 P0 边界与任务内核增量

| 验收项 | 结果 | 实际证据 |
|---|---|---|
| 资产/工作流路径边界 | Passed（代码级） | `test_asset_path_policy.ps1`：1360 个 Data 文件、7 个恶意候选；Data/Models/Workflows 受控解析、上传媒体探针和原子发布已覆盖 |
| LLM 出站边界 | Passed（静态） | `test_llm_egress_policy.ps1`：provider/host allowlist、HTTPS/loopback、DNS 私网阻断、Prompt/响应上限、禁止重定向和脱敏审计 |
| 队列租约/幂等 | Passed（静态） | `test_queue_lease_fencing.ps1`、`test_idempotency_fencing.ps1`；MySQL `NOW(3)` 表达式只读检查通过，Worker fencing 和批次键冲突已落地 |
| 外部进程/产物发布 | Passed（静态） | `test_external_process_boundary.ps1`；ArgumentList、取消子进程树、FFmpeg/ComfyUI/TTS/字幕临时文件发布 |
| 构建与只读 API | Passed | .NET 0 warning/0 error；Vue build；`/api/health` 200、数据库在线，未认证业务接口拒绝，恶意 Origin 无 CORS allow header |

本增量不等于生产发布：数据库仍需最小权限账户、正式迁移和隔离恢复；最近冒烟 ComfyUI 离线；真实双 Worker/Comfy 重启、GPU 生成、完整音频 Episode、人工质量验收和 LAN/公网仍为待验证/No-Go。

## 2026-09-12 末次工作流契约与候选绑定验收

| 验收项 | 结果 | 实际证据 |
|---|---|---|
| 候选导出来源绑定 | Passed（代码/回归） | `candidateId` 必填；候选快照绑定整片、镜头、字幕、音频、封面、审核版本和哈希，并要求来源回指 Ready asset/manifest 的稳定 ID/版本；排队/开始/落盘复核；同源 Ready 去重回归通过 |
| 自动重试来源不漂移 | Passed（代码/回归） | 原契约/路线/角色/动作/槽位/输入快照和父任务已绑定；来源变化返回 `RETRY_SOURCE_DRIFT`；替代路线显式化 |
| 模型版本锁定 | Passed（代码/回归） | 实际解析路径、权重哈希、运行依赖指纹；提交前强制重哈希；同大小同时间戳替换测试通过 |
| 契约与参数自检 | Passed | 10/10 工作流、LTX 请求 73/执行 65/解码目标 73、非法引导帧和实验路线负向测试通过 |
| 运行态健康 | Passed | `/api/health` 200；数据库、ComfyUI 0.31.0、FFmpeg、RTX 4070 在线；队列 0/0，活动任务 0 |
| 数据库 009 | Blocked | 目标表与迁移记录均不存在；应用账户无 DDL 权限，本轮未执行迁移 |
| 受保护 API / 浏览器 E2E | Blocked | `/api/auth/status` 为 configured=true/authenticated=false；业务入口匿名 401；computer-use 适配器返回 `nodeRepl.fetch request failed` |
| 新真实 GPU 短片与人工内容验收 | Unverified | 无已批准测试角色和人工审核；未把代码/夹具结果升级为真实输出或内容通过 |

本次收口仍不等于生产发布。正式报告中的“工作流契约 Passed”仅指契约静态检查及参数自检通过；真实 GPU 输出、参考资产审批约束、版本失效和发布闭环尚未验收。


<!-- campus-umbrella-20261026 -->
> 2026-10-26：项目45《伞向你倾斜》10秒校园新样片已完成，任务1419，实际1376×768/24FPS/240帧。技术与完整浏览器播放Passed；手部/道具细节NeedReview，原生对白语义Unverified，正式发布Blocked。恢复Data/CampusUmbrella20261025/run.json，completed=true，禁止重复提交；一次性续接定时任务已删除。见[本轮记录](CAMPUS_UMBRELLA_20261026.md).


<!-- character-library-20261026:start -->
> 2026-10-26：两个人物模型库与视频调用已完成技术验收，项目46。林安/周言各两张新参考，复用不可变人物版本；四个双视角镜头及一条真实工作台提交的新版本视频全部Succeeded，均864×480/24FPS/124帧。73项实际API与55项媒体/来源核验Passed，五条真实浏览器完整播放Passed。人物自然度仍需人工复核，发布Blocked。无新模型、无云调用、GPU并发1；原媒体与模型保留。入口[人物库](http://127.0.0.1:18080/#character-library)、[验收样片](http://127.0.0.1:18080/character-library-preview.html)。恢复Data/CharacterLibrary20261026/run.json，completed=true禁止重复提交。见[实施与验收记录](docs/CHARACTER_LIBRARY_20261026.md)。
<!-- character-library-20261026:end -->


数值修复：MySQL JSON将1.00规范化为1.0，人物库按声音字段的DECIMAL(5,2)精度恢复规范形式再校验SHA，旧快照未重写；提交后读取错误保留原始异常。UI卡片布局、调用版本说明和重复提交状态已做真实页面复核。


<!-- character-story-15s-20261028 -->
> 2026-10-28: Window Waiting is a real 15-second narrated local preview (final task 1565; source clips 1555/1562/1563, narration 1557–1559 and original music 1560). Technical and browser checks Passed; content and listening remain NeedReview, publication Blocked. See [the detailed report](CHARACTER_STORY_15S_20261028.md).


<!-- character-wide-cutaway-20261028 -->
> 2026-10-28：《窗边等候》增加无人窗边环境切镜：关键帧1566、H3视频1567、最终成片1572；8.75–10.25秒插入，保留原15秒音轨与字幕。技术和浏览器播放Passed；窗格/房间布局不完全一致，内容和听感NeedReview，发布Blocked；双人待审状态不变。[详细证据](CHARACTER_WIDE_CUTAWAY_20261028.md)。


<!-- character-fullbody-story-20261028 -->
> 2026-10-28：《窗边等候》新增林安全身远景，关键帧1575、H3视频1576、16.5秒成片1581；原生视频后段出现文字而Failed，仅截取检查过的前1.5秒。保留原窗景和旁白来源，第三句后移1.5秒，配乐略放慢。成片技术和浏览器播放Passed；面部、手指、窗格及新补裤鞋NeedReview，发布Blocked；被拒参考与双人待审状态不变。[详细记录](CHARACTER_FULLBODY_STORY_20261028.md)。

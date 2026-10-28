<!-- character-turn-repair-20261027:start -->
> 2026-10-27：林安左转回正定向修复已交付，原任务1550、新项目53/任务1551。沿用人物版本3、已批准参考36、同H3工作流和种子；原生864×480/24FPS/124帧。19项媒体来源及两个真实浏览器完整播放Passed；25时点试片检查可见左转、停顿、回正，转幅接近侧脸，人物细节和自然度NeedReview、发布Blocked。仅1次定向修复，无新模型/新人物版本/人工批准/云调用；原片及双人剧情待审检查点保留。恢复Data/CharacterTurnRepair20261027/run.json，completed=true禁止重复提交。 [验收报告](CHARACTER_TURN_REPAIR_20261027.md)、[视频对照](http://127.0.0.1:18080/character-turn-repair.html)。
<!-- character-turn-repair-20261027:end -->

<!-- character-single-preview-20261027:start -->
> 2026-10-27：用户新请求的独立单人动作试片已交付，项目52/任务1550，林安旧版#3、已批准正面参考36；864×480/24FPS/124帧，技术Passed，助手动作检查Failed（实际眨眼和头部回正，定向左转未明显命中），人工内容NeedReview、发布Blocked。仅一个新视频，无新图/新版本/模型/云调用；原双人剧情检查点与保持待审指示不变。恢复Data/CharacterSinglePreview20261027/run.json，completed=true禁止重复生成。 [验收报告](CHARACTER_SINGLE_PREVIEW_20261027.md)、[本次视频](http://127.0.0.1:18080/character-single-preview.html)。
<!-- character-single-preview-20261027:end -->

<!-- character-scene-20261027:start -->
> 2026-10-27：场景五输入与遮罩保存路线真实执行，修复通用宽高补丁覆盖区域尺寸的问题；修复大场景快照导致任务列表MySQL1038排序内存不足，先取有序ID再读完整行，5/100/500条实际回归Passed。页面修复场景改动未冻结保护、拒绝版本调用、项目切换上下文及数值字段过期aria-disabled。1522/1523方向和1525手部真实失败保留，隔离旧头部姿态修复路线尚未真实验证。用户保持待审，新图/视频未续提。[详细证据](CHARACTER_SCENE_CONTINUITY_20261027.md)。
<!-- character-scene-20261027:end -->

<!-- character-prompt-repair-20261027:start -->
> 2026-10-27：人物参考提示词统一为character-anatomy-v2，7人63槽逐张目检，16张新修复候选＋47张原图。24个真实本地任务/8张方向失败候选保留排除；556项媒体来源、100项跨语言提示词、12项实际API、16项人物库自测及63图真实浏览器加载Passed。技术/助手可见缺陷检查Passed；细节内容NeedReview，发布Blocked。无自动批准、新库冻结、新模型、云调用或视频；旧原图/检查点/5个不可变版本保留。新图在候选中待用户复核，旧拒绝版本不会被伪装成可用。恢复Data/CharacterReferenceRepair20261027/run.json，completed=true禁止重复生成。见[验收报告](CHARACTER_PROMPT_REPAIR_20261027.md)、[63图汇总](http://127.0.0.1:18080/character-reference-repair.html)。
<!-- character-prompt-repair-20261027:end -->

<!-- character-story-20261027:start -->
> 2026-10-27：修复缺失审核表与类型约束（管理员010/011）；阻止缺图回退、通用重试绕过和重复Comfy提交。1511多臂、1512双女复制及1516转身不足均保留真实失败与定向修复。恢复1516沿用原promptId，CPU1520取消未执行。真实页面复测修复了项目/集切换后旧调用预览残留，并清除人工确认状态；原媒体与冻结记录不变。 详见[本轮验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。
<!-- character-story-20261027:end -->

<!-- character-reference-pack-20261026:start -->
> 2026-10-26定向修复：近景混入裤装/鞋子造成小人拼贴或半身构图，保留原图并重写仅含头肩与衣领的提示词，选定6张近景。任务1452因Windows torch storage访问异常Failed，保留任务与崩溃日志；恢复既有Comfy并添加--disable-mmap，第二次定向候选1453Succeeded。补充每任务即时历史归档；崩溃前图使用原生PNG实际执行图进行来源核验。UI缺图/重复组合显示具体原因，旧版JSON小数哈希与null字段兼容不改写旧记录。最终技术Passed，人物内容NeedReview，发布Blocked。详见[本轮验收](CHARACTER_REFERENCE_PACK_20261026.md)。
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
> 2026-10-23：受控红本布局＋遮罩局部SDXL融合1211解决此前首帧缺书/坐姿失控，非编辑区像素保持。简化为坐姿取书，20/30步实际比较仅steps不同，选30步续接1214并生成最终1215。30步专属时限增至480分钟并经回归后在队列空闲部署；无中断或重复GPU。240帧、完整音轨、实际播放及恢复Passed。旧四张内容Failed与Blocked证据保留在blocked-before-resume。见[记录](REALISTIC_I2V_20261022.md)。
<!-- realistic-i2v-resume-20261022:end -->

<!-- realistic-i2v-20261022:start -->
> 历史：2026-10-22首帧阶段曾Blocked，后经用户明确要求继续，已在2026-10-23完成新1215成片；当前状态与恢复方式以上方交付记录为准。
<!-- realistic-i2v-20261022:end -->

# AI Video Studio 修复记录

<!-- seedvr2-20261022:start -->
> 2026-10-22：首次部分验收发现修复器按视频帧数结束时丢失音轨尾包，样片PCM47616样本而原轨49000，判Failed。改为画面编码后单独无损混流并比较AAC摘要；真实CPU队列1205/1206修复已生成样片/整片，视频帧逐帧不变，完整AAC与1202/1201一致，复测Passed，未重复GPU。另修复检查脚本inspect.py遮蔽标准库、FFmpeg新版本fps_mode选项、状态定位器歧义；所有相关复测Passed。见[定位与证据](VIDEO_DETAIL_SEEDVR2_20261022.md)。
<!-- seedvr2-20261022:end -->

<!-- qwen3-video-20261022:start -->
> 2026-10-22：本轮音频接入新增tempo并完成真实回归。验收参考音轨补齐后按N/SR/TB规范时钟并拒绝非有限相关值；恢复核验改用dashboard最新任务/数据库计数，初次通用列表快照范围错误已保留；进度观察器改用外层10秒接收上限处理心跳刷新。真实1198/1199/1200均一次Succeeded，最终解码、音轨、浏览器及正确恢复检查Passed；听感和内容待用户确认。 见[本轮记录](QWEN3_VIDEO_10S_20261022.md)。
<!-- qwen3-video-20261022:end -->

<!-- qwen3-tts-20261022:start -->
> 首次真实页面播放测试因通用任务列表优先返回历史Failed任务，找不到新配音1196。增加GET /api/audio/history，按配音类型与时间读取，原声音试听复测Passed。另验证取消杀死进程树、超时正确记录失败、音色/版本/资源队列约束。已有1196音频及旧视频保持，未再次模型推理。 详见[本地配音报告](QWEN3_TTS_LOCAL_20261022.md)。
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

## 2026-10-19 09时：静态样片的运动表达与播放检查

- 用户反馈画面近乎不变：确认旧提示词要求固定机位和少量叶片轻动；124帧不同不能证明动作充分。新增持续前移/明显枝叶动作提示词，保持同一首帧/seed/模型/规格，真实1176技术Passed，画面变化明显。
- 新增独立报告及稳定幂等/文件锁，提交结果未知时先停下查询；实际并发runner被拒绝，完成后复跑保留1176及旧1174/1175，无重复GPU任务。
- 新并排页尝试静音循环播放、点击画面暂停；异步播放请求采用序号避免重播与自动播放相互取消。两项真实媒体测试验证循环回绕、同步定位及实际呈现帧，截图等待视频帧回调，避免只核对currentTime造成静态截图误判。
- Vue构建、Python编译、两项浏览器检查和全片解码Passed；内容NeedReview、发布Blocked。见[动态记录](H3_CAMPUS_MOTION_20261019.md)。

## 2026-10-19：H3规格固定与768p对照验证

- 原本固定480p无法明确选择原生768p：新增独立quality768文件和规格，保留baseline480默认，提交/执行均校验profile与工作流，未知/混用/错误参数拒绝；H3质量门明确124帧。
- 两个受管工作流统一首帧追溯、OOM不改规格和输出审计摘要分支；1174已有执行快照及内嵌prompt，未回写其历史QC伪造新摘要。四个模型和工作流版本保持固定，无云端或低分辨率自动替代。
- 新服务全文件校验冷缓存曾超过检查工具的普通预检超时：先以600秒有界超时完成本地verify，9项真实接口复测Passed，未重复提交GPU任务。最近任务检查改用创建时间排序的dashboard，避免状态排序列表漏掉最新已完成任务。
- 真实1174/1175与独立WAV、完整解码和同步浏览器播放Passed；22项MiniMax、15项H3、14个契约、7项浏览器/UI回归及构建Passed。内容NeedReview、发布Blocked。见[详细记录](H3_NATIVE768_QUALITY_20261018.md)。

## 2026-10-18：60FPS实验工作流的目录误分类

- 新工作流文件名没有video/i2v字样，扫描器仅按名称将其登记为Image；提交前检查正确返回422，未创建GPU任务。
- 目录扫描器优先读取已登记契约的WorkflowType，未知工作流继续原命名规则；重新扫描后原ID1204变为ImageToVideo，Real-ESRGAN明确为Video。没有手工改任务/数据库状态。
- `.NET Release`构建/发布0警告0错误；13个工作流契约及5项实际API检查Passed。旧24FPS路线提交60FPS、新实验提交24FPS/121帧/错误尺寸均422且不增加任务；真实1169/1170完成60FPS新生成/交付。
- 内容仍待审核，原默认24FPS保留；详见[实验记录](LTX_NATIVE60_EXPERIMENT_20261018.md)。

## 2026-10-18：校园超分与当前状态校正

- 512×320源片仅普通缩放到720p，细节收益受限：新增官方Real-ESRGAN x2plus逐帧两倍超分，经显式sourceVideo契约和服务GPU队列执行1166/1167，再由CPU队列1168精确交付10秒/720p/30FPS。原片哈希不变；抽帧建筑边缘略清楚，未声称量化提升或动态内容审核通过。
- 新契约12项自检及5项实际预检Passed；缺少/错误sourceVideo槽、60FPS原生参数、不兼容尺寸均HTTP422且未增加任务。重复运行准备/增强工具保留原结果，未重复提交。
- H3下载恢复后四个文件已校验，任务1165真实输出视频/WAV，技术Passed。修正当前状态入口；下方下载Blocked文字对应早先阶段，内容/发布仍待审核。见[增强记录](AI_UPSCALE_CAMPUS_20261018.md)与[MiniMax报告](MINIMAX_LOCAL_INTEGRATION_20261018.md)。

## 2026-10-18：校园样片交付与下载续传

- 拼接只能固定30FPS输出、无法声明准确时长：新增可选交付时长/尺寸/FPS与源片充足性/输出帧数检查，真实任务1164交付10秒300帧；5项API预检Passed。不带参数的既有行为保留。
- H3下载进度JSON原子替换遇到WinError 5：增加有界重试，持续拒绝仍报错并保留文件；7项离线回归Passed，实际VAE续传已重启。没有修改ACL或提升权限，H3完整模型/声画验收仍Blocked。见[记录](CAMPUS_PREVIEW_20261018.md)。

## 2026-10-18：免登录与本地路线联调

- 用户忘记密码并要求取消登录：新增显式LocalOnly模式、回环监听限制、Host/Origin与签名CSRF，16项回归和真实403负向请求Passed；未重置密码。
- 新增横屏首帧契约时备注分隔符不匹配：首次预检拒绝、未入GPU队列；修正为既有`|`格式后，完整契约自测及真实任务1156 Passed。
- 无Guide LTX旧契约错误减8帧：任务1157的FFprobe为113帧、校验Failed。根据当前ComfyUI节点与实际文件升级实验契约为comfy031-v2；新任务1159完整121帧、24FPS Passed，保留1157失败记录。
- H3权重尚未完整：真实声画验证Blocked，下载和单次验收链继续运行；没有以单元测试或旧媒体替代样片。详见[本轮报告](MINIMAX_LOCAL_INTEGRATION_20261018.md)。

> 2026-09-11 新预览：项目22、任务1089/1090/1091真实生成；720p展示版已导出，但变脸/非预期嘴部动作及动作未完成导致内容Failed、发布Blocked。详见[本轮证据](NEW_PREVIEW_20260911.md)。

> 2026-09-08 H3第二批：提交预检及QA参数修正、Episode规格传递、增强音轨保留已改动；H3夹具14项和720p有声/无声实际后期测试Passed。未部署或GPU生成；许可地域确认、业务队列联调和内容审核未通过。见 [接入报告](H3_INTEGRATION_BATCH2_20260908.md)。

本文件保留本阶段真实发现、修复和复测证据。每一项的最终状态只有 Passed；历史上的未通过结果没有被删除，而是记录在“修复前结果”中。

| 2026-08-12 | 后台 API 无认证/CSRF/审计 | 安全边界缺失 | 增加回环单管理员初始化/登录/登出、PBKDF2 会话、CSRF、精确 CORS 和 `007_local_auth_audit.sql` | 隔离认证、首次初始化/重启、认证后文本/预检和 Playwright 回归 | 匿名业务 API 可直接读写 | 匿名默认拒绝；危险请求和审计闭环可验证 | Passed |

| 时间 | 问题 | 原因分类 | 修改内容 | 测试方法 | 修复前结果 | 修复后结果 | 状态 |
|---|---|---|---|---|---|---|---|
| 2026-08-09 | Wan2.2 首段脸部块状伪影 | 输入输出比例不匹配 | 新增 Wan2.2 TI2V-5B 工作流；界面按参考图比例建议 320×416/512×320；保留 LTX 默认 | 任务 69/70/71、FFprobe、抽帧复核 | 512×320 横幅输出有首段伪影 | 320×416 竖幅匹配输出稳定；模型峰值 11,954 MiB | Passed with constraint |
| 2026-08-09 | 数据库无法进入真实 CRUD/QA | 配置问题 | 使用用户提供的本地凭据配置 `config/local.env`；不写入报告 | 备份、Migration、健康检查、CRUD、真实任务 | 数据库依赖未通过 | 数据库在线；34 表；002/003 已应用 | Passed |
| 2026-08-09 | 备份 SQL 目标路径为空 | 脚本问题 | 使用明确的 `--result-file`，并预检查数据库是否存在 | `scripts/backup.ps1`，检查备份文件大小 | 备份脚本报路径错误 | 备份目录和非空 SQL dump 均验证通过 | Passed |
| 2026-08-09 | Schema 初始化输入失败 | 数据库/脚本问题 | 改用 MySQL 客户端 `source` 执行 schema；修复 JSON seed 和长路径索引 | `scripts/init_database.ps1`；读回 Migration、表和 preset | 初始化中断 | 34 表、3 QA preset、3 generation preset | Passed |
| 2026-08-09 | GUID 插值格式在运行时异常 | 代码问题 | 将非法 `Guid.NewGuid():N` 改为 `ToString("N")` | `rg` 全量扫描；.NET build；API 真实创建路径 | 运行时可能抛出格式异常 | 全量扫描无残留；build 0 警告/0 错误 | Passed |
| 2026-08-09 | 默认视频只达到约 3 秒 | 参数问题 | Smoke 与 I2V 参数统一为 121 frames / 24 FPS / 5 秒 | 真实 I2V task 4；FFprobe；技术 QA | 73 frames 结果约 2.99 秒 | 真实结果约 4.96 秒，技术 QA 100 | Passed |
| 2026-08-09 | QA 锁定状态判断错误 | 数据库/代码问题 | 修复 MySQL `TINYINT(1)` 返回 Boolean 的读取逻辑 | Approved、锁定、解锁、锁定时拒绝检查/重生成 | 锁定 Episode 检查接口错误放行 | 锁定时 Shot/Episode 检查均返回 409；解锁后流程正常 | Passed |
| 2026-08-09 | Episode render 返回未知字段错误 | 数据库 SQL 问题 | 修正音频结果排序字段，从不存在的 `s.shot_id` 改为有效字段 | 真实 3-shot Episode render | 合成返回 503 | Render task 24 成功，1920x1080/30 FPS/14.7 秒 | Passed |
| 2026-08-09 | 发布目录被运行服务锁定且脚本误报 | 运维/脚本问题 | 发布前安全停止目标服务；`publish.ps1` 检查 npm 和 dotnet 原生退出码 | 停止、发布、启动、HTTP health | 发布复制失败但脚本继续打印成功 | 发布成功；重启后数据库/ComfyUI/FFmpeg 全部在线 | Passed |
| 2026-08-09 | QA 回炉复用原 Seed | Workflow/参数问题 | 每次回炉生成新 Seed，并把 changedParameters 写入任务参数和日志 | Shot 11 两轮真实 I2V | 回炉参数可能完全相同 | 两个 Seed 不同，且日志可读回 | Passed |
| 2026-08-09 | QA 回炉没有自动增强和再次 QA | Workflow/代码问题 | QA-Retry I2V 自动排队 1080P Enhance；增强成功后自动排队 ShotQA | Shot 11 实际执行两轮完整链路 | 回炉后只停留在低分辨率视频 | 两轮均完成 `ShotQA → I2V → Enhance → ShotQA` | Passed |
| 2026-08-09 | 已完成 Enhance 被误判为活动任务 | 数据库查询问题 | 活动任务只统计 Pending/Running，排除 Succeeded | Shot 11 第二轮回炉 | 第二轮无法继续排队增强 | 第二轮 Enhance 和 QA 均成功执行 | Passed |
| 2026-08-09 | 回炉日志记录旧的 AutoChecking/0 分 | 代码问题 | 将本轮真实 `evaluation.Status` 和 `evaluation.Score` 传入回炉记录 | Shot 11 最终回归；读取 operation_logs 和 input_json | 原因和分数不准确 | 两轮日志分别记录 Rejected/73.05、Rejected/85.35 | Passed |
| 2026-08-09 | QA 夹具判定与时序/损坏文件兼容性问题 | QA/FFmpeg 问题 | 修复 FFprobe 数字解析、损坏文件判定、时序 Warning、PowerShell 参数过滤 | `qa_test.ps1` 9 个真实夹具 | 个别夹具结果与预期不一致 | 9/9 与预期一致 | Passed |
| 2026-08-09 | 队列回归不完整 | 任务队列问题 | 保留取消、暂停/恢复和任务重试路径，补充实际回归 | cancel task 46；retry task 47；检查 attempts/errorType | 缺少闭环证据 | 取消成功；缺失输入按预期失败并重试到 attempts=2 | Passed |
| 2026-08-09 | 生产流水线回归首次 404 | 测试脚本问题 | `Call-Api` 显式枚举 `Invoke-RestMethod` 返回的 JSON 数组，修复项目/集筛选 | 首次运行 `test_production_pipeline.ps1`；检查实际 HTTP 路径和服务端点 | 项目筛选为空，构造 `/api/projects//episodes`，返回 404 | 修复后同一脚本 health、文件、数据库和 5 Shot RuleBased 分析全部通过 | Passed |
| 2026-08-10 | VideoReview 后没有继续生产动作 | 生产状态机/UI 缺口 | `approve-video` 创建 CPU Enhance 任务；生产中心增加“通过视频并增强” | 真实 Shot 34：I2V 77 → Enhance 78 | 视频停在 VideoReview | Enhance 成功，Shot 进入 Completed | Passed |
| 2026-08-10 | Episode 中文输出文件名导致 Render 失败 | Windows 文件名边界 | 对 Episode Render 文件名做非法字符清洗，保留合法中文 | Task 81 失败后重跑 Task 82/85 | `C:\install\AI\Data\Output\\?????_001.mp4` 无法创建 | UTF-8 名称 `验收测试集-UTF8_001.mp4` 成功生成 | Passed |
| 2026-08-10 | Approved Episode 成片后无法导出 Master | QA 状态门禁使用了 production status | Render 保留锁定 Approved；QAExport 改读 `qaStatus` | Task 83 失败后重跑 Task 84/86 | Render 后 status=Completed 被误判未 Approved | Master 与 QA 报告成功导出 | Passed |
| 2026-08-10 | 本地管理边界过宽 | 安全边界 | CORS 限定 loopback 来源；媒体限制到 Data；异常返回 requestId 和通用错误 | API/CORS/media 负向回归 | 任意来源与 Data 外路径可进入边界 | 18081 精确 CORS；Data 200；server 404 | Passed with local-only constraint |
| 2026-08-10 | 关键帧错误回退到人像工作流 | 生产工作流问题 | 关键帧任务改用场景关键帧 workflowId=7，I2V 保持 Wan workflowId=87；关键帧提示增加英文化 | A/B 真实关键帧任务与抽帧 | Wide 场景生成泛化人像/随机建筑 | 英文废墟铁路探针生成语义匹配画面；中文长提示仍记录为未解决质量问题 | Fixed with quality limitation |
| 2026-08-10 | QA 回炉被已有 Enhance 吞掉 | 生产状态机问题 | QA-Retry 独立排队 Enhance，不受原 Enhance Pending 阻断 | A EP01 Shot 01 真实 Seed 回炉 | 新视频没有自己的增强/再次 QA | 代码修复并保留首轮缺陷证据；后续回炉可独立完成 | Fixed |
| 2026-08-10 | Episode 成片时长不足 | FFmpeg 合成问题 | Episode Normalize 按目标时长补齐/裁剪 | A EP01 V1 52.5 秒；V2/V3/V4 重跑 | 8×7.5 秒目标未达到 60 秒 | V4 实际视频 60 秒、1920×1080/30 | Fixed |
| 2026-08-10 | 混音音频流短于视频 | FFmpeg 音频问题 | 混音按视频时长补齐音频，避免 `-shortest` 截断 | A EP01 V4 技术 QA | 视频 60 秒、音频 52.5 秒 | V4 音频流实际 60 秒，技术检查 Passed | Fixed |
| 2026-08-10 | TTS 空 WAV 被误报成功 | 音频/缓存问题 | 校验 FFprobe 时长和文件大小；无效缓存不再命中 | A EP01 原始 46 字节 WAV；重试任务 413–422 | TTS task Succeeded 但不可播放 | 新校验明确 Failed；B 短文本验证生成 1.57 秒有效 WAV | Fixed with environment limitation |

## 最终回炉证据

Shot 11 的真实任务链：

`39 ShotQA → 40 I2V → 41 Enhance → 42 ShotQA → 43 I2V → 44 Enhance → 45 ShotQA`

最终 `qa_retry_count=2`，没有第三个回炉任务。最终测试使用故意不匹配的 9999x9999 Episode 输出标准，因此 Shot 最终保持 Rejected 是边界测试的预期业务结果；回炉机制本身验收状态为 Passed。

## 备份与数据安全

数据库修改前已创建备份：

`C:\install\AI\VideoStudio\backup\20260809_100930`

本阶段没有删除既有业务数据；清理动作仅删除了本轮临时 CRUD 测试记录。

## 2026-08-10 — Missing formal Episode result entry

| Time | Issue | Root cause | Change | Test | Before | After | Status |
|---|---|---|---|---|---|---|---|
| 2026-08-10 | Formal Episode output could be submitted but lacked a clear result-viewing lifecycle | Product/UI and task-history gap | Added output status/history API, source snapshots, active-render protection, stale detection, versioned output names and a player/download/version UI | Builds, live output lookup for TEST A EP01, and not-ready rejection for Episode 22 | Users could only infer the final result from the render action or shot cards | Users can see formal status, view retained versions and read the blocking or failure state | Passed |
| 2026-08-10 | “查看整集成片” button did not open the player | Vue event argument replaced the intended default version argument | Resolved the active output version inside `openEpisodeOutput` unless an explicit version object is supplied | New Playwright browser regression through Vite `18081` proxy | Player dialog never rendered after clicking the primary view button | Player/video/version history render; `npm run test:e2e` 2/2 Passed | Passed |

## 2026-08-11 — AI 人物质量专项

| Time | Issue | Root cause | Change | Test | Before | After | Status |
|---|---|---|---|---|---|---|---|
| 2026-08-12 | 后台角色资产及验收历史出现连续问号乱码 | 历史写入时文本已被替换为 0x3F；非前端字体或数据库 utf8mb4 配置问题 | 备份后执行可审计数据迁移，恢复可确定中文内容；对不可逆历史内容改用明确中文夹具/修复标记；新增服务端连续问号输入拦截 | 全库文本/JSON 扫描、13 个接口回归、浏览器资产编辑回归、后端构建与前端 E2E | QA-Adult-01 等字段及历史记录可见连续问号 | 后台可见文本无连续问号，新增/更新疑似乱码文本返回 400 | Passed locally |
| 2026-08-11 | 人物跨构图身份不稳定 | 纯文本 SD1.5 无单脸身份锚点，全身构图容易重复人物 | 建立 Character 15 单脸 Master、侧脸和半身分层参考；拒绝全身失败候选 | 任务 598～610，抽帧与 Face QA | full-body 候选可误入参考集 | 605/606 可作身份参考，608 仅作构图参考，609/610 明确拒绝 | Passed with limitation |
| 2026-08-11 | v2 I2V 表情/结构突变 | guide 过强且提示词放大眼睛/嘴部运动 | 新增 v3，复用旧版稳定结构，guide 0.45，320×416/73 帧/3 秒 | 611～624 同身份 A/B | v2 5 秒转头伪影最高 45.45% | v3 3 秒复现 94.19、0% 代理伪影；仍需人工复核 | Passed with manual review |
| 2026-08-11 | 后处理可能产生脸部鬼影 | Enhance 默认同时 deflicker + minterpolate | 默认改为安全缩放/补边/转码，插帧和去闪烁改为显式参数 | 任务 645、FFprobe、抽取首帧 | 默认插帧链可能放大局部鬼影 | 1920×1080/24 FPS，`false/false`，首帧内容未被裁切 | Passed |
| 2026-08-11 | 质量结果长期为空 | generation_results 未写回 QC 分数和 JSON | 增加结果质量写回，新增实验/Golden/Repair 数据表 | 任务 625～644、质量 API | 历史推荐平均分多为 0 | 新任务记录 quality_score/qc_json，20/20 成功 | Passed |
| 2026-08-11 | v3 I2V 部分种子尾帧眼部重影 | 单个 AddGuide 位于第 36 帧，且 `SamplerCustom.noise_seed` 未被覆盖 | 修复实际 seed 注入；默认将参考约束移至 `guideFrameIndex=72`，增加输出哈希多样性门禁 | 同种子 920500～920519 配对任务 677～696 vs 721～740；抽帧和 Comfy 历史 | 中点约束 1/20 脸部拒绝，任务 678 尾帧双眼重影 | 尾帧前约束 0/20 拒绝，平均 95.15，20/20 输出不同；任务 722 尾帧恢复 | Passed with manual review |

## 2026-08-12 — 任务提交绕过与空状态回归

| Time | Issue | Root cause | Change | Test | Before | After | Status |
|---|---|---|---|---|---|---|---|
| 2026-08-12 | 无效工作流/LoRA/音色仍可通过部分任务入口写入队列 | 任务提交、A/B、重试、重新执行和旧式拼接的校验入口不一致 | 新增统一提交前校验；重试/重新执行恢复原始输入后复检；拼接固定 CPU 并复检 | PowerShell 负向回归：ControlNet、LoRA、项目、TTS、retry、rerun | 可避免的配置错误会留下 Failed 任务或走错 GPU 队列 | 无效请求在写入/重入队前返回 422；无新任务产生 | Passed |
| 2026-08-12 | 创建镜头可形成同集重复镜头号 | 创建/更新未同时验证父级关系和唯一编号 | 服务端验证项目-Episode 归属、正镜头号、预查与数据库唯一冲突 | 重复镜头号 API 回归 | 同一 Episode 可出现歧义镜头编号 | 返回 409 和已有镜头 ID | Passed |
| 2026-08-12 | Episode 空状态 E2E 把“已有历史成片但当前镜头未就绪”误报为空成片 | 测试选择条件只检查镜头未就绪，没有检查历史输出 | 回归数据选择改为 `latestVersion` 和活动任务均为空的 Episode | Playwright 6/6 | 正确的历史版本 UI 会导致假失败 | 空状态和历史版本分别断言，回归稳定 | Passed |
| 2026-08-12 | 快速切换项目/分集时旧输出可能覆盖当前 Episode | 异步项目与 Episode 请求没有版本隔离，旧请求完成顺序不可控 | 项目与 Episode 选择加入版本号；旧响应、旧加载状态和不属于当前项目的点击全部忽略 | Playwright 快速双项目切换回归 | 当前集可能显示前一项目的历史成片 | 当前项目与当前集只接受本次选择的输出 | Passed |

## 2026-08-13 — P0 边界与任务内核增量

| 时间 | 问题 | 原因分类 | 修改内容 | 测试方法 | 修复前结果 | 修复后结果 | 状态 |
|---|---|---|---|---|---|---|---|
| 2026-08-13 | 客户端/任务/工作流路径边界分散 | 路径规范化与发布策略不统一 | 增加 `AssetPathPolicy`，统一 Data/Models/Workflows 受控解析、上传媒体探针、重解析点拒绝和临时文件原子发布 | `test_asset_path_policy.ps1`、`test_external_process_boundary.ps1` | 不同入口可能直接接收本机路径或半成品 | 1360 个 Data 文件、7 个恶意候选回归通过；外部产物成功后发布 | Passed with runtime gates |
| 2026-08-13 | LLM BaseUrl 出站边界不足 | provider、DNS、重定向和大小限制缺失 | 增加 allowlist、HTTPS/loopback、DNS 私网阻断、超时/大小上限、禁止重定向和脱敏审计 | `test_llm_egress_policy.ps1` | 未形成明确的安全出站决策 | 静态边界和审计覆盖通过；真实 provider 未执行 | Passed with runtime gates |
| 2026-08-13 | 旧 Worker 可能写回已恢复任务 | 进度/错误更新未绑定租约所有者 | 进度/错误按 `lease_owner` fencing；领取/心跳/deadline 使用 MySQL `NOW(3)`；生产批次幂等键冲突返回 Conflict | `test_queue_lease_fencing.ps1`、`test_idempotency_fencing.ps1`、MySQL 只读表达式 | 仅有代码路径，缺少 Worker 归属约束 | 静态回归通过；真实多进程恢复未执行 | Passed with runtime gates |

## 2026-09-12 — 候选绑定、重试来源与模型指纹收紧

| 时间 | 问题 | 修改内容 | 验证 | 状态 |
|---|---|---|---|---|
| 2026-09-12 | Ready 候选可能导出当前 Episode 的另一版本 | 导出强制 `candidateId`；候选保存整片/镜头/字幕/音频/封面/审核版本快照；队列、开始、落盘逐层复核；同源 Ready 去重 | QualityHarness、发布候选回归、最终发布目录复核；009 未落库，数据库行为待授权迁移后验收 | Passed（代码/静态）；DB行为 Blocked |
| 2026-09-12 | 自动重试可能改变动作和制作路线 | 保存原任务来源快照，继承契约/路线/角色/动作/槽位/输入；来源或审核变化返回 `RETRY_SOURCE_DRIFT`；替代方案显式且不继承通过结论 | 发布候选回归和质量自测 | Passed（代码/回归） |
| 2026-09-12 | 同名模型文件替换不会被发现 | 登记实际解析路径、权重哈希和运行依赖；提交 Comfy 前强制重哈希；同大小同时间戳替换回归 | 工作流契约自测、QualityHarness | Passed（代码/回归） |
| 2026-09-12 | 同一来源重复生成 Ready 候选 | 增加同源 Ready 检查，并保留幂等键与唯一冲突有限重试 | 发布候选回归；真实表未迁移 | Passed（代码）；DB行为 Blocked |
| 2026-09-12 | 候选来源只能凭路径和哈希追溯 | 整片、镜头、字幕、音频和封面来源回指 Ready asset/manifest，并保存 assetId、manifestId、版本和哈希；缺失血缘保持阻断 | 后端构建、发布候选回归；真实候选表未迁移 | Passed（代码）；DB行为 Blocked |


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

# 2026-10-22至23 纯本地写实首帧、20/30步对比与10秒Qwen配音交付：技术Passed

## 当前交付

2026-10-23 05:46（北京时间）已ReadyForUserPreview。最终任务1215 Succeeded，采用30步源片1213及其实际frame123续接1214，一次CPU合成5.886秒；实际1920×1080、24FPS、240帧、10秒，含完整Qwen中文旁白。内容仍NeedReview、发布Blocked；未替用户批准内容或发布。

最终文件：`C:/install/AI/Data/Artifacts/project-31/video/task-1215/v0001/v0001_realistic_i2v_qwen_10s_dad40433395a.mp4`。
SHA256：`dad40433395a3956d4472218fb31904411a046ba4f0643d74c1173e1c0e766bf`。
对比与播放：[本地对照页](http://127.0.0.1:18080/realistic-i2v-compare.html)。原B/C、源1198/1199/1200和Qwen原WAV均保持SHA，所有新生成及合成都走业务队列。

| 本轮任务 | 实际结果 | 耗时 | 尺寸/帧数 |
| --- | --- | --- | --- |
| 1211 受控红本局部融合首帧 | Succeeded；遮罩外像素保持 | 35.664秒 | 1536×864 |
| 1212 H3 20步 | Succeeded | 10856.310秒 | 1920×1080/24FPS/124帧 |
| 1213 H3 30步 | Succeeded，选作成片起段 | 16570.386秒 | 1920×1080/24FPS/124帧 |
| 1214 实际尾帧续接30步 | Succeeded，轻微抬头、手与书稳定 | 16596.502秒 | 1920×1080/24FPS/124帧 |
| 1215 一次合成完整旁白 | Succeeded | 5.886秒 | 1920×1080/24FPS/240帧/10秒 |

三段视频GPU任务共44023.198秒（12小时13分43.198秒）；5秒整卡采样8777个，显存采样峰值11867MiB，最低可用系统内存22MiB。任务内记录峰值最高11870MiB，与整卡5秒采样口径/时点不同，不据此断言30步更省显存。12GB显卡的原生1080p路线耗时很长，CPU卸载使32GB系统内存也非常紧张；本轮所有任务均一次Succeeded，无隐式降规格。

## 最终验收与选片依据

- 18个实际工作流契约及附加门Passed；42项MiniMax和28项H3回归Passed，30步专属时限480分钟（其余原生1080p仍360分钟）。Vue构建、.NET发布、Python编译Passed。
- 两组实际执行图归一化后仅steps及任务输入/输出文件名不同；首帧SHA一致、种子2026102220、提示词一致；没有额外LoRA、超分、插帧或成片修复。
- 两组各124帧完整解码、各124个不同哈希；最终240帧完整解码、240个不同哈希。续接首帧SHA49add1dc8a9b3a574d2b393b1b26e939ce73845665dede5d41595e8c8f0a587d与选中视频实际frame123一致，未用旧片或静帧填充。
- 采用30步：红本转动时的大小变化较小，末帧握持较稳。拿书、停稳、抬头动作可见；手指边缘仍偏软、皮肤和书面有生成平滑感，背景人物模糊。只是本次场景的视觉选片，不虚构电影感分数或等同其他模型水平。
- 原始1196 Qwen WAV保持；1.32倍tempo保持音高，延迟0.12秒后完整9.874041667秒、236977样本，未截断。最终10秒音轨与拟合参考相关系数0.999958041，峰值-5.278dB/RMS -21.205dB。
- 3项真实视频浏览器检查Passed：20步单路先行播放、20/30同步跳转/播放/放大、完整10秒成片；最终ended=true、time=10、decodedFrames=240、无视频或页面错误，双源片暂停且静音，最终一路音量1。生成期间浏览器验收使用CPU视频解码，避免争用显存。4项新对照页夹具和7项MiniMax夹具Passed。
- 六项pose实际预检+一次422拒绝、两组H3预检+跨模板拒绝、29步/768p30步/文生视频30步三个真实端点拒绝Passed，失败输入未创建任务。

本地API27676、Comfy29860、MySQL与FFmpeg在线，Worker启用，CPU/GPU并发均1，两个队列空闲；下载、进度观察器和生成runner已结束。分支main、HEAD d6ec38d076a8b0336d349c36df5c123f2c941ac8，原脏工作保留，未提交/推送；未改数据库结构或全局环境。

恢复先读Data/RealisticI2V20261022/run.json（ReadyForUserPreview）与verification-summary.json；`run.py --stage check`只核验既有任务/SHA。旧Blocked、NoUsableReference及验收报告保存在blocked-before-resume，下面保留完整过程；不得因旧首帧失败把当前已交付成片误判为尚未生成，也不得自动追加GPU任务。

## 过程记录（历史，保留原失败与续接证据）


## 继续实施：用户要求输出成片

用户在上一轮明确说“继续，保证结果输出出来”，授权继续解决首帧并完成交付；不再因旧的单张姿态尝试范围重复要求批准。旧Blocked状态、NoUsableReference、检查和源码已复制到Data/RealisticI2V20261022/blocked-before-resume，未改写旧失败。

方法改为受控局部布局：使用本轮新生成1209作为人物/背景来源，以程序确定唯一闭合红本的位置、透视、纸页和接触阴影，然后经RealVisXL局部低去噪融合。CPU布局及遮罩是明确标记的派生输入，不伪称原始模型照片；真实融合任务1211通过业务GPU队列，输出SHA256 2e598e022b6036d6a12ae5eff01d197f66a84b6380667d3093bc67eb8ef74cf4。遮罩外人物和背景像素与1209完全一致；实际PNG记录的布局/遮罩SHA正确。

构图公开简化为坐姿拿起身旁的红本，不再要求站立转换；服装按实际首帧为深青色卫衣，无强制添加不存在的背包。首帧审查已选1211进入I2V，内容仍NeedReview，书封面较平整。H3同首帧/同种子2026102220/同提示词对比20与30步；20步实际任务1212已开始。所有视频仍原生1920×1088采样，裁成1920×1080，24FPS/124帧。

新增realvisxl_book_reference_api显式firstFrame/editMask槽位契约；完整18个工作流契约及附加门复测Passed，Python编译、4项对照页夹具和服务发布Passed。API13156，Comfy29860保留；GPU任务活跃期间不重启服务或Comfy。30步、选片、真实尾帧续接、10秒Qwen合成及真实播放检查继续执行中。


用户已授权依次实施：SDXL写实首帧、单一取书动作、H3同首帧/同种子/同提示词20步与30步对照；检查脸/手/道具后，选择路线制作10秒Qwen中文旁白成片。保留原生1920×1088采样、上下各裁4行交付1920×1080，24FPS。只使用本地模型，不调用生成云服务。

恢复入口：`C:/install/AI/Data/RealisticI2V20261022/run.json`。所有真实图像、视频、声音与合成均走业务队列。未知提交结果先核查任务，不重复提交；GPU并发1。新30步使用独立固定模板，20步老路线保留。内容NeedReview，发布Blocked。

初始核验：main / d6ec38d076a8b0336d349c36df5c123f2c941ac8，大量既有脏工作保留；API33496、Comfy29860在线，Comfy队列空，4070 12GB显存约1.5GB占用，C盘约71GiB可用。MySQL与FFmpeg在线，未改数据库结构。

RealVisXL V5.0 FP16固定版本ac93e0dda1f6d448cae19bbfab8c5e720a5e48bc，大小6,938,065,488字节，SHA256 6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80，已下载并完整校验，位于中央Models/checkpoints目录。无新的Comfy运行环境或依赖安装。

## 接入与回归

- 新增固定30步1088 I2V模板，服务和页面只允许native1080图生视频选择20/30步；768p、480p、文生视频仍固定20步。实际执行最多360分钟，不隐式降低尺寸或帧数。
- 首帧工作流realvisxl_reference_api注册为1410，1536×864、35步、CFG5.5、dpmpp_sde/karras、tiled VAE。新项目31。首帧1536×864是公开声明的SDXL尺寸；H3视频继续原生1920×1088采样。
- 构建Passed（0警告0错误）；42项MiniMax、28项H3回归、7项MiniMax页面测试、2项对照页路径/待生成状态测试、Vue构建Passed。
- 工作流契约测试最初因模型尚未下载Failed；下载完成后16个实际契约及额外槽位/实验门测试全部Passed，保留初始结果。
- 3项真实API拒绝检查Passed：29步、768p30步、文生视频30步均422且任务列表保持，未触发GPU。
- 已部署源码与前端，API40708，Comfy29860保留。发布前副本在Data/Deploy/BeforeRealisticI2V_20261022，改前源码在本轮source-before目录。
- 新对照页`/realistic-i2v-compare.html`，实际路径只从run.json中的安全Artifacts文件读取；待生成时禁用播放。

## 首帧内容检查与新的显式授权

1207：真实皮肤/衣物较好，但人物过近，手、书、背包不在画面；内容Failed。1208：扩大构图后仍坐着看打开的书，且有另一本红书；内容Failed。1209：加强站姿并排除阅读后仍为坐姿，书和背包缺失；内容Failed。三个任务技术均Passed，绝不替换成动作语义通过。

初次加两次定向修复已耗尽AGENTS.md第6节预算，prompt-only路线Blocked。已向用户说明并获得原文授权“批准一次姿态约束生成，并继续原计划”；记录在pose-authorization.json，允许一张新的姿态控制首帧，通过后继续20/30步及10秒成片。未以换名规避预算。

新增程序绘制的COCO18站姿约束图（不是生成照片），1536×864，SHA256 285683c14cb05c4cbd6849f8d90e473cbed85abdb4d304fb3b8ca87a01440746；手靠近长椅端点，双脚固定在地面。SDXL专用OpenPose模型来自作者[xinsir/controlnet-openpose-sdxl-1.0](https://huggingface.co/xinsir/controlnet-openpose-sdxl-1.0)，固定23f966cd5cfdd3f7729c903e243d87152162d2b7，2,502,139,104字节，SHA256 b8524e557a7df60d081f5d4a0eb109967d107df217943bf88c2d99b9ebcc06c5。工作流固定ControlNet强度1.0、0–90%步骤，仅显式pose槽位；模板SHA256 97bf578427a6505d22f7cefa7ca7f5ab166af21da14e8f0be3bb42fef14bcee7。

## 最终实际结果

| 任务 | 方法 | 尺寸 | 耗时 | 任务显存峰值 | 技术 | 内容检查 |
| --- | --- | --- | --- | --- | --- | --- |
| 1207 | RealVisXL初次 | 1536×864 | 49.435秒 | 6460MiB | Passed | Failed：人物过近，手/书未入镜 |
| 1208 | 扩大构图修复 | 1536×864 | 47.697秒 | 6384MiB | Passed | Failed：坐着阅读，出现多本书 |
| 1209 | 强化站姿修复 | 1536×864 | 45.303秒 | 6331MiB | Passed | Failed：仍坐着，红本缺失 |
| 1210 | 用户额外批准一次OpenPose | 1536×864 | 70.486秒 | 9351MiB | Passed | Failed：站姿但背影、白衣、红包，缺少红本 |

1210的实际PNG内执行图确认：RealVisXL与SDXL OpenPose正确加载、正负提示词和seed2026102206正确、姿态图SHA正确，35步/CFG5.5/控制强度1.0正确。其余三张也逐一核对实际执行图与提交提示词/种子一致。当前属于构图与物体语义失败，不能假称参数未进入模型，不能作为拾书动作的首帧。四张图片与执行记录全部保留。

三轮prompt-only路线Blocked；用户追加批准的一张姿态图也已用完。最终run.json为Blocked、integrationStatus=Passed、contentStatus=Failed。reference-review.json为NoUsableReference；没有填写selectedCandidate；不绕过首帧审查。**未提交新20步/30步H3视频、续接或10秒合成任务；这些阶段均Blocked。没有新的10秒视频可交付。** 现有Qwen音频、旧1198/1199/1200/1206和B1201逐一SHA校验保持。

整卡5秒采样47个，峰值9458MiB，最低可用系统内存6870MiB；所有图像在RTX4070 12GB本地执行。最终API24924、Comfy29860、数据库与FFmpeg在线；Worker启用，CPU/GPU并发均1，业务与Comfy队列空闲，观察器与下载进程已退出。未修改数据库结构，未提交或推送Git；main/d6ec38d076a8b0336d349c36df5c123f2c941ac8，原脏工作保留。

## 修复和最终验收

- Pose工作流首次预检发现Windows文本换行导致契约SHA漂移；改为确定性UTF-8字节输出，源码与中央模板均97bf578427a6505d22f7cefa7ca7f5ab166af21da14e8f0be3bb42fef14bcee7。原预检Failed报告保留，未误提交GPU。
- 旧TaskSubmissionPreflightService只接受legacy controlImages/controlImagePath，与显式pose槽位契约冲突。现在仅在完整契约Prepare成功、声明pose槽位且本地文件存在时接受；缺失、错误身份角色、空值、越界路径及混用legacy仍拒绝。六项实际预检及一次422提交拒绝全部Passed，无新增任务。
- 最终17个实际工作流契约及附加门测试Passed；42项MiniMax、28项H3回归Passed；20步与30步各自实际预检通过，30步绑定20步模板拒绝，三项Passed但不代表实际30步推理已完成。
- 29步/768p30步/文生视频30步三个真实端点拒绝均422，未创建任务。
- 7项MiniMax页面夹具、4项新对照页夹具Passed；新页增加Blocked/Failed文案和四张实际首帧审查。1项真实浏览器验收Passed：四张均真实解码1536×864、显示未选用原因、没有设置任何视频src、没有冒充成片、无页面错误。截图和结果在browser-reference-review.*。
- Python脚本编译、Vue构建和.NET发布Passed；构建保留原有Rollup注解/大包提示。恢复只读检查应只核验既有任务与SHA，禁止新增生成。

## 复核入口和后续条件

[首帧对比页](http://127.0.0.1:18080/realistic-i2v-compare.html)展示真实1207–1210及未选用原因，原B/C页面保留。系统已准备好本地20/30步接入，但当前缺少一张人物、手和唯一红本均正确的首帧。继续需要合格首帧，或用户对新的首帧方法及尝试范围作出明确授权。不得自动反复抽种子，也不得用旧视频填充新的成片。

恢复先读取Data/RealisticI2V20261022/run.json、reference-review.json和verification-summary.json。`python tools/realistic_i2v/run.py --stage check`只核验既有任务，不清除Blocked原因。GPU比较、续接、Qwen合成和真实视频播放未执行，不能写为Passed。

最终恢复实测Passed：执行--stage check前后最近100个任务ID保持，Blocked阶段、blockerCode和错误原因保留。21个本轮源码/模板/配置文件的凭据模式与末尾空白扫描Passed，git diff --check Passed，Git已跟踪模型/生成音视频数量0；模型、参考姿态和全部生成媒体实际位于仓库外。final-source-audit.json保存检查结果。审计脚本第一次因Windows默认GBK读UTF-8报告失败，显式UTF-8后通过，未改业务或媒体数据。

续报：20步1212已Succeeded，10856.310秒、任务显存峰值11870MiB；实际原生1080p/24FPS/124帧，逐帧完整解码124个不同哈希，真实浏览器完整播放Passed。抽帧可见接触、拿起、停稳，手指中段略软，书本透视变化较大，内容NeedReview。队列空闲后发布30步专属480分钟时限（28项H3回归Passed），API27676，Comfy29860保留；30步1213已运行，首帧/种子/提示词保持。页面允许单路已完成源片独立预览，GPU生成期间浏览器测试禁用GPU/硬件视频解码，避免争用显存。

2026-10-23续报：30步1213已Succeeded，16570.386秒，任务显存峰值11358MiB；124帧/124个不同哈希。两组真实执行图已归一化比较，除steps及任务文件路径外完全一致，首帧SHA和种子保持。同步播放/跳转/局部放大真实浏览器Passed。视觉选30步：书本转动时大小变化较小、末段握持较稳定；手指略软、皮肤与书面仍有平滑感，内容NeedReview。comparison-review.json明确为预览选片，非用户内容或发布批准。续接使用30步实际frame123，继续30步原生1080p，只做轻微抬头并保持手和书位置；全部步骤完成后继续10秒配音合成。

最终收尾：ReadyForUserPreview下分别执行--stage check和--stage assemble，任务列表/成片SHA均保持，没有新增任务（Passed）。26个本轮源码/配置/模板文件的凭据模式、末尾空白检查、git diff --check Passed；Git已跟踪模型或生成音视频数量0。所有生成runner、进度观察器和下载进程结束，两个队列空闲。源码前后对照在Data/RealisticI2V20261022/source-changes.patch，原脏工作和备份保留。

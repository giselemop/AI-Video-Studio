"""Final record from actual completed media, diagnostics and playback evidence."""
from run import *
s=read(FOLDER/'run.json')
if not s.get('completed'):raise RuntimeError('Finish real acceptance first')
summary=read(FOLDER/'execution-summary.json');api=read(FOLDER/'api-admission-checks.json');before=read(FOLDER/'audit-baseline.json');after=read(FOLDER/'audit-new.json')
rows=[]
for clip in CLIPS:
    name=clip['name'];task=s[name+'DriverTaskId'];duration=read(FOLDER/f'task-{task}.json')['task']['durationMs']/1000
    rows.append(f"| {name} | {clip['startFrame']/24:.3f}–{(clip['startFrame']+clip['frames'])/24:.3f}秒 | {clip['frames']}帧 / {clip['frames']/24:.3f}秒 | {task} / {duration:.1f}秒 | {s[name+'FinalTaskId']} |")
repair_text=('双人初样口部更收敛，但男方始终注视手机，回应偏冷。第一轮保持seed/原声/采样不变，只改视线与收尾提示，实际未明显实现视线交流，因此未选用，不把提示写入视为改善。第二轮采用嘴部/姿态分离：用新1350音频驱动的嘴部语义点[6,12,14,17,19,20]，配合原1299已认可的姿态、视线及非嘴部表情模板，并使用官方闭唇基线归一化。固定版LivePortrait官方源码未改动，运行时独立适配，8份既有权重保持。每人57帧的R/t/scale及非嘴部表情字段逐项保持，断言仅指潜在运动字段，不是输出非嘴部像素完全不变。最终参考取1346片段首帧并缩放，明确是现有输入而不是新生成关键帧。姿态窗始于原生56帧（原片约6.240秒），比原声窗早0.010秒；仅复用原姿态节奏，新嘴部与原声窗保持不动。经实际定格选用分离候选，闭唇笑容可能略紧，仍需用户观看。初样及未选提示候选全部保留，见hybrid-review.json、wide-repair-review.json和hybrid-inputs.json。' if s.get('wideHybridSelected') else
             '双人初样口部更收敛，但男方始终注视手机，回应偏冷，因此保留初样后做一次定向修正：参考、原声、seed、音频引导、步数和尺寸保持，只调整短暂看向女方、眉部放松及闭唇收尾的表演提示。实际执行提示与提交值一致；经新旧候选定格与表演检查后选择修正版，初样驱动、两个人物表演、合成和canvas全部保留。见wide-repair-review.json。' if s.get('wideRepairSelected') else
             '双人定向表演候选保留为独立版本；具体选片及取舍见本轮实际检查记录。' if s.get('wideRepairDriverPath') else '')
text=f'''# 口型同步与双人回应小样验收

2026-10-25，项目{s['projectId']}，阶段ReadyForUserPreview。技术 **Passed**；内容NeedReview；发布 **Blocked**。两段小样已完成，原项目40任务1346十秒版与模型保留。本轮没有替换整段十秒成片。

同步对比：<http://127.0.0.1:18080/dialogue-sync.html>。支持片段切换、正常/半速、声音选择、逐帧、女方/男方面部及说话者嘴部查看。

| 片段 | 原片时间窗 | 交付 | 新音频驱动任务/耗时 | 最终任务 |
|---|---|---|---|---|
{chr(10).join(rows)}

女方片段含完整“哟，约会回来了？”，双人片段含完整男方“这还差不多。”及女方聆听。窗口外台词仍在原十秒版保留。最终文件：

- 女方：`C:/install/AI/Data/{s['closeFinalPath']}`，SHA256 `{s['closeFinalSha256']}`。
- 双人：`C:/install/AI/Data/{s['wideFinalPath']}`，SHA256 `{s['wideFinalSha256']}`。

## 实际调整

本轮使用已认可的Klein K05女方参考和1328双人参考生成新的InfiniteTalk音频驱动，再沿用LivePortrait/眨眼保护转移；最终双人分离候选的参考和姿态来源如下。没有下载新模型或使用云推理。原声未改字、重配或变速。

{repair_text}

既有Lightx2v和8步采样保留，音频CFG由旧驱动的1调整为2；[InfiniteTalk官方说明](https://github.com/MeiGen-AI/InfiniteTalk)推荐LoRA条件下从2起验证。双人音频区域按当前参考图实际人脸中心中点{s['splitRatio']:.6f}绑定，左女右男。提示词对应完整说话与静默聆听，强调放松下颌、细小连贯颊眉变化和渐进收尾，未把整段强制设为闭口。未通过整体降低动作系数来压小嘴部，LivePortrait整体系数为1。

基线的嘴部几何与原分角色干声能量粗诊断未显示固定整段延迟，因此未移动音频时间轴。该诊断及新旧逐帧数据见audit-baseline.json/audit-new.json。音量与张嘴幅度不对应每个音素，不能把相关系数、最优能量滞后或嘴部间隙称作口型准确率，也不能据此保证自然度改善。

两段QHD后期仍为SeedVR2强度0.30，加同帧源频段回补0.65；眼睛、嘴部及非皮肤区域在细节合成前后保持，保护断言不扩大成最终有损视频逐像素不变。最终2560×1440为后期输出，并非原生2K。

双人两张脸分别按左右方向处理57帧，并通过不重叠支持区域合成；最终候选明确结合新嘴部和原姿态驱动，面部之外为现有片段首帧静态参考。因此本轮主要验证嘴形、聆听和面部回应，未恢复全身或手部新动作。

## 实测验收

- 新原生驱动51/57帧、25FPS；交付48/54帧、24FPS，2.000/2.250秒。选用源、驱动、表演、canvas、QHD、细节、画面与最终片完整解码、帧数/画幅/时长/SHA **Passed**，见final-verification.json。
- 四份分角色驱动WAV逐采样等于原干声的精确截取；两侧播放共享同一原声片段，最终AAC包和解码PCM与基线片段分别逐字节一致。截取基线时AAC编码一次，之后新片无损复制，不宣称该截取AAC与十秒原AAC按包直接对应。画面换轨后视频包保持。
- 基线片段首尾8个抽查帧与原1346相应时间帧对应；字幕仅按窗口偏移，台词不改。实际Comfy成功历史已归档，并核对执行中的音频CFG、帧数及双人区域，而不只看预设JSON。
- 新短合成分支的真实57帧预检、旧151帧兼容预检与{api['invalidPostCount']}个无效POST拒绝 **Passed**，没有测试任务入队。覆盖未知/非字符串profile、脚本/清单SHA、错误帧率帧数、角色回执交换、遮罩SHA、正式父项和资源类别。旧合成151帧边界保持。
- 嘴部/姿态分离分支、旧表演分支与合成分支真实预检及11个无效POST拒绝 **Passed**，覆盖姿态SHA/越界/错误帧数、方向/时长/强度/区域、正式父项及资源类别。旧表演CPU协议回归28项 **Passed**；真实GPU推理另以已出片任务及回执为证，不能把协议夹具当作生成质量结果。
- 实际浏览器两段正常和半速均完整播放；声音新/旧/静音、切段、逐帧和局部查看 **Passed**，控制台错误0。browser-playback.json、AX和实际截图保留。
- {summary['olderVersionHashesVerified']}份既有版本与输入SHA复核一致，模型目录{summary['modelMetadataFilesUnchanged']}份文件集合/大小/mtime保持，既有工作流合同逐项保留。没有提交/推送或清理脏工作，main原HEAD d6ec38d。
- GPU最大并发1，设备采样显存峰值{summary['sampledPeakDeviceVramMiB']}MiB，可用RAM最低{summary['sampledMinAvailableRamMiB']}MiB，磁盘最低{summary['sampledMinFreeDiskGiB']}GiB。增强音频条件增加计算；加载阶段内存余量较低，数值为采样而非单进程精确峰值。仅在全部队列空闲时请求释放Comfy缓存，未删模型/历史。曾按8GiB预留检查未过（可用7.9GiB）；实际表演峰值约1.26GiB，改按实测峰值加2GiB且至少4GiB预留复核通过，原失败检查保留，并未降低推理分辨率或更换模型。
- 原18080保持，18081仅在队列空闲时切到独立构建；原队列与实验队列均恢复本轮前状态，DB/Comfy/FFmpeg在线。新旧构建和成片保留，人工与发布门保持。

首次工作流预检因旧服务的合同快照未加载新登记而拒绝，未创建GPU任务。失败预检保留，使用显式i2v新版本、空闲切换服务和重新扫描后通过，不绕过合同或手动改任务状态。

辅助定格脚本曾与标准库inspect重名，双人任务提交前退出。改名inspect_contacts.py后仅提交尚未入队的双人任务，已完成女方驱动未重跑；加入标准库重名检查，避免复发。

每个字的唇齿闭合、人物身份细节和表情自然度仍需观看判断。本轮保留所有真实候选和诊断，未虚构同步、美学或真人表演评分。

## 恢复

入口`C:/install/AI/Data/DialogueSync20261025/run.json`。已完成阶段只读核验，不再重复生成；下一轮开独立版本。证据包括各任务/回执、prepared-inputs.json、speaker-region-check.json、api-admission-checks.json、final-verification.json、comfy-executed-history.json、execution-summary.json、browser-playback.json、source-manifest.json和final-environment-verification.json。
'''
(ROOT/'docs/DIALOGUE_SYNC_20261025.md').write_text(text,encoding='utf-8');print('Final pilot report written')

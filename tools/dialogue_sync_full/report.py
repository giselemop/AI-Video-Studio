"""Chinese acceptance record drawn from actual finalized files and task receipts."""
from run import *
s=read(FOLDER/'run.json')
if not s.get('completed'):raise RuntimeError('Finish actual acceptance first')
e=read(FOLDER/'execution-summary.json');v=read(FOLDER/'final-verification.json');rows=[]
for shot in SHOTS:
    i=shot['index'];driver=read(FOLDER/f"task-{s[f'driver{i}TaskId']}.json")['task'];qhd=read(FOLDER/f"task-{s[f'qhd{i}TaskId']}.json")['task']
    rows.append(f"| {i} | {shot['start']}–{shot['start']+shot['frames']-1} | {shot['frames']} | {s[f'driver{i}TaskId']} / {driver['durationMs']/1000:.1f}秒 | {s[f'qhd{i}TaskId']} / {qhd['durationMs']/1000:.1f}秒 |")
recovery=read(FOLDER/'driver-recovery.json')
text=f'''# 完整十秒口型与双人回应升级验收

2026-10-25，项目{s['projectId']}。技术 **Passed**，内容NeedReview，发布 **Blocked**。最终2560×1440 /24FPS /240帧 /10秒，为后期QHD输出。原项目40十秒版与项目41小样保留。

[本机前后同步对比](http://127.0.0.1:18080/dialogue-sync-full.html)，支持完整正常/半速播放、原声选择、逐帧和人物局部查看。

成片：`C:/install/AI/Data/{s['finalPath']}`。SHA256 `{s['finalSha256']}`。

| 镜头 | 原/新全局帧 | 交付帧数 | 新原声驱动任务 / 实际耗时 | QHD任务 / 实际耗时 |
|---|---|---|---|---|
{chr(10).join(rows)}

双人驱动队列监控1373在30分钟时标记 **Failed / TASK_TIMEOUT**，原记录保留。实际Comfy原prompt随后成功完成，执行耗时{recovery['actualComfyDurationMs']/1000:.1f}秒。经真实历史、151帧完整解码和SHA核验，通过独立CPU队列{recovery['recoveryTaskId']}无损接入，视频及音频包保持，没有重提GPU推理或手工改数据库状态。后续GPU任务前确认Comfy空闲，避免与尾段计算重叠。新构建仅为该固定151帧工作流设置60分钟上限，其余短镜头/未知工作流/CPU时限保持；33项CPU回归含5项时限边界通过，见driver-recovery.json、deadline-regression.json。

## 实际方法与范围

按已认可两段小样的方法扩展三个完整镜头。使用已有InfiniteTalk/Lightx2v、8步、音频CFG2及原分角色干声，重新生成57/46/151帧、25FPS的三个驱动。没有更换、下载新模型或调用云推理。女近景与男反打用原有闭唇参考及dialogue-blink-v1表演/眨眼保护；这两个近景转移新驱动的完整面部表演，男反打的抬头与视线因此和旧版不同，切回双人的衔接仍需观看判断。双人镜头则只替换嘴部并保留已认可姿态。

六秒双人镜头使用独立dialogue-hybrid-full-v1固定151帧分支：新音频驱动的嘴部语义点[6,12,14,17,19,20]，原已认可1299的完整姿态与非嘴部表情，官方闭唇基线归一化。每人151帧的R/t/scale及非嘴部潜在表情字段严格保持，不声称解码后非嘴部像素完全相同。参考使用原完整双人镜头的1328初始参考，与小样的中段首帧参考时刻不同；这是将同一方法扩展到完整镜头的明确选择。双人面部以外仍为静态原参考，不生成新的手部或全身动作。闭唇笑容可能偏紧，精细口型和自然度仍需观看判断。

沿用SeedVR2强度0.30及源频段回补0.65。眼睛、嘴部及非皮肤区域在细节合成的编码前保持，不能扩大成最终有损视频逐像素不变或真实毛孔恢复。原57帧小样脚本、正式父项边界和人工/发布门均保留，151帧分支是固定白名单，不接受任意命令。

## 实测验收

- 六份驱动WAV逐采样等于原干声的镜头时间窗，切点后仅补静音。最终整条AAC包与解码PCM分别逐字节等于原1346十秒版；换轨未改变视频包，AAC包PTS/DTS/时长及priming信息保持，240个视频帧时间戳严格对应i/24。四句对白、音量、原速和时间轴保持，没有重配音。
- 原SRT SHA `{v['subtitleSha256']}`保持，同一文件用于完整十秒单遍字幕合成。240帧和两个切点53/96保持，首末帧及切点前后共10个源帧对应检查通过。另按原SRT独立渲染字幕模板，抽查四句各自首/中/末共12个实际帧的字形核心，见caption-render-checks.json；这是显示存在检查而非OCR或全像素不变保证，并已实际观看四句字幕。
- 三个新原生驱动、四个人物表演、三份canvas/QHD/细节、画面与最终片完整解码和规格检查通过，最终240个解码帧均唯一。
- 双人两份151帧潜在运动轨迹、眼部保护、角色支持区域不重叠和逐帧皮肤保护检查通过。嘴部/能量或几何不是每个音素准确率，本轮不虚构同步、美学或身份评分。
- 真实Comfy成功历史与上传图片/WAV SHA一致；前两个原始输出与已发布驱动文件SHA一致，双人恢复原始副本SHA一致、发布容器的视频包一致（容器SHA不同，明确保留此差别）。执行音频CFG/帧数/步数/双人区域符合冻结请求。证据comfy-executed-history.json和final-verification.json。
- 新151帧、旧57帧、旧表演/短合成实际预检及13个无效POST拒绝通过，未创建额外任务。完整合成有效预检及无效请求拒绝见composition-admission-checks.json。旧表演CPU协议28项通过，这些夹具不是GPU生成质量结果。
- 浏览器完整正常/半速配对播放、声音切换、逐帧和局部查看通过，控制台错误0。实际AX、截图与browser-playback.json保留。
- {e['preservedFileHashesVerified']}份冻结文件SHA保持；模型目录{e['modelMetadataFilesUnchanged']}份文件集合/大小/mtime保持，LP官方源码/8份权重由既有固定哈希预检验证。旧工作流合同逐项保留。
- GPU最大并发1，设备采样显存峰值{e['sampledPeakDeviceVramMiB']}MiB，可用RAM最低{e['sampledMinAvailableRamMiB']}MiB，磁盘最低{e['sampledMinFreeDiskGiB']}GiB。加载时RAM余量低，值为系统采样而非单进程精确峰值，1373监控超时后约两分钟尾段未纳入资源采样；未隐式降分辨率或换模型。仅空闲时释放Comfy缓存，不删模型/历史。
- DB/Comfy/FFmpeg在线，原服务18080保留，独立18081使用新构建且旧构建保留。队列恢复此前状态。完成态重新调用核验/生成不会重复提交。未清理脏工作、提交或推送。

## 恢复与证据

`C:/install/AI/Data/DialogueSyncFull20261025/run.json`已标记ReadyForUserPreview/completed。先核对已登记任务，禁止重复提交；下一轮使用新版本。详细证据见voice-window-checks、api-admission-checks、composition-admission-checks、legacy-protocol-checks、final-verification、execution-summary、browser-playback、completed-guard-checks、source-manifest和final-environment-verification各JSON。
'''
(ROOT/'docs/DIALOGUE_SYNC_FULL_20261025.md').write_text(text,encoding='utf-8');print('Final full-ten-second report written')

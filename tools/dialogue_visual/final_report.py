"""Final human-readable record from actual task and acceptance evidence."""
from run import *
s=read(FOLDER/'run.json')
if not s.get('completed'):raise RuntimeError('Complete actual acceptance first')
summary=read(FOLDER/'execution-summary.json');verified=read(FOLDER/'final-verification.json')
def seconds(field):return round(read(FOLDER/f'task-{s[field]}.json')['task']['durationMs']/1000,1)
rows=[]
for i,frames in [(1,53),(2,43),(3,144)]:rows.append(f'| {i} | {frames}帧 / {frames/24:.3f}秒 | {s[f"qhd{i}TaskId"]} / {seconds(f"qhd{i}TaskId")}秒 | {s[f"detail{i}TaskId"]} / {seconds(f"detail{i}TaskId")}秒 |')
text=f'''# 十秒对话画面升级执行与验收

项目{s['projectId']}，最终任务{s['finalTaskId']}，`ReadyForUserPreview`。技术 **Passed**；内容 `NeedReview`；发布 **Blocked**。用户要求把已认可的画面小样方法应用到此前十秒对话，按约定于2026年10月25日北京时间03:35恢复。本次一次性恢复提醒已核对并移除，未留下重复执行。

新对比页：<http://127.0.0.1:18080/dialogue-visual.html>。最终文件：`C:/install/AI/Data/{s['finalPath']}`，SHA256 `{s['finalSha256']}`。实际2560×1440、24FPS、240个可完整解码且互异的帧、10秒，含原四句对白、原声及原字幕。

## 实际路线与版本选择

没有重新配音、改台词或调用云推理，也没有下载新模型。首镜头明确复用用户认可小样的Klein K05作为参考，重新生成本轮完整表演，不把旧小样直接充当十秒新结果。男方与双人参考新生成；首张双人候选1327把女方眼睛改为低垂闭合，因此未选用，保留后以1328眼睛睁开的修复候选继续。1326/1327在中断后已完成，恢复时没有重复提交。

新增独立 `dialogue-blink-v1`，使用已固定SHA的眼部残差适配器和既有LivePortrait隔离环境；原V1、短样本适配器、官方源码、依赖及权重保留。对话原生段为57/46/151帧、25FPS，转换到53/43/144帧、24FPS；切点仍为53、96帧。对白沿用原生视频的说话/头部动作驱动，眼部只在实际驱动眨眼时修正，不能把闭口H3提示套到整段说话。嘴部为新渲染，不宣称保留旧口型像素或音素准确率。

男方近景初版嘴部幅度偏大，做了一次定向修复：整体动作系数从1.0降到0.7，保留说话时间线和独立眼部修正。初版、旧canvas、修复版均保留。双人镜头分别以明确左右角色提取原驱动，再在不重叠人物支持区域合成；151个原生帧全部验证角色遮罩不重叠，区域外为静态新参考。没有把另一人的表演套到同一张脸。静态背景和不同参考构图属于实际限制，不能称全画面身体运动重生成。

逐镜头SeedVR2强度0.30输出QHD，然后从同帧精修前素材回补已有亮度频段（0.65、增量限幅6级）。单人/双人分别校验1/2张脸；240帧的皮肤掩膜外及眼口保护区在细节合成前后逐像素不变。眼部保护断言发生于解码脸部裁片，后续贴回、重采样与编码独立记录；不扩大成最终视频像素全不变。QHD是后期输出，不能称原生2K、真实毛孔恢复或真人表演。

| 镜头 | 时间轴 | QHD任务/耗时 | 源细节任务/耗时 |
|---|---|---|---|
{chr(10).join(rows)}

发现旧常规拼接会经过多次有损编码，因此本轮扩展独立预览的一次编码导出，让拼接、时长与SRT烧录在同一CRF16画面编码中完成，再无损复制完整原AAC。旧无字幕调用保持原行为，正式Episode审核边界不变。等待全部GPU/CPU任务空闲后才切换18081到独立V2构建；原18080进程与旧构建保留。

## 测试与验收证据

- 原表演协议28项 **Passed**；真实API15个无效POST全部422且任务集合未变，覆盖方向/时长/强度/引擎及清单SHA、人物角色/遮罩对调和帧数错误。真实短于2秒的男方、6.04秒双人及两个人物方向均已实际出片，不仅是预检。
- 新一次编码字幕回归17项 **Passed**：实际UTF8中文SRT可见、未到时间不显示、旧无字幕行为及缺失/非SRT拒绝，并用与本片相同的53/43/144分数帧时长验证240帧/10秒及52/53/95/96切点；全部完整解码。最终V2还做真实字幕API预检及无效输入拒绝，见 `caption-api-checks.json`。
- 9份选用canvas/QHD/细节视频与最终片完整解码、规格与SHA **Passed**；最终240帧互异。原完整AAC数据包与解码PCM分别逐字节一致，容器/音视频时长一致。
- 原53/96切点前后8帧与对应镜头源逐一比对，编码容差内一致；字幕源SHA保留。三张新参考的实际Comfy成功历史已归档，原始PNG与发布PNG SHA一致。
- 实际浏览器正常十秒与半速完整播放，两版均到结尾；新版/上一版/静音声音选择、定位、逐帧和人物局部查看 **Passed**，页面控制台错误0。原始AX与截图保存，不伪造身份或美学分数。
- 完成后再次执行check与act阶段只读核验 **Passed**，任务集合未变、新提交0；见 `completed-guard-checks.json`。
- 旧版与输入{summary['priorVersionHashesVerified']}个文件SHA复核一致；模型目录{summary['modelMetadataFilesUnchanged']}个基线文件大小/mtime不变，未新算全部旧权重完整SHA。未删除旧模型、成片、工作流或重置脏工作。未提交或推送，分支main，原HEAD d6ec38d。
- GPU实际最大并发1。设备显存采样峰值{summary['sampledPeakDeviceVramMiB']}MiB，可用RAM采样最低{summary['sampledMinAvailableRamMiB']}MiB，磁盘最低{summary['sampledMinFreeDiskGiB']}GiB；为系统/设备采样，不是单进程精确峰值或持续稳定性保证。
- 原队列恢复此前状态，实验队列暂停，数据库、Comfy、FFmpeg在线且队列空闲。人脸检测权重沿用既有研究实验边界，未绕过人工/许可/发布门。

画面已按同一组对白时刻、眨眼与切点进行对照。自然度、人物身份细节和细微口型仍需用户观看判断；皮肤回补收益较轻，不能用几何或频带诊断替代审美认可。

## 恢复

`C:/install/AI/Data/DialogueVisual20261025/run.json`为入口。完成后所有运行阶段只读核验，不再生成；新修改开独立版本。证据包括 `final-verification.json`、`execution-summary.json`、各任务与回执、`api-admission-checks.json`、`caption-api-checks.json`、`browser-playback.json`、`source-manifest.json`、`final-environment-verification.json`。
'''
(ROOT/'docs/DIALOGUE_VISUAL_20261025.md').write_text(text,encoding='utf-8')
print('Final dialogue acceptance report written')

"""Additive Chinese recovery notes and compatibility entries, with real evidence."""
from run import *
import shutil
s=read(FOLDER/'run.json');e=read(FOLDER/'execution-summary.json');v=read(FOLDER/'final-verification.json');repeat=read(FOLDER/'repeatability.json')
report=f'''# 稳定768p十秒对白本地验证（2026-10-25）

用户选择先稳定768p成片。项目{s['projectId']}已完成，技术验收 **Passed**，整体表演自然度仍待用户复核（NeedReview），正式发布 **Blocked**。没有覆盖项目40/41/42的成片、模型或旧脚本。工作分支main，原HEAD d6ec38d；既有脏工作保留，本轮没有提交或推送。

本地对比：http://127.0.0.1:18080/dialogue-stable.html 。新版 `{s['finalPath']}`，SHA256 `{s['finalSha256']}`。恢复入口为 `C:/install/AI/Data/DialogueStable20261025/run.json`；已完成入口具有禁止重复提交保护。

## 实际分辨率

| 阶段 | 尺寸 | 含义 |
|---|---|---|
| 已有InfiniteTalk动作驱动 | 832×480，25FPS | 约480p，不是原生2K或原生768p |
| 本轮人物表演 | 1024×576，25FPS | 源参考图贴回，口型与姿态分开控制 |
| 旧版项目42交付 | 2560×1440，24FPS | 后期720p画面再经神经超分与细节处理 |
| 新稳定版交付 | 1366×768，24FPS，240帧，10秒 | 常规Lanczos缩放，跳过神经超分；宽度采用偶数取整 |

## 原因和对应处理

1. 4秒跳切来自两套姿态：新版男方近景采用新的抬头动作，双人镜头采用已认可的旧低头动作，没有统一镜头交界。本轮近景改用已认可1298姿态，双人继续1299姿态，保留项目42原音频驱动的嘴部残差。实际95/96帧均低头看手机，消除了此前明显的抬头到低头跳变。
2. 连眨来自生成驱动的眼部表情随机变化。旧残差方法能补足闭合，但不负责删除多余眨眼。本轮冻结语义眼部关键点差分，分别设置每个人物轨道的一次眨眼时点，沿用有界眼部遮罩与已有学习残差。头部、眉颊仍来自独立批准姿态；口型保留现有音频驱动。
3. 固定seed不足以保证数值重现。实际上游 `LivePortraitPilot/official/src/live_portrait_pipeline.py:8` 显式设置 `torch.backends.cudnn.benchmark = True`。V1两次57帧渲染平均像素差0.723/255，测试阈值0.5未通过，保留 `repeat-v1-failed.json` 与两次成片。V2在导入上游后关闭benchmark、启用确定性算法、禁用TF32，固定NumPy/随机状态和CPU线程数，CuBLAS工作区配置在导入前设置。V2两次57帧解码像素、控制轨迹全部一致，最大像素差0，复测Passed。
4. 身体偏静来自静态参考图驱动面部、遮罩之外保留静态画面的设计。降低输出尺寸不能创造身体表演。此版保持安静对白范围，没有声称修好躯干、手或手机动作。
5. 神经超分会增加耗时和资源占用，也无法替代源表演连续性验收。本轮完全跳过该阶段，保留参考图自身的纹理范围；不宣称恢复了原本不存在的真实毛孔。

## 已执行的测试

- 实际队列任务1391–1406，共{len(e['tasks'])}个，全部Succeeded，GPU实际执行无重叠。V1候选均保留；最终选用V2四个人物轨道。
- 本轮新增扩散任务0、神经超分任务0、模型下载0、云推理0。明确复用项目42已经选定的音频驱动，重新进行本地人物渲染，不将旧驱动称为新生成。
- 全片完整解码、1366×768/24FPS/240帧/10秒、240个不同解码帧、逐帧时间戳通过；第53/96帧切点与对应镜头源一致。
- 最终视频包与字幕画面包一致；整条原声AAC包、解码PCM、PTS/DTS及priming完全一致，没有重新合成或切碎原声。
- 原始SRT SHA保留，四条字幕的首/中/末共12处字形核心检查通过，已查看实际字幕画面。
- V2重复小样57帧×2：像素和控制轨迹逐帧一致。此结果只覆盖当前硬件、冻结输入和此小样，不能外推为任意模型/提示词的保证。
- 新表演分支9个实际非法POST拒绝、3个旧分支CPU预检通过；新合成固定规格、非法phase/帧数/宽度拒绝通过，没有测试任务落库。
- 原人物表演协议回归28项、字幕/切点/换轨几何回归23项Passed；1366×768偶数宽度取整只在明确允许跨分辨率换轨时开放，默认严格匹配不变。
- 实际对比页正常/半速均完整播放10秒；声音三选项、52/53和95/96逐帧、滑块、四种放大方式通过；浏览器console错误0。实际截图 `browser-final.png` 和 `browser-cut95.png` 已保存。
- {e['preservedFileHashesVerified']}个保留文件SHA校验通过，{e['modelMetadataFilesUnchanged']}个模型文件的集合、大小、修改时间未变；人物运行器仍执行既有权重SHA锁。
- 本轮设备显存采样峰值{e['sampledPeakDeviceVramMiB']}MiB，系统可用内存采样最低{e['sampledMinAvailableRamMiB']}MiB。仅代表此复用驱动/人物渲染/CPU交付流程，不能与包含扩散、超分的旧流程等同比较容量。
- 结束后原18080队列恢复未暂停、隔离18081队列恢复暂停；MySQL/ComfyUI/FFmpeg在线，无活跃任务。

## 验收边界和后续方向

技术测试Passed；本次针对开头连眨和4秒切镜方向的样本复核Passed。双人画面躯干、手和手机偏静，女方听话后的笑容仍较固定，细粒度音素同步和完整表演自然度没有自动评分证明，仍需用户观看判断。原声完全一致只证明声轨保留，不证明音素口型准确。

后续提高自然度应另做带身体运动的短片小样，同时锁定镜头末姿态/下镜初姿态，再验证人物分离遮罩和口型；不通过继续加超分或增加随机动作掩盖问题。当前稳定版不自动扩大到原生768p扩散、不更换模型、不触发正式发布。

证据均在 `C:/install/AI/Data/DialogueStable20261025/`：`repeatability.json`、`repeat-v1-failed.json`、`final-verification.json`、`caption-render-checks.json`、`native-review.json`、`final-content-review.json`、`browser-playback.json`、`execution-summary.json`、`final-environment.json`、`source-verification.json` 和 `completed-guard-checks.json`。源检查覆盖Python编译、标准库同名检查、JS语法、部署DLL、配置秘密值扫描与预期文件diff检查；不输出秘密值。
'''
(ROOT/'docs/DIALOGUE_STABLE_768_20261025.md').write_text(report,encoding='utf-8')
start='<!-- dialogue-stable-768-20261025:start -->';end='<!-- dialogue-stable-768-20261025:end -->'
entry=start+'\n> 2026-10-25：项目43稳定768p完整十秒已完成，1366×768/24FPS/240帧，技术Passed；整体表演仍需用户复核，发布Blocked。修复开头连眨和4秒姿态跳变，确定性小样57帧重复像素一致；身体/手/手机偏静仍保留为限制。原声、四句字幕、53/96帧切点、旧版和模型保留。对比http://127.0.0.1:18080/dialogue-stable.html；恢复Data/DialogueStable20261025/run.json，completed=true禁止重复提交。见[执行与验收记录](docs/DIALOGUE_STABLE_768_20261025.md)。\n'+end+'\n\n'
for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
    p=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(p,backup)
    old=p.read_text(encoding='utf-8-sig')
    if start in old:
        a=old.index(start);b=old.index(end,a)+len(end);old=old[:a]+old[b:].lstrip('\r\n')
    block=entry.replace('(docs/DIALOGUE_STABLE_768_20261025.md)','(DIALOGUE_STABLE_768_20261025.md)') if name.startswith('docs/') else entry
    p.write_text(block+old,encoding='utf-8')
print('Passed: Chinese recovery records and compatibility entries updated additively')

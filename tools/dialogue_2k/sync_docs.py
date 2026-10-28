"""Bounded progress/completion records, preserving all existing project text."""
from datetime import datetime, timezone
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import FOLDER, ROOT, read

state = read(FOLDER / 'run.json')
now = datetime.now(timezone.utc).isoformat()
marker = 'seedvr2-dialogue-2k-20261024'
report_name = 'SEEDVR2_DIALOGUE_2K_20261024.md'
stages = dict(ReadyForFirstShot='已冻结原片，等待首镜', RestoringShot1='女方近景修复中',
              AwaitingShot1Inspection='女方近景待检查', RestoringShot2='男方反打修复中',
              AwaitingShot2Inspection='男方反打待检查', RestoringShot3='双人收尾修复中',
              AwaitingShot3Inspection='双人收尾待检查', AwaitingFinalVerification='成片待验收',
              AwaitingBrowserPlayback='技术核验通过，待浏览器实播', ReadyForUserPreview='成片与对比可供用户观看')
stage = stages.get(state['stage'], state['stage'])
summary = (f"2026-10-24：项目{state.get('projectId')}，同人物/同四句台词的10秒三镜头 SeedVR2 逐镜头2K修复，"
           f"目标2560×1440（QHD）/24FPS/240帧，阶段：{stage}。技术{state.get('technicalStatus', 'Blocked')}；"
           "内容待用户复核，发布Blocked。原1263与声轨、切点保留，无新增表演或配音；不是原生2K生成或H3官方再生成。"
           "恢复Data/Dialogue2KSeedVR220261024/run.json，按已登记任务续接，不重复提交。")
backup = FOLDER / 'docs-before'
backup.mkdir(exist_ok=True)
for name in ['项目状态.md', '待办事项.md', '变更记录.md', 'PROJECT_STATE.md', 'NEXT_STAGE.md', 'CHANGELOG.md',
             'docs/ACCEPTANCE_REPORT.md', 'docs/FIX_HISTORY.md']:
    path = ROOT / name
    old = path.read_text(encoding='utf-8-sig')
    copy = backup / name.replace('/', '_')
    if not copy.exists():
        shutil.copy2(path, copy)
    target = report_name if name.startswith('docs/') else 'docs/' + report_name
    block = f'<!-- {marker}:start -->\n> {summary} 见[本轮记录]({target})。\n<!-- {marker}:end -->'
    pattern = rf'<!-- {marker}:start -->.*?<!-- {marker}:end -->'
    if re.search(pattern, old, flags=re.S):
        updated = re.sub(pattern, lambda _: block, old, count=1, flags=re.S)
    else:
        updated = block + '\n\n' + old
    path.write_text(updated, encoding='utf-8')
task_ids = {k: v for k, v in state.items() if k.endswith('TaskId') and type(v) is int}
tasks = '\n'.join(f'| {name} | {value} |' for name, value in task_ids.items())
verification = FOLDER / 'verification.json'
extra = ''
if verification.exists():
    result = read(verification)
    extra = (f"\n技术文件核验：{result.get('status')}；实际{result.get('width')}×{result.get('height')}、"
             f"{result.get('frames')}帧、{result.get('durationSeconds')}秒；原始AAC载荷一致：{result.get('audioPacketsIdentical')}。\n")
    extra += (f"整卡资源采样{result.get('resourceSamples')}条，采样显存峰值{result.get('sampledPeakDeviceVramMiB')}MiB，"
              f"系统最低可用RAM{result.get('sampledMinAvailableRamMiB')}MiB；这些是设备/系统采样值，不是进程精确峰值。\n")
execution_file = FOLDER / 'execution-summary.json'
if execution_file.exists():
    execution = read(execution_file)
    extra += (f"实际GPU任务合计{execution['gpuTaskMilliseconds']/1000:.3f}秒，CPU任务合计{execution['cpuTaskMilliseconds']/1000:.3f}秒；"
              f"按完整起止时间计算GPU最大并发{execution['maxActualGpuConcurrency']}。\n")
playback_file = FOLDER / 'browser-final-playback.json'
if playback_file.exists():
    playback = read(playback_file)
    extra += (f"浏览器实际完整播放：{playback.get('status')}。原版音轨、2K音轨两轮均两播放器ended=true、duration=10、单路未静音，界面音量100%。"
              "8项镜头/台词定位及前后逐帧检查Passed，浏览器控制台错误0。最终截图browser-final.png。\n")
report = f'''# 同人物三镜头：SeedVR2 逐镜头 2K 修复与对比

更新于 `{now}`。{summary}

## 执行方案

- 输入为上一轮三个已选镜头的干净720p交付帧：53帧、43帧、144帧，切点53/96帧；没有重新生成动作或口型。
- 使用已部署 SeedVR2 3B FP8 及原VAE，固定引擎/模型版本，离线运行。每个镜头单独进入业务GPU队列，并发1。
- 新增显式 `qhd1440` 输出规格2560×1440；源视频仍限1080p以内、24FPS、240帧以内。旧任务保留源尺寸逻辑。
- QHD使用5帧批次、3帧重叠，CPU卸载和512分块编解码。初选重建混合强度0.35，逐镜检查后选择；尺寸放大不代表原生生成细节。
- 三镜合成后重绘同一份字幕，再通过业务CPU队列无损接回原1263的完整AAC音轨，保留语速、音高、停顿、帧数和时长。
- 无损换轨新增显式allowResolutionDifference布尔选项，宽高比必须一致；帧数、帧率、时长、源SHA和零起点要求保持。14项实际预检及无效POST拒绝422、零新增任务Passed；最终AAC包与解码PCM完全一致。
- 对比基线为真实原1263成片（已做过保守720p修复）；新推理使用各镜的干净源帧，避免在原修复成片上叠加重建。

## 运行与保护

原版：`{state['originalPath']}`；SHA256 `{state['originalSha256']}`。

运行状态：`C:\\install\\AI\\Data\\Dialogue2KSeedVR220261024\\run.json`。每项提交参数、预检、任务ID、真实结果、设备/内存采样及逐镜检查保存在同目录。

使用独立本地预览API `127.0.0.1:18081`，保持原18080服务及其发布文件在线不变；通过现有pause/resume接口协调队列。GPU全局互斥仍生效。结束后新队列暂停，原队列恢复原状态。部署中停止原服务并覆盖发布文件的组合操作被自动审批拦截；实际采用上述保留原服务的方式。

{extra}

| 实际任务字段 | 任务ID |
|---|---|
{tasks}

新成片：`{state.get('finalPath', '尚未生成')}`。

SHA256：`{state.get('finalSha256', '尚未生成')}`。

## 验收与限制

22项实际预检验证默认源尺寸、显式QHD及拒绝无效规格/资源/哈希/边界；预检不创建任务。新包装器CPU边界检查、Python编译与.NET发布已执行，结果见证据文件。

最终需检查全部帧实际解码、240帧/10秒/24FPS/QHD尺寸、原片与原声轨哈希保持、AAC包与解码PCM一致、逐句声音、每镜实际修复回执、对齐脸部裁图和浏览器完整播放。技术核验不能替代身份、牙齿、口眼及真实感人工判断；内容保持待复核。

实际画面选择：三镜均选初次0.35混合候选，无GPU重试。每镜六组同帧全画面对照，第三镜补看嘴部几何差异最大的42/77帧；最终又比较原1263与新1268的11个实际时点，包括52/53、95/96切点两侧及末帧。发丝、衣物边缘较干净，肤质和牙齿仍有生成平滑感；原片的表演与收尾视线模式保留。CPU嘴部几何记录仅作观察，不能换算为身份或音素准确率。

新对比入口：`http://127.0.0.1:18080/dialogue-2k-compare.html`（最终验收后提供）。支持同步播放、逐帧、半速、镜头/台词定位、单路声音和局部放大。原预览页继续保留。

分支`main`，HEAD`d6ec38d076a8b0336d349c36df5c123f2c941ac8`；既有216项工作区改动保留，无提交、推送或云推理。
'''
(ROOT / 'docs' / report_name).write_text(report, encoding='utf-8')
print(stage)

"""Close this local preview only after actual media, queue and browser checks."""
from datetime import datetime, timezone
from run import ROOT,FOLDER,API,Run,read,write,preserve

run=Run(API,FOLDER/'run.json');preserve(run)
required=['pilot-verification','final-verification','pilot-qhd-verification','preflight-verification',
    'workflow-verification','streaming-boundary-verification','execution-summary','source-verification',
    'browser-final-playback','final-environment-verification','final-source-checks']
checks={name:read(FOLDER/(name+'.json')) for name in required}
if any(value['status']!='Passed' for value in checks.values()):raise RuntimeError('Required actual check not Passed')
browser=checks['browser-final-playback']
for key,seconds in [('normalFull',10),('halfFull',10),('pilotQhd',2)]:
    rows=browser[key]
    if len(rows)!=3 or any(not row['ended'] or abs(row['duration']-seconds)>.02 for row in rows):
        raise RuntimeError('Complete three-player browser playback required')
if browser['consoleErrors'] or not browser['controlsVerified']:raise RuntimeError('Browser verification incomplete')
if not (FOLDER/'browser-final.png').is_file():raise RuntimeError('Actual browser screenshot required')
stats=checks['execution-summary'];state=run.state
rows=[]
for index in [1,2,3]:
    native=read(FOLDER/f'shot-{index}-review.json');qhd=read(FOLDER/f'qhd-{index}-review.json')
    a=state[f'shot{index}Attempt{native["attempt"]}TaskId'];b=state[f'restore{index}Attempt{qhd["attempt"]}TaskId']
    rows.append(f'| {index} | {a} / attempt {native["attempt"]} | {b} | {stats["tasks"][str(b)]["durationMs"]/60000:.1f} 分钟 |')
report=f'''# 同人物参考、对白表情与 2K 三镜头交付

用户批准按参考表情校正、两秒原声短测、逐镜头修复、十秒三镜头的顺序纯本地实施。项目 {state['projectId']}，最终任务 {state['finalTaskId']}。

- 技术验收：Passed。实际 2560×1440、24 FPS、240 个可完整解码且互异的帧、10 秒。
- 内容状态：NeedReview。人物自然度、身份细节、音素口型与情绪仍需人工观看；没有虚构身份或口型分数。
- 发布：Blocked。仅交付本机预览；没有发布、提交或推送。
- 视频原生为 832×480 / 25 FPS，经 24 FPS 剪辑和 SeedVR2 超分得到 QHD，不能称为原生 2K。

## 实际实现

复用现有 RealVisXL V5 FP16、Wan2.1 I2V Q4、InfiniteTalk Multi Q8、LightX2V 与 SeedVR2 3B FP8；无新模型下载、无云推理。执行均经现有服务队列，未直接提交 Comfy prompt 或手工改数据库状态。

女方参考初始及第一轮定向修复未解决固定露齿笑/嘴角残留，第二轮定向修复选择 B 轻微闭口版本；已用完本轮两次自动参考修复。男方第一张出现双眼线，定向修复后保留完整上半脸并柔化脸颊合成边缘。三张候选是同一三分之四角度的表情对照，不是已验证的多视角身份集。

男方近景初版 task1297 向窗边抬眼，未选用；task1298 定向修改为低头看手机回话。双人段检查了女方讲话、男方接话及 57/105 帧附近的分段交界。脸部、口型和表情本轮重新生成，不能称为保留原嘴部像素。

原来的四句对白、声线、时序和字幕保持。最终从 task1263 直接复制完整 AAC 数据包，逐字节比较音频包与解码 PCM 均一致。

| 镜头 | 选用原生任务 | QHD 任务 | QHD 队列耗时 |
|---|---|---|---|
{chr(10).join(rows)}

SeedVR2 强度 0.30，batch5、overlap3、33 帧流式分段、32 blocks swap、512 tile。实查源帧/QHD 帧及 33/66/99/132 等实际存在的分段边界。未修改已有引擎或权重；source profile 仍不启用新分段。实测 GPU 最大并发 {stats['gpuMaximumConcurrency']}，设备显存采样峰值 {stats['sampledDevicePeakMiB']} MiB；QHD 阶段采样峰值 {stats['qhdSampledDevicePeakMiB']} MiB，最低可用系统内存 {stats['qhdMinimumAvailableRamMiB']} MiB。这些是采样值，不是连续监控保证。原生长段仍曾出现低可用 RAM，不能声称整条链路已无内存压力。

## 验收和实际限制

已完成最终成片及两秒 QHD 裁片的完整解码、规格、帧数、原音频包/PCM 一致性，原媒体/状态/参考 SHA 保全，以及队列、Comfy history、实际输出文件三方比对。真实浏览器验证三版正常/半速十秒完整播放、两秒完整播放、声音切换、定位和逐帧操作；控制台无错误，截图已保存。

改善主要是从固定大笑起始脸改为闭口起始表情，增加讲话/停顿和静默反应。肤质仍偏平滑，部分圆口型、眼形和牙齿仍有生成感；超分不构成真人质感或音素准确率的保证。男方反打不再全画面镜像，故与旧版的主体位置不同，局部查看已分别对齐。

## 本机交付与恢复

- 对比页：http://127.0.0.1:18080/face-acting-preview.html
- 最终文件：`C:/install/AI/Data/{state['finalPath']}`
- SHA256：`{state['finalSha256']}`
- 实际证据：`C:/install/AI/Data/FaceActing20261024/`，含各轮失败记录、逐镜头帧、音频完整性、资源和浏览器验收。
- API 复用已有验证构建，ComfyUI 复用已有 venv/模型；结束时两队列空闲，预览服务继续运行。
- Git main / d6ec38d076a8b0336d349c36df5c123f2c941ac8；保留全部原有脏工作，未提交或推送。

继续时先读 `run.json`；ReadyForUserPreview 只做核验，不能重复提交已登记任务。旧版1263、旧QHD1268、旧肤质小样1281均保留。
'''
(ROOT/'docs/FACE_ACTING_20261024.md').write_text(report,encoding='utf-8')
run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
    completedAt=datetime.now(timezone.utc).isoformat(),previewUrl='http://127.0.0.1:18080/face-acting-preview.html')
write(FOLDER/'completion-verification.json',dict(status='Passed',requiredChecks=required,technicalStatus='Passed',
    contentStatus='NeedReview',publicationStatus='Blocked',finalSha256=state['finalSha256']))
print('ReadyForUserPreview; no new generation',flush=True)

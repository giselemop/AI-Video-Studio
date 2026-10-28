"""Publish local preview metadata; mark ready only after real playback evidence."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
from bootstrap import ASSETS
from run import Pilot,FOLDER,DATA,ROOT,sha
from sync_docs import update

def verified(run):
    report=json.loads((FOLDER/'delivery-verification.json').read_text(encoding='utf-8'))
    if report.get('status')!='Passed' or report['finalSha256']!=sha(DATA/run.state['finalPath']):raise RuntimeError('Real delivery verification is required')
    return report

def preview(run):
    verified(run)
    poster=FOLDER/'final-poster.jpg'
    subprocess.run([r'C:\install\FFmpeg\bin\ffmpeg.exe','-v','error','-y','-i',str(DATA/run.state['finalPath']),'-frames:v','1',str(poster)],check=True)
    old=json.loads((DATA/'DouyinReference20261023/run.json').read_text(encoding='utf-8'))
    labels=['含笑打趣','佯装不服','温柔让步','轻松满意']
    manifest=dict(finalPath=run.state['finalPath'],posterPath=poster.relative_to(DATA).as_posix(),previousPath=old['finalVideoPath'],lines=[dict(role=x['role'],text=x['text'],startSeconds=x['startSeconds'],emotionLabel=labels[i]) for i,x in enumerate(run.state['timeline'])],note='四句对白均保持原速，字幕标明说话人；两人轮流说话，保留倾听与反应。')
    path=ROOT/'web/public/dialogue-pilot-preview.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for file in ['dialogue-pilot-preview.html','dialogue-pilot-preview.json']:shutil.copy2(ROOT/'web/public'/file,ROOT/'web/dist'/file)
    print('Local preview ready: http://127.0.0.1:18080/dialogue-pilot-preview.html',flush=True)

def complete(run):
    report=verified(run)
    playback=json.loads((FOLDER/'browser-final-playback.json').read_text(encoding='utf-8'))
    if playback.get('status')!='Passed' or not playback.get('ended') or playback.get('muted') is not False or playback.get('volumePercent')!=100:raise RuntimeError('Actual complete unmuted browser playback is required')
    fields=['line1TaskId','line2TaskId','line3TaskId','line4TaskId','video125TaskId','testTrimTaskId','video241TaskId','canvasTaskId','restoreTaskId','finalTaskId']
    tasks=[]
    for field in fields:
        d=run.api(f'/api/tasks/{run.state[field]}')['task']
        expected='Failed' if field=='video125TaskId' else 'Succeeded'
        if d['status']!=expected:raise RuntimeError('Unexpected task status: '+field)
        tasks.append(dict(field=field,**d))
    samples=[json.loads(x) for x in (FOLDER/'resources.jsonl').read_text().splitlines() if x]
    ids={t['id'] for t in tasks};samples=[x for x in samples if x['taskId'] in ids]
    events=[]
    for t in tasks:
        if t['resourceClass']=='GPU':events.extend([(datetime.fromisoformat(t['startedAt']),1),(datetime.fromisoformat(t['finishedAt']),-1)])
    active=peak=0
    for _,change in sorted(events):active+=change;peak=max(peak,active)
    if peak!=1:raise RuntimeError('GPU task overlap detected')
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,encoding='utf-8').strip()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip()
    summary=dict(status='Passed',scope='Corrected final delivery; failed prototype remains Failed',branch=branch,head=head,projectId=run.state['projectId'],finalTaskId=run.state['finalTaskId'],finalPath=run.state['finalPath'],finalSha256=run.state['finalSha256'],output=report,modelDownloadBytes=sum(a[4] for a in ASSETS),maxConcurrentGpuTasks=peak,gpuDurationMs=sum(t.get('durationMs') or 0 for t in tasks if t['resourceClass']=='GPU'),cpuDurationMs=sum(t.get('durationMs') or 0 for t in tasks if t['resourceClass']=='CPU'),sampledPeakDeviceMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),sampledMinimumAvailableRamMiB=min(x['availableRamMiB'] for x in samples),resourceSamples=len(samples),tasks=tasks,contentStatus='NeedReview',publicationStatus='Blocked')
    (FOLDER/'execution-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',previewUrl='http://127.0.0.1:18080/dialogue-pilot-preview.html')
    text=f'2026-10-23交付：项目33双人对白样片，最终任务{run.state["finalTaskId"]}实际1280×720/24FPS/228帧/9.5秒，全程本地Qwen分角色/逐句情绪、InfiniteTalk双音轨及人物区域驱动、细节处理和混音字幕。四句完整原速对白、解码/音轨/真实浏览器完整播放Passed；内容待用户复核、发布Blocked。初次短测1241帧数Failed保留，CPU1242精确裁取；v2保存前裁帧已修复。恢复Data/DialoguePilot20261023/run.json为ReadyForUserPreview，只核验、不重提。'
    (FOLDER/'progress-summary.txt').write_text(text,encoding='utf-8');update(text)
    detail=ROOT/'docs/DIALOGUE_PILOT_20261023.md'
    table='\n'.join(f'| {t["id"]} | {t["field"]} | {t["status"]} | {(t.get("durationMs") or 0)/1000:.3f} |' for t in tasks)
    block=f'''<!-- pilot-delivery:start -->
## 实际最终交付

- 文件：`{DATA/run.state['finalPath']}`
- SHA256：`{run.state['finalSha256']}`
- 实测1280×720、24FPS、228帧、9.5秒，四句台词均完整原速；末句8.78秒结束，仅去掉0.14秒静音尾部。
- 技术验收Passed：全片解码、逐句及完整音轨相关性、实际浏览器从头到尾未静音播放；旧1236/参考片/旧run哈希保持。
- GPU任务按实际起止记录最大并发{peak}；GPU合计{summary['gpuDurationMs']/1000:.3f}秒，含保留的初次失败短测。约5秒采样整卡峰值{summary['sampledPeakDeviceMiB']}MiB、最低可用RAM{summary['sampledMinimumAvailableRamMiB']}MiB。
- 混音按句平衡音量，第三句保留较轻语气；添加极低电平本地生成室内底噪和轻微早期反射，不改变对白时机和语速。
- 声画精细效果保留人工复核，内容NeedReview、发布Blocked；不把路由或地标数值当成音素准确率。
- 分支{branch}，HEAD {head}，未提交/推送；既有脏改动保留。

| 任务 | 阶段 | 实际状态 | 秒 |
| --- | --- | --- | --- |
{table}

恢复使用`tools/dialogue_pilot/run.py --stage check`；Ready状态只读核验现有路径与SHA，不生成新任务。原生测试1241保持Failed；实际5秒结果来自CPU裁切1242，其余本轮成功任务分别可追溯。
<!-- pilot-delivery:end -->'''
    original=detail.read_text(encoding='utf-8')
    if '<!-- pilot-delivery:start -->' in original:
        a=original.index('<!-- pilot-delivery:start -->');b=original.index('<!-- pilot-delivery:end -->',a)+len('<!-- pilot-delivery:end -->');original=original[:a]+block+original[b:]
    else:original+='\n\n'+block+'\n'
    detail.write_text(original,encoding='utf-8')
    print('Final pilot ready for user preview',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['preview','complete'],required=True);args=parser.parse_args()
    run=Pilot('http://127.0.0.1:18080',FOLDER/'run.json');run.access()
    (preview if args.stage=='preview' else complete)(run)

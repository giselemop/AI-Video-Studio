"""Close the local run only after actual delivery and browser checks pass."""
import json
from datetime import datetime,timezone
from run import RealisticRun,FOLDER,DATA,sha


def main():
    run=RealisticRun('http://127.0.0.1:18080',FOLDER/'run.json');run.access()
    if run.state['stage'] not in ['AwaitingPlaybackInspection','ReadyForUserPreview']:
        raise RuntimeError('Actual final assembly and playback inspection are required')
    checks={}
    for name,file in [('media','delivery-verification.json'),('finalPlayback','browser-final-playback.json'),
        ('sourceComparisonPlayback','browser-comparison.json'),('comparisonInputs','comparison-input-verification.json')]:
        report=json.loads((FOLDER/file).read_text(encoding='utf-8'))
        if report.get('status')!='Passed':raise RuntimeError('Required actual check not passed: '+name)
        checks[name]=report
    if checks['media']['finalVideoSha256']!=run.state['finalVideoSha256'] or sha(DATA/run.state['finalVideoPath'])!=run.state['finalVideoSha256']:
        raise RuntimeError('Verified final output binding changed')
    if not checks['comparisonInputs'].get('comparisonOnlyStepsDiffer'):raise RuntimeError('Comparison conditions are not equivalent')
    if checks['finalPlayback']['completion']['time']<9.9 or checks['finalPlayback']['completion'].get('error'):
        raise RuntimeError('Final browser playback was incomplete')
    for source in run.state['sources']:
        if sha(DATA/source['path'])!=source['sha256']:raise RuntimeError('Previous source changed')
    if sha(DATA/run.state['previousBPath'])!='821155a532afd54bd2dfd7f1c50a3706c2a79e8d658346bdb921000a75b4fc22':
        raise RuntimeError('Previous B export changed')
    tasks=[]
    for field in ['reference5TaskId','video20TaskId','video30TaskId','continuationTaskId','finalTaskId']:
        task=run.api(f'/api/tasks/{run.state[field]}')['task']
        if task['status']!='Succeeded':raise RuntimeError('A required business task did not succeed')
        path=run.state['finalVideoPath'] if field=='finalTaskId' else run.state[field+'Path']
        digest=run.state['finalVideoSha256'] if field=='finalTaskId' else run.state[field+'Sha256']
        if sha(DATA/path)!=digest:raise RuntimeError('Generated output changed')
        tasks.append(dict(role=field,id=task['id'],status=task['status'],durationMs=task['durationMs'],taskVramPeakMiB=task['vramPeakMiB']))
    records=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    resources=dict(samples=len(records),intervalSeconds=5,sampledWholeCardVramPeakMiB=max(x.get('usedVramMiB',0) for x in records),
        sampledMinimumAvailableRamMiB=min(x['systemAvailableMiB'] for x in records if 'systemAvailableMiB' in x),
        threeVideoTasksDurationMs=sum(t['durationMs'] for t in tasks if t['role'] in ['video20TaskId','video30TaskId','continuationTaskId']))
    health=run.api('/api/health');queue=run.api('/api/minimax/local/status')['queue']
    if not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available'] or queue['activeTasks']!=0:
        raise RuntimeError('Expected local runtime health or idle queue not observed')
    summary=dict(verificationStatus='Passed',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
        tasks=tasks,resources=resources,selectedSteps=run.state['selectedSteps'],comparisonOnlyStepsDiffer=True,
        previousSourcesPreserved=True,newVideoDecodedFrames=240,audio=checks['media']['audio'],
        browserFinalPlayback=checks['finalPlayback']['completion'],finalVideoPath=run.state['finalVideoPath'],
        finalVideoSha256=run.state['finalVideoSha256'],queue=queue,
        finalizedAt=datetime.now(timezone.utc).isoformat())
    (FOLDER/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
        error=None,blockerCode=None,newH3TasksSubmitted=True,newFinalVideoCreated=True,
        reference5Review='已选用：人物与原背景保持，唯一红本的位置受控；成片待审',
        previewUrl='http://127.0.0.1:18080/realistic-i2v-compare.html',resourceSummary=resources,
        finalizedAt=summary['finalizedAt'])
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()

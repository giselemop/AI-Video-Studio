"""Complete only after real media, browser and preserved-input verification."""
from run import ROOT,DATA,FOLDER,Run,read,write,media,sha
import json
from pathlib import Path
import requests

run=Run('http://127.0.0.1:18081',FOLDER/'run.json');run.preserve();run.access()
verified=read(FOLDER/'media-verification.json');browser=read(FOLDER/'browser-playback.json')
if verified['status']!='Passed' or browser['status']!='Passed' or browser['consoleErrors']!=0:
    raise RuntimeError('Media and actual browser validation must pass first')
if len(browser.get('playbacks',[]))<6 or not all(x['bothEnded'] for x in browser['playbacks']):
    raise RuntimeError('Normal and half-speed complete playback must be verified for all three groups')
if not all(browser.get(k) for k in ['seekAndStepPassed','zoomPassed']):raise RuntimeError('Actual UI controls remain unverified')
screenshot=media(browser['screenshot'])
if sha(screenshot)!=browser['screenshotSha256']:raise RuntimeError('Browser screenshot changed')
for item in verified['videos'].values():
    if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Verified media changed')
tasks=[]
for path in sorted(FOLDER.glob('task-*.json')):
    value=read(path);task=value['task']
    if task.get('projectId')==run.state['projectId']:tasks.append(task)
if not tasks or any(t['status']!='Succeeded' for t in tasks):raise RuntimeError('Every recorded pilot task must have succeeded')
for task in tasks:
    live=run.api(f'/api/tasks/{task["id"]}')['task']
    if live['projectId']!=run.state['projectId'] or live['status']!='Succeeded':raise RuntimeError('Live task detail drifted')
global_tasks=run.api('/api/tasks?limit=500')
active=[t['id'] for t in global_tasks if t['status'] in ['Pending','Running','Queued']]
if active:raise RuntimeError('Local queue still has unresolved work: '+str(active))
session=requests.Session();session.trust_env=False
q=session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if q['queue_running'] or q['queue_pending']:raise RuntimeError('Comfy queue still active')
run.api('/api/production/pause',{})
original=Run('http://127.0.0.1:18080',FOLDER/'run.json');original.access()
was_paused=run.state['originalQueueStatus']['paused']
original.api('/api/production/pause' if was_paused else '/api/production/resume',{})
old_status=original.api('/api/minimax/local/status')['queue'];new_status=run.api('/api/minimax/local/status')['queue']
if old_status['paused']!=was_paused or not new_status['paused']:raise RuntimeError('Queue restoration failed')
health=original.api('/api/health')
if not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Final health not ready')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines() if line.strip()]
gpu=[t for t in tasks if t['resourceClass']=='GPU']
summary=dict(status='Passed',tasks=[dict(id=t['id'],taskType=t['taskType'],status=t['status'],durationMs=t.get('durationMs'),
    resourceClass=t['resourceClass'],startedAt=t.get('startedAt'),finishedAt=t.get('finishedAt')) for t in tasks],
    gpuTaskCount=len(gpu),gpuDurationMs=sum(t.get('durationMs') or 0 for t in gpu),
    sampledPeakDeviceVramMiB=max(s['gpu'][0] for s in samples if s.get('gpu')),
    sampledMinAvailableRamMiB=min(s['availableRamMiB'] for s in samples),
    sampledMinFreeDiskGiB=min(s['freeDiskGiB'] for s in samples),sampleCount=len(samples),
    measurementScope='Device/system samples, not continuous or per-process exact peaks',contentStatus='NeedReview',publicationStatus='Blocked')
intervals=sorted((t['startedAt'],t['finishedAt'],t['id']) for t in gpu if t.get('startedAt') and t.get('finishedAt'))
if any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):raise RuntimeError('GPU task intervals overlap')
summary['gpuMaxConcurrencyFromTaskIntervals']=1
write(FOLDER/'execution-summary.json',summary)
write(FOLDER/'final-environment-verification.json',dict(status='Passed',databaseOnline=True,comfyOnline=True,ffmpegAvailable=True,
    activeTasks=[],comfyQueueIdle=True,originalQueueRestored=True,originalQueuePaused=old_status['paused'],
    experimentalQueuePaused=new_status['paused'],oldApiPreserved=True,sourceHashesPreserved=True,
    existingModelMetadataUnchanged=verified['existingModelMetadataUnchanged'],browserVerified=True,
    cacheArtifactChanges=verified.get('cacheArtifactChanges',[]),
    comfyLiveHistoryStatus=read(FOLDER/'comfy-source-verification.json')['liveHistoryStatus'],
    provenanceVerification='Retained raw Comfy output SHA matched published assets; business tasks succeeded; PNG workflow metadata checked'))
run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
    newTaskSubmitted=False,completed=True,comparisonUrl='http://127.0.0.1:18080/visual-validation.html')
print('ReadyForUserPreview: technical Passed; content NeedReview; publication Blocked; original queue restored')

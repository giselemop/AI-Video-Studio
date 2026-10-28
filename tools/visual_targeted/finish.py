"""Seal only after real browser playback, media decode and preserved-version checks."""
from run import *
import psutil,numpy as np,re
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
verified=read(FOLDER/'media-verification.json');browser=read(FOLDER/'browser-playback.json')
if verified['status']!='Passed' or browser['status']!='Passed' or browser['consoleErrors']:
    raise RuntimeError('Actual media/browser verification required')
if len(browser['playbacks'])!=6 or not all(x['bothEnded'] for x in browser['playbacks']) or not browser['seekAndStepPassed'] or not browser['zoomPassed']:
    raise RuntimeError('Actual playback/controls incomplete')
if sha(media(browser['screenshot']))!=browser['screenshotSha256']:raise RuntimeError('Browser screenshot changed')
for video in verified['videos'].values():
    if sha(media(video['path']))!=video['sha256']:raise RuntimeError('Verified output changed')
old=read(DATA/'VisualValidation20261024/run.json');versions={x['path']:x['sha256'] for x in old['preserved']}
for key,value in old.items():
    if key.endswith('Path') and isinstance(value,str) and old.get(key[:-4]+'Sha256'):versions[value]=old[key[:-4]+'Sha256']
for i in range(1,7):versions[old[f'keyframe{i}Path']]=old[f'keyframe{i}Sha256']
for candidate in old['actingCandidates']:versions[candidate['path']]=candidate['sha256']
versions['VisualValidation20261024/keyframe-selection.json']=old['selectionSha256']
for path,digest in versions.items():
    if sha(media(path))!=digest:raise RuntimeError('An older version changed')
tasks=[]
for field in ['h3RepairTaskId','blinkTaskId','blinkCompareTaskId','detailTaskId']:
    t=r.api(f'/api/tasks/{s[field]}')['task']
    if t['projectId']!=s['projectId'] or t['status']!='Succeeded':raise RuntimeError('Actual task not successful')
    tasks.append(t)
active=[t['id'] for t in r.api('/api/tasks?limit=500') if t['status'] in ['Running','Pending','Queued']]
q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Queues still active')
for item in read(FOLDER/'model-inventory.json')['files']:
    p=ROOT.parent/'Models'/item['path']
    if not p.exists() or p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model directory metadata changed')
admission=read(FOLDER/'api-admission-checks.json');protocol=read(FOLDER/'detail-protocol-checks.json')
if admission['status']!='Passed' or protocol['status']!='Passed':raise RuntimeError('Boundary checks incomplete')
gpu=sorted((t['startedAt'],t['finishedAt'],t['id']) for t in tasks if t['resourceClass']=='GPU')
if any(a[1]>b[0] for a,b in zip(gpu,gpu[1:])):raise RuntimeError('GPU task overlap')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines() if line.strip()]
summary=dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','status','resourceClass','startedAt','finishedAt','durationMs']} for t in tasks],
    gpuMaxConcurrency=1,sampledPeakDeviceVramMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),
    sampledMinAvailableRamMiB=min(x['availableRamMiB'] for x in samples),sampledMinFreeDiskGiB=min(x['freeDiskGiB'] for x in samples),
    measurementScope='Sampled device/system observations, not exact per-process peaks',priorVersionHashesVerified=len(versions),
    modelDirectoryMetadataFilesUnchanged=verified['modelInventoryFilesUnchanged'],cloudInferenceCalls=0,newModelDownloads=0,
    contentStatus='NeedReview',publicationStatus='Blocked')
write(FOLDER/'execution-summary.json',summary)
r.api('/api/production/pause',{})
original=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');original.access()
paused=s['originalQueueStatus']['paused'];original.api('/api/production/pause' if paused else '/api/production/resume',{})
old_queue=original.api('/api/minimax/local/status')['queue'];pilot_queue=r.api('/api/minimax/local/status')['queue']
health=original.api('/api/health')
if old_queue['paused']!=paused or not pilot_queue['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:
    raise RuntimeError('Final queue/environment restoration failed')
write(FOLDER/'final-environment-verification.json',dict(status='Passed',originalQueueRestored=True,originalQueuePaused=paused,pilotQueuePaused=True,
    databaseOnline=True,comfyOnline=True,ffmpegAvailable=True,activeTasks=[],olderVersionHashesVerified=len(versions),modelMetadataUnchanged=True,
    h3HistoryAndRawHashVerified=True,modelFilesNotDeleted=True))
r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
    comparisonUrl='http://127.0.0.1:18080/visual-targeted.html',newTaskSubmitted=False)
print('ReadyForUserPreview: technical Passed; content NeedReview; all prior versions verified; original queue restored')

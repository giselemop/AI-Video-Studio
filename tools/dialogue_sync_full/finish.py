"""Seal the real full-ten-second result after actual browser playback; restore queues."""
from run import *
from datetime import datetime,timezone,timedelta
r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
if r.state.get('completed'):r.preserve();print('Preserved; no new tasks');sys.exit(0)
r.access();r.preserve();s=r.state
verified=read(FOLDER/'final-verification.json');browser=read(FOLDER/'browser-playback.json')
for name in ['api-admission-checks.json','composition-admission-checks.json','voice-window-checks.json','caption-render-checks.json','legacy-protocol-checks.json','driver-recovery.json','deadline-regression.json','qhd-memory-gate.json']:
    if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Acceptance missing: '+name)
if verified['status']!='Passed' or browser['status']!='Passed' or browser['consoleErrors']:raise RuntimeError('Media/browser acceptance incomplete')
if not {1,.5}.issubset({p['speed'] for p in browser['playbacks'] if p['bothEnded']}):raise RuntimeError('Complete normal and half-speed paired playback required')
if not all(browser.get(k) for k in ['audioSelectionsPassed','seekAndStepPassed','zoomPassed']):raise RuntimeError('Actual comparison controls incomplete')
if sha(media(browser['screenshot']))!=browser['screenshotSha256'] or sha(media(s['finalPath']))!=verified['videos']['final']['sha256']:raise RuntimeError('Final visual evidence changed')
tasks=[]
recovery=read(FOLDER/'driver-recovery.json') if s.get('driver3Recovered') else None
for file in sorted(FOLDER.glob('task-*.json')):
    t=read(file)['task'];live=r.api('/api/tasks/'+str(t['id']))['task']
    resolved_timeout=recovery and recovery['status']=='Passed' and live['id']==recovery['failedTaskId'] and live['status']=='Failed' and live['errorType']=='TASK_TIMEOUT'
    if (live['status']!='Succeeded' and not resolved_timeout) or live['projectId']!=s['projectId']:raise RuntimeError('Recorded actual task incomplete or unresolved failure')
    tasks.append(live)
gpu=sorted((x['startedAt'],x['finishedAt'],x['id']) for x in tasks if x['resourceClass']=='GPU')
if any(a[1]>b[0] for a,b in zip(gpu,gpu[1:])):raise RuntimeError('GPU execution overlapped')
if recovery:
    subsequent=[t for t in tasks if t['resourceClass']=='GPU' and t['id']>recovery['failedTaskId']]
    if not any(t['id']==recovery['recoveryTaskId'] and t['status']=='Succeeded' for t in tasks) or not recovery['comfyIdleBeforeRecovery'] or any(datetime.fromisoformat(t['startedAt']).replace(tzinfo=timezone(timedelta(hours=8))).timestamp()*1000 < recovery['actualComfyEndEpochMs'] for t in subsequent):raise RuntimeError('Late Comfy completion overlapped subsequent GPU work')
active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Keep active work; cannot finalize yet')
inventory=read(FOLDER/'model-inventory.json')['files']
for item in inventory:
    p=ROOT.parent/'Models'/item['path']
    if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Existing model metadata changed')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines() if line.strip()]
write(FOLDER/'execution-summary.json',dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','resourceClass','status','durationMs','startedAt','finishedAt']} for t in tasks],resolvedWatcherTimeouts=[dict(failedTaskId=recovery['failedTaskId'],originalStatus='Failed',comfyStatus='success',recoveryTaskId=recovery['recoveryTaskId'],newGpuSubmissions=0)] if recovery else [],gpuMaxConcurrency=1,sampledPeakDeviceVramMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),sampledMinAvailableRamMiB=min(x['availableRamMiB'] for x in samples),sampledMinFreeDiskGiB=min(x['freeDiskGiB'] for x in samples),measurementScope='System/device samples; not exact process peaks or continuous health guarantee. Watcher-timeout tail before recovered Comfy success was not resource-sampled; its completion/idle barrier was checked before subsequent GPU tasks.',preservedFileHashesVerified=len(s['preserved']),modelMetadataFilesUnchanged=len(inventory),newModelDownloads=0,cloudInferenceCalls=0,originalWholeAudioPacketsEqual=True,originalWholeAudioPcmEqual=True,contentStatus='NeedReview',publicationStatus='Blocked'))
old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
for api,paused in [(r,s['pilotQueueStatus']['paused']),(old,s['originalQueueStatus']['paused'])]:api.api('/api/production/pause' if paused else '/api/production/resume',{})
health=old.api('/api/health');a=old.api('/api/minimax/local/status')['queue']['paused'];b=r.api('/api/minimax/local/status')['queue']['paused']
if a!=s['originalQueueStatus']['paused'] or b!=s['pilotQueueStatus']['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Final environment not restored')
write(FOLDER/'final-environment-verification.json',dict(status='Passed',originalQueuePaused=a,pilotQueuePaused=b,originalQueueRestored=True,pilotQueueRestored=True,databaseOnline=True,comfyOnline=True,ffmpegAvailable=True,activeTasks=[],comfyIdle=True))
r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',previewUrl='http://127.0.0.1:18080/dialogue-sync-full.html')
print('Passed: complete ten-second local version sealed; original queues and prior media preserved')

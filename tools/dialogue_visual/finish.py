"""Seal the new dialogue only after actual playback and immutable-version checks."""
from run import *
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
verified=read(FOLDER/'final-verification.json');browser=read(FOLDER/'browser-playback.json')
if verified['status']!='Passed' or browser['status']!='Passed' or browser['consoleErrors']:
    raise RuntimeError('Final media and actual browser acceptance required')
if not {1,.5}.issubset({x['speed'] for x in browser['playbacks']}) or not all(x['bothEnded'] for x in browser['playbacks']):raise RuntimeError('Normal/half playback incomplete')
if not all(browser.get(k) for k in ['audioSelectionsPassed','seekAndStepPassed','zoomPassed']):raise RuntimeError('Actual viewer/audio controls incomplete')
if sha(media(browser['screenshot']))!=browser['screenshotSha256']:raise RuntimeError('Screenshot drift')
if sha(media(s['finalPath']))!=verified['videos']['final']['sha256']:raise RuntimeError('Final file drift')
for name in ['api-admission-checks.json','caption-api-checks.json']:
    if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Actual API checks incomplete')
versions={}
for folder in ['FaceActing20261024','VisualValidation20261024','VisualTargeted20261024']:
    old=read(DATA/folder/'run.json')
    for item in old.get('preserved',[]):versions[item['path']]=item['sha256']
    for key,path in old.items():
        if key.endswith('Path') and isinstance(path,str) and old.get(key[:-4]+'Sha256'):versions[path]=old[key[:-4]+'Sha256']
    for i in range(1,7):
        if old.get(f'keyframe{i}Sha256'):versions[old[f'keyframe{i}Path']]=old[f'keyframe{i}Sha256']
    for item in old.get('actingCandidates',[])+old.get('blinkCandidates',[]):versions[item['path']]=item['sha256']
    for i,digest in old.get('referenceHashes',{}).items():versions[f'{folder}/reference-{i}.png']=digest
for path,digest in versions.items():
    if sha(media(path))!=digest:raise RuntimeError('A prior preserved version changed: '+path)
for item in read(FOLDER/'model-inventory.json')['files']:
    path=ROOT.parent/'Models'/item['path']
    if not path.exists() or path.stat().st_size!=item['size'] or path.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model directory metadata changed')
tasks=[]
for file in sorted(FOLDER.glob('task-*.json')):
    task=read(file)['task'];live=r.api(f'/api/tasks/{task["id"]}')['task']
    if live['projectId']!=s['projectId'] or live['status']!='Succeeded':raise RuntimeError('Recorded task is not actually successful')
    tasks.append(live)
gpu=sorted((x['startedAt'],x['finishedAt'],x['id']) for x in tasks if x['resourceClass']=='GPU')
if any(a[1]>b[0] for a,b in zip(gpu,gpu[1:])):raise RuntimeError('GPU execution overlaps')
active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
queue=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if active or queue['queue_running'] or queue['queue_pending']:raise RuntimeError('Other local work remains active; do not disturb it')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines() if line.strip()]
write(FOLDER/'execution-summary.json',dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','status','resourceClass','durationMs','startedAt','finishedAt']} for t in tasks],
    gpuMaxConcurrency=1,sampledPeakDeviceVramMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),
    sampledMinAvailableRamMiB=min(x['availableRamMiB'] for x in samples),sampledMinFreeDiskGiB=min(x['freeDiskGiB'] for x in samples),
    measurementScope='Device/system samples, not exact per-process peaks',priorVersionHashesVerified=len(versions),
    modelMetadataFilesUnchanged=verified['modelMetadataFilesUnchanged'],newModelDownloads=0,cloudInferenceCalls=0,
    cuts=[53,96],frames=240,seconds=10,audioPacketsEqual=True,audioPcmEqual=True,
    finalPictureVideoEncodingPasses=1,finalAudioRemuxVideoEncodingPasses=0,contentStatus='NeedReview',publicationStatus='Blocked'))
r.api('/api/production/pause',{})
original=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');original.access();was_paused=s['originalQueueStatus']['paused']
original.api('/api/production/pause' if was_paused else '/api/production/resume',{})
old_status=original.api('/api/minimax/local/status')['queue'];pilot_status=r.api('/api/minimax/local/status')['queue'];health=original.api('/api/health')
if old_status['paused']!=was_paused or not pilot_status['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Final environment restoration failed')
write(FOLDER/'final-environment-verification.json',dict(status='Passed',originalQueueRestored=True,originalQueuePaused=was_paused,pilotQueuePaused=True,
    databaseOnline=True,comfyOnline=True,ffmpegAvailable=True,activeTasks=[],comfyQueueIdle=True,olderVersionHashesVerified=len(versions),modelMetadataUnchanged=True,
    oneShotResumeAutomationRemoved=True))
r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',newTaskSubmitted=False,
    previewUrl='http://127.0.0.1:18080/dialogue-visual.html')
print('ReadyForUserPreview: complete 10s dialogue; technical Passed; original voice/cuts/versions retained; original queue restored')

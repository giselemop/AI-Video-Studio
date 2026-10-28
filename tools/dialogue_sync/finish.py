"""Seal only after actual A/B playback; restore original queues and retain media."""
from run import *
p=argparse.ArgumentParser();p.add_argument('--browser-evidence',action='store_true');args=p.parse_args()
r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
evidence=read(FOLDER/'browser-environment.json') if args.browser_evidence else None
if evidence:
    if not all((FOLDER/evidence['actions'][key]).is_file() for key in ['originalResume','pilotPause']):raise RuntimeError('Actual queue UI records required')
    if '生产队列已继续' not in (FOLDER/evidence['actions']['originalResume']).read_text(encoding='utf-8') or '生产队列已暂停' not in (FOLDER/evidence['actions']['pilotPause']).read_text(encoding='utf-8'):raise RuntimeError('Queue UI results missing')
else:r.access()
r.preserve();s=r.state
verified=read(FOLDER/'final-verification.json');browser=read(FOLDER/'browser-playback.json');admission=read(FOLDER/'api-admission-checks.json')
if any(x['status']!='Passed' for x in [verified,browser,admission]) or browser['consoleErrors']:raise RuntimeError('Actual final media/browser/API acceptance required')
if s.get('wideHybridSelected') and read(FOLDER/'hybrid-api-checks.json')['status']!='Passed':raise RuntimeError('Hybrid actual boundary checks required')
required={(name,speed) for name in ['close','wide'] for speed in [1,.5]}
if not required.issubset({(x['clip'],x['speed']) for x in browser['playbacks'] if x['bothEnded']}):raise RuntimeError('Both clips need complete normal and half playback')
if not all(browser.get(k) for k in ['clipSwitchPassed','audioSelectionsPassed','seekAndStepPassed','zoomPassed']):raise RuntimeError('Actual comparison controls incomplete')
if sha(media(browser['screenshot']))!=browser['screenshotSha256']:raise RuntimeError('Screenshot drift')
for clip in CLIPS:
    if sha(media(s[clip['name']+'FinalPath']))!=verified['videos'][clip['name']+'Final']['sha256']:raise RuntimeError('Final pilot changed')
adapt=read(FOLDER/'compose-adaptation.json')
if sha(ROOT/'tools/dialogue_visual/compose.py')!=adapt['baseSha256'] or sha(ROOT/'tools/dialogue_sync/compose.py')!=adapt['newSha256']:raise RuntimeError('Frozen compositor source changed')
versions={}
for folder in ['FaceActing20261024','VisualValidation20261024','VisualTargeted20261024','DialogueVisual20261025']:
    old=read(DATA/folder/'run.json')
    for item in old.get('preserved',[]):versions[item['path']]=item['sha256']
    for key,value in old.items():
        if key.endswith('Path') and isinstance(value,str) and old.get(key[:-4]+'Sha256'):versions[value]=old[key[:-4]+'Sha256']
    for item in old.get('actingCandidates',[])+old.get('blinkCandidates',[]):versions[item['path']]=item['sha256']
    for i,digest in old.get('referenceHashes',{}).items():versions[f'{folder}/reference-{i}.png']=digest
for path,digest in versions.items():
    if sha(media(path))!=digest:raise RuntimeError('A prior version changed: '+path)
inventory=read(FOLDER/'model-inventory.json')['files']
for item in inventory:
    p=ROOT.parent/'Models'/item['path']
    if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model metadata changed')
tasks=[]
for file in sorted(FOLDER.glob('task-*.json')):
    t=read(file)['task']
    matches=[x for x in evidence['pilotTasks'] if x['id']==t['id']] if evidence else []
    if evidence and len(matches)!=1:raise RuntimeError('Browser task detail missing or duplicated')
    live=matches[0] if evidence else r.api('/api/tasks/'+str(t['id']))['task']
    if live['status']!='Succeeded' or live['projectId']!=s['projectId']:raise RuntimeError('A recorded real task did not succeed')
    tasks.append(live)
gpu=sorted((x['startedAt'],x['finishedAt'],x['id']) for x in tasks if x['resourceClass']=='GPU')
if any(a[1]>b[0] for a,b in zip(gpu,gpu[1:])):raise RuntimeError('GPU execution overlapped')
active=[x['id'] for x in (evidence['tasks'] if evidence else r.api('/api/tasks?limit=500')) if x['status'] in ['Running','Pending','Queued']]
q=evidence['comfyQueue'] if evidence else r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Tasks remain active; preserve their work')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines() if line.strip()]
write(FOLDER/'execution-summary.json',dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','resourceClass','status','durationMs','startedAt','finishedAt']} for t in tasks],
    gpuMaxConcurrency=1,sampledPeakDeviceVramMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),sampledMinAvailableRamMiB=min(x['availableRamMiB'] for x in samples),
    sampledMinFreeDiskGiB=min(x['freeDiskGiB'] for x in samples),measurementScope='Device/system samples; not exact process peaks or continuous health guarantee',
    olderVersionHashesVerified=len(versions),modelMetadataFilesUnchanged=len(inventory),newModelDownloads=0,cloudInferenceCalls=0,
    pairedAudioPacketsEqual=True,pairedAudioPcmEqual=True,contentStatus='NeedReview',publicationStatus='Blocked'))
if evidence:
    health=evidence['health'];a=evidence['original']['queue']['paused'];b=evidence['pilot']['queue']['paused']
    if any(evidence[k]['queue']['activeTasks'] for k in ['original','pilot']):raise RuntimeError('Live browser queue not idle')
else:
    old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    for api,paused in [(r,s['pilotQueueStatus']['paused']),(old,s['originalQueueStatus']['paused'])]:api.api('/api/production/pause' if paused else '/api/production/resume',{})
    health=old.api('/api/health');a=old.api('/api/minimax/local/status')['queue']['paused'];b=r.api('/api/minimax/local/status')['queue']['paused']
if a!=s['originalQueueStatus']['paused'] or b!=s['pilotQueueStatus']['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Final queue/environment restoration failed')
write(FOLDER/'final-environment-verification.json',dict(status='Passed',originalQueueRestored=True,originalQueuePaused=a,pilotQueueRestored=True,pilotQueuePaused=b,databaseOnline=True,comfyOnline=True,ffmpegAvailable=True,activeTasks=[],comfyIdle=True,olderVersionHashesVerified=len(versions),modelMetadataUnchanged=True,
    observationMethod='Existing production UI controls and read-only rendered API pages' if evidence else 'Local API',browserEvidenceSha256=sha(FOLDER/'browser-environment.json') if evidence else None))
r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',previewUrl='http://127.0.0.1:18080/dialogue-sync.html')
print('Passed: two local pilots sealed, old versions retained and original queues restored')

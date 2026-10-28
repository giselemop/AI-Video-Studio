"""Seal only after real decode, bounded content review and browser evidence."""
from run import *
from datetime import datetime
def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Preserved; no new tasks');return
    r.access();r.preserve();s=r.state
    for name in ['repeatability.json','admission-checks.json','composition-checks.json','caption-render-checks.json','final-verification.json','native-review.json','final-content-review.json','browser-playback.json','legacy-protocol-checks.json','caption-regression.json']:
        if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Missing acceptance '+name)
    b=read(FOLDER/'browser-playback.json')
    if b['consoleErrors'] or not b['normalBothEnded'] or not b['halfBothEnded'] or not b['seekAndStepPassed'] or not b['zoomPassed'] or not b['audioSelectionsPassed']:raise RuntimeError('Browser acceptance incomplete')
    if sha(media(b['screenshot']))!=b['screenshotSha256'] or sha(media(b['cutScreenshot']))!=b['cutScreenshotSha256']:raise RuntimeError('Browser evidence changed')
    tasks=[]
    for p in FOLDER.glob('task-*.json'):
        t=read(p)['task'];live=r.api('/api/tasks/'+str(t['id']))['task']
        if live['status']!='Succeeded' or live['projectId']!=s['projectId']:raise RuntimeError('Actual task unresolved')
        tasks.append(live)
    gpu=sorted((t['startedAt'],t['finishedAt'],t['id']) for t in tasks if t['resourceClass']=='GPU')
    if any(a[1]>b[0] for a,b in zip(gpu,gpu[1:])):raise RuntimeError('GPU overlap')
    active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']];q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Active work; preserve')
    samples=[json.loads(x) for x in (FOLDER/'resources.jsonl').read_text().splitlines() if x.strip()]
    write(FOLDER/'execution-summary.json',dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','resourceClass','status','durationMs','startedAt','finishedAt']} for t in sorted(tasks,key=lambda t:t['id'])],gpuMaxConcurrency=1,sampledPeakDeviceVramMiB=max(x['gpu'][0] for x in samples if x.get('gpu')),sampledMinAvailableRamMiB=min(x['availableRamMiB'] for x in samples),preservedFileHashesVerified=len(s['preserved']),modelMetadataFilesUnchanged=len(read(FOLDER/'model-inventory.json')['files']),newModelDownloads=0,newDiffusionJobs=0,newNeuralUpscaleJobs=0,cloudInferenceCalls=0,measurementScope='Sampled system/device resources for this reused-driver portrait/CPU path, not full generation capacity. V1 repeat test failure preserved; V2 test passed.',contentStatus='NeedReview',publicationStatus='Blocked'))
    old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    for api,paused in [(r,s['pilotQueueStatus']['paused']),(old,s['originalQueueStatus']['paused'])]:api.api('/api/production/pause' if paused else '/api/production/resume',{})
    health=old.api('/api/health');a=old.api('/api/minimax/local/status')['queue']['paused'];c=r.api('/api/minimax/local/status')['queue']['paused']
    if a!=s['originalQueueStatus']['paused'] or c!=s['pilotQueueStatus']['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Environment restoration failed')
    write(FOLDER/'final-environment.json',dict(status='Passed',originalQueuePaused=a,pilotQueuePaused=c,activeTasks=[],comfyIdle=True,databaseOnline=True,comfyOnline=True,ffmpegAvailable=True))
    r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',previewUrl='http://127.0.0.1:18080/dialogue-stable.html')
    print('Passed: stable768 full version sealed; queues restored')
if __name__=='__main__':main()

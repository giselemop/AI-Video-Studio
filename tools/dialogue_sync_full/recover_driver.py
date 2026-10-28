"""Recover the same genuinely completed Comfy prompt after watcher timeout; no re-inference."""
from run import *
from verify_helpers import video_packets,audio,inspect
r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
if r.state.get('completed'):r.preserve();print('Preserved; no new tasks');sys.exit(0)
r.access();r.preserve();s=r.state
failed=r.api('/api/tasks/'+str(s['driver3TaskId']))
if failed['task']['status']!='Failed' or failed['task']['errorType']!='TASK_TIMEOUT' or failed['results']:raise RuntimeError('Only the recorded un-published watcher timeout may be recovered')
q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if q['queue_running'] or q['queue_pending']:raise RuntimeError('Original Comfy computation not idle; never resubmit or overlap')
history=r.session.get('http://127.0.0.1:8188/history',timeout=30).json();matches=[]
for pid,e in history.items():
    graph=e.get('prompt',[None,None,{}])[2]
    if any(('task_'+str(s['driver3TaskId'])+'_') in str(n.get('inputs',{}).get('filename_prefix','')) for n in graph.values() if isinstance(n,dict)):matches.append((pid,e))
if len(matches)!=1 or matches[0][1].get('status',{}).get('status_str')!='success':raise RuntimeError('Original Comfy prompt must actually have completed successfully')
pid,entry=matches[0];items=[]
for node in entry['outputs'].values():
    for values in node.values():
        if isinstance(values,list):items += [x for x in values if isinstance(x,dict) and str(x.get('filename','')).endswith('.mp4')]
if len(items)!=1:raise RuntimeError('Completed original driver not unique')
root=(ROOT.parent/'ComfyUI/output').resolve();item=items[0];raw=(root/item.get('subfolder','')/item['filename']).resolve(strict=True)
if not raw.is_relative_to(root):raise RuntimeError('Original Comfy file outside controlled output root')
target=FOLDER/'recovered-original-comfy-driver3.mp4'
if target.exists() and sha(target)!=sha(raw):raise RuntimeError('Frozen recovered input differs')
if not target.exists():shutil.copy2(raw,target)
specification=inspect(rel(target),832,480,25,151)
graph=entry['prompt'][2]
if graph['7']['inputs']['audio_cfg_scale']!=2 or graph['7']['inputs']['num_frames']!=151:raise RuntimeError('Original executed driver differs')
write(FOLDER/'recovered-comfy-history.json',{pid:entry})
r.api('/api/production/resume',{})
body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='SyncFull-Recover-Completed-Comfy-1373',parameters=dict(files=[rel(target)],videoSha256=sha(target),audioStreamCopyFrom=rel(target),audioStreamCopySha256=sha(target),outputName='recovered_full_wide_audio_driver.mp4'))
detail=r.once('driver3RecoveryTaskId',body);asset(r,'driver3',detail)
if video_packets(s['driver3Path'])!=video_packets(rel(target)) or audio(s['driver3Path'])!=audio(rel(target)):raise RuntimeError('Recovery remux altered media packets')
messages=entry['status']['messages'];start=next(x[1]['timestamp'] for x in messages if x[0]=='execution_start');end=next(x[1]['timestamp'] for x in messages if x[0]=='execution_success')
write(FOLDER/'driver-recovery.json',dict(status='Passed',failedTaskId=s['driver3TaskId'],failedTaskStatus='Failed',failureType='TASK_TIMEOUT',promptId=pid,comfyStatus='success',actualComfyStartEpochMs=start,actualComfyEndEpochMs=end,actualComfyDurationMs=end-start,rawPath=str(raw),importedPath=rel(target),rawSha256=sha(raw),importedSha256=sha(target),recoveryTaskId=s['driver3RecoveryTaskId'],publishedPath=s['driver3Path'],publishedSha256=s['driver3Sha256'],videoPacketsUnchanged=True,audioPacketsUnchanged=True,comfyIdleBeforeRecovery=True,newGpuSubmissions=0,scope='Same original real-queue prompt1373 finished after watcher deadline. OriginalFailed remains; separate realCPU task validates/publishes stream-copy remux. No repeated inference and no manual DB status changes.',specification=specification))
r.save('AwaitingDriverInspection',driver3Recovered=True);print('Passed: same genuine Comfy output recovered by real CPU queue; original failure preserved; no new GPU submission')

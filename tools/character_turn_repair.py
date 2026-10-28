"""Targeted H3 repair of task1550. Every real video is queued by VideoStudio.

Completed originals remain read-only. The original story review hold is not
resumed, and no candidate, reference, or character version is approved here.
"""
from pathlib import Path
import argparse,datetime,json,msvcrt,re,sys,uuid
import requests
sys.path.insert(0,str(Path(__file__).parent/'character_scene'))
from common import ROOT,DATA,write,sha,mysql
OUT=DATA/'CharacterTurnRepair20261027'
BASE=DATA/'CharacterSinglePreview20261027'
PROMPTS={
  1:('A continuous close-up of the same woman in the same room, with an absolutely locked camera. '
     'The woman begins facing the camera. Clearly ROTATE HER ENTIRE HEAD toward the LEFT EDGE OF THE IMAGE, '
     'so her nose and gaze visibly point to the viewer\'s left, approximately 20 to 25 degrees. '
     'Hold the left-facing head pose briefly, then smoothly rotate her entire head back to the starting camera-facing pose. '
     'Perform exactly one visible left turn and one return within the clip. Her shoulders and torso remain still. '
     'Keep her exact face, age, black shoulder-length hair, cream knitted sweater, facial structure, skin and earrings. '
     'Natural slow motion, realistic neck and eyes, neutral expression, mouth closed, no speech. '
     'No camera movement, scene cut, extra person, extra face, clothing change, deformation or background change.'),
  2:('The same woman sits still in the same close-up with a fixed camera. Starting from the provided image, '
     'first she deliberately turns her WHOLE HEAD so her nose points toward SCREEN LEFT and pauses there; '
     'then she slowly turns her head back so her nose and eyes face the camera again at the end. '
     'Show a clearly visible moderate leftward rotation rather than only eye motion. '
     'Preserve the same woman\'s recognizable face, black shoulder-length hair, cream knitted sweater, earrings, age and body position. '
     'One smooth left turn, one return, realistic eyes and neck, neutral face, closed mouth, no speaking. '
     'Camera, background and clothing remain unchanged, without a cut, second face or extra person. Quiet indoor ambience, no voices or music.')}

class Repair:
 def __init__(self):
    OUT.mkdir(parents=True,exist_ok=True);self.path=OUT/'run.json';self.base='http://127.0.0.1:18080';self.s=requests.Session()
    self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(runId=str(uuid.uuid4()),stage='Created',completed=False,baseTaskId=1550,attempts=[],maxRepairs=2,contentReview='NeedReview',publication='Blocked',newModels=0,newCloudCalls=0)
    auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];self.s.headers['X-CSRF-Token']=auth['csrfToken']
 def save(self):write(self.path,self.state)
 def api(self,path,body=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP '+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def preconditions(self):
    health=self.api('/api/health');queue=self.api('/api/minimax/local/status')['queue'];comfy=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert health['database']['online'] and health['comfy']['online'] and health['ffmpeg']['available'] and health['comfy']['gpu']['freeMiB']>=1024
    assert queue['gpuConcurrency']==1 and not queue['activeTasks'] and not queue['paused'] and not comfy['queue_running'] and not comfy['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');")=='0'
    return health,queue
 def prepare(self):
    if self.state.get('projectId'):return
    health,queue=self.preconditions();old=json.loads((BASE/'run.json').read_text(encoding='utf-8'));inspection=json.loads((BASE/'visual-inspection.json').read_text(encoding='utf-8'))
    assert old['completed'] and old['taskId']==1550 and old['previewInspection']=='Failed' and inspection['directedHeadTurnCheck']=='Failed'
    assert self.api('/api/tasks/1550')['task']['status']=='Succeeded' and sha(DATA/old['assetPath'])==old['sha256']
    version=next(v for v in self.api('/api/character-library')['versions'] if v['id']==3);source=next(r for r in version['payload']['references'] if r['referenceId']==36 and r['view']=='front')
    reference=next(r for r in self.api('/api/characters/19/references') if r['id']==36)
    assert reference['available'] and reference['reviewStatus']=='Approved' and reference['assetSha256']==source['sha256']==sha(DATA/source['assetPath'])
    assert source['sha256']==old['sourceReference']['sha256'] and version['sha256']==old['versionSnapshot']['sha256']
    assert version['payload']['workflow']['profile']=='baseline480' and sha(ROOT.parent/'Workflows'/version['payload']['workflow']['fileName'])==version['payload']['workflow']['sha256']
    scene=DATA/'CharacterScene20261027/run.json';assert json.loads(scene.read_text(encoding='utf-8'))['generationHold']['active']
    self.state.update(startedAt=datetime.datetime.now().astimezone().isoformat(),source=source,versionSnapshot=version,baseRunSha256=sha(BASE/'run.json'),baseVideoPath=old['assetPath'],baseVideoSha256=old['sha256'],baseInspection=inspection,sceneCheckpointSha256=sha(scene),initialTaskCount=int(mysql('SELECT COUNT(*) FROM generation_tasks;')),healthBefore=health,queueBefore=queue,baseSeed=old['request']['seed'],directionConvention='screen-left / viewer-left',mode='Character-Library-Experiment',audioStrategy='NativeH3; preview muted by default, audio content unreviewed');self.save()
    name='林安左转回正定向试片_'+self.state['runId'][:8];existing=next((p for p in self.api('/api/projects') if p['name']==name),None)
    self.state['projectId']=existing['id'] if existing else self.api('/api/projects',dict(name=name,description='Targeted repair of task1550: visible screen-left head turn then return; same approved library version3/reference36, output remains NeedReview.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id']
    self.state['stage']='Prepared';self.save()
 def submit(self,attempt):
    if self.state.get('completed'):
        if len(self.state.get('attempts',[]))>=attempt and self.state['attempts'][attempt-1].get('taskId'):
            print('Completed run is read-only; preserved existing task '+str(self.state['attempts'][attempt-1]['taskId']));return
        raise RuntimeError('Completed run is read-only; no new attempt')
    self.prepare()
    if attempt not in [1,2]:raise RuntimeError('Maximum two targeted repairs')
    attempts=self.state['attempts']
    if len(attempts)>=attempt:
        a=attempts[attempt-1]
        if a.get('taskId'):print('Existing attempt retained: '+str(a['taskId']));return
    else:
        if len(attempts)!=attempt-1:raise RuntimeError('Attempts must be sequential')
        if attempt==2 and attempts[0].get('inspection',{}).get('status')!='Failed':raise RuntimeError('Second repair requires recorded first-attempt content failure')
        prompt=PROMPTS[attempt];seed=self.state['baseSeed'] if attempt==1 else self.state['baseSeed']+100
        body=dict(projectId=self.state['projectId'],versionId=3,view='front',prompt=prompt,seed=seed,idempotencyKey=f'turn-repair:{self.state["runId"]}:{attempt}')
        attempts.append(dict(attempt=attempt,request=body,parentTaskId=1550 if attempt==1 else attempts[0]['taskId'],reason='原1550向画面左转头和回正未明显命中' if attempt==1 else '第一次定向结果未通过实际画面检查',changes='明确整个头部向画面左20–25度、停顿再回正；沿用同参考、工作流、种子与规格' if attempt==1 else '调整动作提示词和种子，仅重做本失败项'))
        self.state['stage']='AttemptPrepared';self.save();a=attempts[-1]
    folder=OUT/f'attempt-{attempt}';folder.mkdir(exist_ok=True);key=a['request']['idempotencyKey'];assert re.fullmatch(r'[A-Za-z0-9:-]+',key)
    existing=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if existing:
        a['taskId']=int(existing);self.state['stage']='RecoveredExistingTask';self.save();print('Recovered already-created attempt '+str(a['taskId']));return
    if a.get('submissionIntentAt'):raise RuntimeError('Submission outcome uncertain and no task found; inspect API and queue before retrying')
    self.preconditions();resolved=self.api('/api/character-library/resolve',a['request']);binding=resolved['binding']
    assert binding['versionId']==3 and binding['referenceId']==36 and binding['referenceSha256']==self.state['source']['sha256']
    task=resolved['task'];task['dependencyTaskId']=a['parentTaskId'];task['maxRetries']=0
    write(folder/'resolved.json',resolved);write(folder/'submission-task.json',task)
    preflight=self.api('/api/tasks/preflight',task);write(folder/'preflight.json',preflight)
    if not preflight['passed']:raise RuntimeError('Preflight rejected: '+json.dumps(preflight.get('issues'),ensure_ascii=False))
    a['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.state['stage']='SubmissionPrepared';self.save()
    result=self.api('/api/tasks',task);write(folder/'submission.json',result);a['taskId']=result['id'];self.state['stage']='VideoQueued';self.save()
    print(f'Queued targeted repair {attempt}: task {a["taskId"]}, parent {a["parentTaskId"]}, same approved character reference36.')
 def tick(self,attempt):
    a=self.state['attempts'][attempt-1];folder=OUT/f'attempt-{attempt}';detail=self.api('/api/tasks/'+str(a['taskId']));write(folder/'task.json',detail);a['status']=detail['task']['status']
    raw=mysql("SELECT JSON_OBJECT('id',id,'status',status,'input',input_json,'comfyPromptId',comfy_prompt_id,'durationMs',duration_ms,'vramPeakMiB',vram_peak_mib,'dependencyTaskId',dependency_task_id) FROM generation_tasks WHERE id="+str(a['taskId'])+';')
    trace=json.loads(raw);write(folder/'task-trace.json',trace)
    if trace.get('comfyPromptId'):
        history=requests.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30).json()
        if history:write(folder/'comfy-history.json',history)
    if a['status']=='Succeeded':
        result=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.mp4'));a.update(assetPath=result['assetPath'],sha256=sha(DATA/result['assetPath']));self.state['stage']='VideoReady'
    elif a['status'] in ['Failed','Cancelled']:a['failure']=detail['task'].get('errorMessage');self.state['stage']='Failed'
    else:self.state['stage']=a['status']
    self.save();print(json.dumps(dict(attempt=attempt,taskId=a['taskId'],status=a['status'],progress=detail['task'].get('progress'),comfyPromptId=trace.get('comfyPromptId'),failure=a.get('failure')),ensure_ascii=False))
 def inspect(self,attempt,decision,note):
    if decision not in ['Passed','Failed'] or not note:raise RuntimeError('An explicit visual decision and actual observations are required')
    a=self.state['attempts'][attempt-1];folder=OUT/f'attempt-{attempt}'
    checks=json.loads((folder/'media-checks.json').read_text(encoding='utf-8'))
    if a.get('status')!='Succeeded' or checks['status']!='Passed' or sha(DATA/a['assetPath'])!=a['sha256']:raise RuntimeError('Inspect the actual verified video first')
    inspection=dict(status=decision,scope='PreviewInspection',taskId=a['taskId'],sourceSha256=self.state['source']['sha256'],outputSha256=a['sha256'],framesInspected=checks['frameIndices'],note=note,reviewer='local-operator',checkedAt=datetime.datetime.now().astimezone().isoformat(),humanApproved=False,identityScore=None,contentReview='NeedReview',publication='Blocked')
    write(folder/'visual-inspection.json',inspection);a['inspection']=inspection;self.state['stage']='PreviewInspected' if decision=='Passed' else 'ContentFailed';self.save()
    print('Actual frame inspection '+decision+'; human content approval remains NeedReview.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['submit','tick','inspect']);parser.add_argument('--attempt',type=int,default=1);parser.add_argument('--decision',choices=['Passed','Failed']);parser.add_argument('--note');a=parser.parse_args();OUT.mkdir(exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);r=Repair()
        if a.command=='inspect':r.inspect(a.attempt,a.decision,a.note)
        else:getattr(r,a.command)(a.attempt)
if __name__=='__main__':main()

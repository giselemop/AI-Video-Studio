"""One new single-actor plot: actual story plan -> inspected keyframe -> H3.

Every request has a durable idempotency key and uses the existing business
queue. Original completed runs, rejected material and review holds are read-only.
"""
from pathlib import Path
import argparse,datetime,json,msvcrt,re,sys,uuid
import requests
sys.path.insert(0,str(Path(__file__).parent/'character_scene'))
from common import ROOT,DATA,OUT as _,sha,write,mysql
OUT=DATA/'CharacterPlotPreview20261027'
SCENE=('A quiet cozy room in the afternoon. Lin An is sitting beside a large wooden window; '
       'soft daylight and distant green trees are visible through the glass. Same person, same cream knit top. '
       'Single person, no phone, no handheld objects, no other person. Warm natural light.')
START=('Lin An is waiting for a friend by the window. Her head and gaze face almost toward the camera, '
       'with a thoughtful and expectant expression, lips gently closed, before she notices anyone.')
ACTION=('Initially she waits quietly beside the window, looking thoughtful. She notices a friend arriving offscreen on picture LEFT. '
        'She turns her whole head and gaze gently toward picture LEFT, pauses, then turns her head back toward the camera. '
        'As she recognizes the friend, her worried expression softens into a small warm closed-mouth smile. '
        'One continuous natural response; same hair, face and cream knit top, no speaking, no extra person.')
CAMERA='Eye-level locked close-up, same framing throughout, no camera motion, zoom, crop or cut.'

class Plot:
 def __init__(self):
    self.path=OUT/'run.json';self.state=json.loads(self.path.read_text(encoding='utf-8'));self.base='http://127.0.0.1:18080';self.s=requests.Session()
    auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];self.s.headers['X-CSRF-Token']=auth['csrfToken']
 def save(self):write(self.path,self.state)
 def key(self,label):return 'plot-preview:'+self.state['runId']+':'+label
 def api(self,path,body=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP '+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def preserve(self):
    for item in self.state['protectedFiles']:
        if sha(Path(item['path']))!=item['sha256']:raise RuntimeError('Protected earlier artifact changed: '+item['path'])
 def idle(self):
    health=self.api('/api/health');q=self.api('/api/minimax/local/status')['queue'];c=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert health['database']['online'] and health['comfy']['online'] and health['ffmpeg']['available'] and health['comfy']['gpu']['freeMiB']>=1024
    assert not q['paused'] and q['gpuConcurrency']==1 and q['activeTasks']==0 and not c['queue_running'] and not c['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');")=='0'
 def prepare(self):
    if self.state.get('completed'):raise RuntimeError('Completed plot is read-only')
    self.preserve();self.idle();assert self.api('/api/character-story/readiness')['ready']
    library=self.api('/api/character-library')['versions'];version=next(v for v in library if v['id']==3);reference=next(x for x in self.api('/api/characters/19/references') if x['id']==36)
    assert reference['reviewStatus']=='Approved' and reference['available'] and reference['assetSha256']==sha(DATA/reference['assetPath'])
    self.state.update(actorVersionSha256=version['sha256'],sourceReference=reference,scene=SCENE,startingState=START,action=ACTION,camera=CAMERA,audioStrategy='PostDubbing',initialTaskCount=int(mysql('SELECT COUNT(*) FROM generation_tasks;')));self.save()
    name='窗边等候_单人剧情_'+self.state['runId'][:8]
    if not self.state.get('projectId'):
        old=next((p for p in self.api('/api/projects') if p['name']==name),None);self.state['projectId']=old['id'] if old else self.api('/api/projects',dict(name=name,description='Single close-up plot preview using explicitly selected approved legacy headshot36; no full-body claim. Content NeedReview.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id'];self.save()
    pid=self.state['projectId']
    if not self.state.get('castId'):
        record=self.api(f'/api/character-story/projects/{pid}/cast',dict(roles=[dict(role='林安',versionId=3)],audioStrategy='PostDubbing',idempotencyKey=self.key('project-cast')));self.state['castId']=record['id'];self.save()
    if not self.state.get('episodeId'):
        old=next((e for e in self.api(f'/api/projects/{pid}/episodes') if e['name']=='窗边等候'),None);self.state['episodeId']=old['id'] if old else self.api('/api/episodes',dict(projectId=pid,name='窗边等候',episodeNumber=1,outputWidth=864,outputHeight=480,outputFps=24,targetSeconds=124/24))['id'];self.save()
    eid=self.state['episodeId']
    if not self.state.get('episodeCastId'):
        self.state['episodeCastId']=self.api(f'/api/character-story/episodes/{eid}/cast',dict(idempotencyKey=self.key('episode-cast')))['id'];self.save()
    if not self.state.get('shotId'):
        old=next((s for s in self.api(f'/api/episodes/{eid}/shots') if s['title']=='久候的回应'),None);self.state['shotId']=old['id'] if old else self.api('/api/shots',dict(projectId=pid,episodeId=eid,shotNumber=1,title='久候的回应',width=864,height=480,frames=124,fps=24,durationSeconds=124/24))['id'];self.save()
    if not self.state.get('planBody'):
        self.state['planBody']=dict(episodeCastId=self.state['episodeCastId'],shotFraming='closeUp',scene=SCENE,action=ACTION,camera=CAMERA,props='No handheld props, no text and no other person.',actors=[dict(role='林安',view='front',framing='closeUp',position='center',action=START,legacyHeadshotReferenceId=36)],idempotencyKey=self.key('shot-plan'));self.save()
    print('Plot, source and project/episode/shot checkpoint prepared. No generation or approval.')
 def api_checks(self):
    self.prepare();before=mysql('SELECT COUNT(*) FROM generation_tasks;');sid=self.state['shotId'];uri='/api/character-story/shots/'+str(sid);base=self.state['planBody'];checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(OUT/'api-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    def reject(name,body):
        r=self.s.post(self.base+uri,json=body,timeout=30);check(name,r.status_code==422)
    import copy
    def variant(label):
        b=copy.deepcopy(base);b['idempotencyKey']=self.key('negative-'+label);return b
    b=variant('missing-explicit');b['actors'][0].pop('legacyHeadshotReferenceId');reject('no silent legacy fallback',b)
    b=variant('wrong-reference');b['actors'][0]['legacyHeadshotReferenceId']=37;reject('wrong view reference rejected',b)
    b=variant('unknown-reference');b['actors'][0]['legacyHeadshotReferenceId']=999999;reject('unknown reference rejected',b)
    b=variant('full-body');b['shotFraming']='fullBody';b['actors'][0]['framing']='fullBody';reject('legacy portrait cannot stand in for full body',b)
    b=variant('fixed-scene');b['sceneVersionId']=29;reject('legacy portrait cannot bypass fixed scene actor binding',b)
    record=self.api(uri,base);self.state.update(planId=record['id'],planSha256=record['sha256']);self.save();a=record['payload']['actors'][0]
    check('explicit frozen identity and reference36',a['referenceMode']=='ApprovedLegacyHeadshotV1' and a['legacyHeadshotReferenceId']==36 and a['reference']['sha256']==self.state['sourceReference']['assetSha256'])
    check('no invented full-body reference','outfitReference' not in a and a['reference'].get('framing') is None)
    same=self.api(uri,base);check('identical plan request is idempotent',same['id']==record['id'] and same['sha256']==record['sha256'])
    request=dict(planId=record['id'],profile='baseline480',seed=2026102751,idempotencyKey=self.key('keyframe'))
    resolved=self.api('/api/character-story/resolve/Keyframe',request);write(OUT/'keyframe-resolved.json',resolved);task=resolved['task'];params=task['parameters'];marker=params['storyPipeline']
    check('actual workflow gets one explicit identity slot',list(params['inputSlots'])==['firstFrame'] and params['inputSlots']['firstFrame']==self.state['sourceReference']['assetPath'])
    check('source hash and plan provenance frozen',marker['planId']==record['id'] and marker['inputSha256']==self.state['sourceReference']['assetSha256'] and marker['inputHashes'][params['inputSlots']['firstFrame']]==self.state['sourceReference']['assetSha256'])
    preflight=self.api('/api/tasks/preflight',task);check('generic submission cannot bypass story business gate',not preflight['passed'])
    response=self.s.post(self.base+'/api/character-story/resolve/Video',json=dict(request,keyframeTaskId=0,reviewId=0),timeout=30);check('video without inspected keyframe rejected',response.status_code==422)
    check('API tests did not submit GPU work',mysql('SELECT COUNT(*) FROM generation_tasks;')==before)
    write(OUT/'api-checks.json',dict(status='Passed',checks=checks,gpuSubmitted=0,humanApprovals=0));self.state['stage']='ReadyForKeyframe';self.save();print(str(len(checks))+' live API checks Passed; actor36 and incomplete legacy coverage remain explicit.')
 def submit(self,kind):
    if self.state.get('completed'):print('Completed plot retained; no task resubmitted.');return
    if not self.state.get('planId'):raise RuntimeError('Run API checks and freeze the plan first')
    entry=self.state.setdefault(kind,{})
    if entry.get('id'):print('Existing '+kind+' task '+str(entry['id'])+' retained');return
    self.preserve();self.idle();body=dict(planId=self.state['planId'],profile='baseline480',seed=2026102751 if kind=='Keyframe' else 2026102752,idempotencyKey=self.key(kind.lower()))
    if kind=='Video':
        frame=self.state.get('Keyframe',{});review=frame.get('inspection',{});
        if review.get('payload',{}).get('decision')!='Passed':raise RuntimeError('Inspect and pass the actual keyframe before any video')
        body.update(keyframeTaskId=frame['id'],reviewId=review['id'])
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen request changed')
    entry['body']=body;self.save()
    key=body['idempotencyKey'];assert re.fullmatch(r'[A-Za-z0-9:-]+',key)
    found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['id']=int(found);self.state['stage']='RecoveredExistingTask';self.save();print('Recovered existing task '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Submission outcome uncertain; inspect queue and original idempotency before retrying')
    resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(kind.lower()+'-resolved.json'),resolved)
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.state['stage']=kind+'SubmissionPrepared';self.save()
    result=self.api('/api/character-story/generate/'+kind,body);entry.update(id=result['id'],status='Pending');self.state['stage']=kind+'Queued';self.save();print(kind+' queued '+str(result['id']))
 def tick(self):
    for kind in ['Keyframe','Video','Preview']:
        entry=self.state.get(kind,{});
        if not entry.get('id'):continue
        detail=self.api('/api/tasks/'+str(entry['id']));write(OUT/(kind.lower()+'-task.json'),detail);entry['status']=detail['task']['status']
        if kind in ['Keyframe','Video']:
            shot=self.api('/api/character-story/shots/'+str(self.state['shotId']));record=next((t for t in shot['tasks'] if t['id']==entry['id']),None)
            if record and record.get('review'):entry['inspection']=record['review']
        if entry['status']=='Succeeded':
            extension='.png' if kind=='Keyframe' else '.mp4';asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').endswith(extension));entry.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
            if kind!='Preview':
                traceDir=DATA/f'CharacterStoryTrace/task_{entry["id"]}';receipt=traceDir/'submission.json'
                if receipt.exists():entry['comfyPromptId']=json.loads(receipt.read_text(encoding='utf-8'))['promptId']
        elif entry['status'] in ['Failed','Cancelled']:entry['failure']=detail['task'].get('errorMessage')
    self.save();print(json.dumps({k:{x:v for x,v in self.state[k].items() if x in ['id','status','sha256','failure','comfyPromptId']} for k in ['Keyframe','Video','Preview'] if self.state.get(k,{}).get('id')},ensure_ascii=False))
 def inspect(self,kind,decision,note):
    if decision not in ['Passed','Failed'] or not note:raise RuntimeError('Actual image/video inspection result and notes are required')
    entry=self.state[kind]
    if entry['status']!='Succeeded' or sha(DATA/entry['assetPath'])!=entry['sha256']:raise RuntimeError('Inspect the unchanged real output first')
    body=dict(taskId=entry['id'],scope='PreviewInspection',decision=decision,note=note,humanConfirmed=False,idempotencyKey=self.key('inspection-'+kind.lower()+'-'+str(uuid.uuid4())))
    entry['inspection']=self.api('/api/character-story/inspect',body);self.state['stage']=kind+'Inspected'+decision;self.save();print(kind+' PreviewInspection '+decision+'; final human review remains pending.')
 def repair(self,kind,note,adjustment):
    if self.state.get('completed'):raise RuntimeError('Completed plot is read-only')
    if not note or not adjustment:raise RuntimeError('Record the specific failure and changed prompt')
    self.preserve();old=self.state[kind];history=self.state.setdefault(kind+'History',[]);pending=self.state.get(kind+'RepairPending')
    if pending is None:
        if old.get('status')!='Failed' and old.get('inspection',{}).get('payload',{}).get('decision')!='Failed':raise RuntimeError('Only a recorded failed output can be repaired')
        attempt=len(history)+1
        if attempt>2:raise RuntimeError('Two targeted repairs exhausted; preserve evidence for review')
        body=dict(old['body'],planId=self.state['planId'],seed=old['body']['seed']+100,repairOfTaskId=old['id'],changeReason=note,promptAdjustment=adjustment,idempotencyKey=self.key(kind.lower()+'-repair-'+str(attempt)))
        pending=dict(body=body,repairAttempt=attempt);self.state[kind+'RepairPending']=pending;self.save()
    body=pending['body'];key=body['idempotencyKey'];assert re.fullmatch(r'[A-Za-z0-9:-]+',key)
    found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:pending['id']=int(found)
    elif pending.get('submissionIntentAt'):raise RuntimeError('Repair submission outcome uncertain; inspect queue before retrying')
    else:
        self.idle();resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(kind.lower()+'-repair'+str(pending['repairAttempt'])+'-resolved.json'),resolved)
        pending['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/character-story/generate/'+kind,body);pending['id']=result['id']
    pending['status']='Pending'
    if not any(h['id']==old['id'] for h in history):history.append(old)
    self.state[kind]=pending;self.state.pop(kind+'RepairPending',None);self.state['stage']=kind+'RepairQueued';self.save();print(kind+' targeted repair '+str(pending['repairAttempt'])+' queued '+str(pending['id']))
 def preview(self):
    v=self.state.get('Video',{});review=v.get('inspection',{}).get('payload',{})
    if v.get('status')!='Succeeded' or review.get('decision')!='Passed':raise RuntimeError('Inspect actual video before silent preview')
    entry=self.state.setdefault('Preview',{})
    if entry.get('id'):print('Existing preview task retained '+str(entry['id']));return
    body=dict(episodeId=self.state['episodeId'],taskIds=[v['id']],audioPath=None,idempotencyKey=self.key('preview'));entry['body']=body;self.save()
    key=body['idempotencyKey'];found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['id']=int(found);self.save();print('Existing preview recovered '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Preview submission outcome uncertain; inspect before retrying')
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/character-story/preview',body);entry.update(id=result['id'],status='Pending');self.state['stage']='PreviewQueued';self.save();print('Silent CPU review preview queued '+str(result['id']))

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','api-checks','keyframe','video','tick','inspect-keyframe','inspect-video','repair-keyframe','repair-video','preview']);p.add_argument('--decision',choices=['Passed','Failed']);p.add_argument('--note');p.add_argument('--prompt');a=p.parse_args()
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);r=Plot()
        if a.command=='prepare':r.prepare()
        elif a.command=='api-checks':r.api_checks()
        elif a.command in ['keyframe','video']:r.submit('Keyframe' if a.command=='keyframe' else 'Video')
        elif a.command.startswith('inspect'):r.inspect('Keyframe' if a.command=='inspect-keyframe' else 'Video',a.decision,a.note)
        elif a.command.startswith('repair'):r.repair('Keyframe' if a.command=='repair-keyframe' else 'Video',a.note,a.prompt)
        else:getattr(r,a.command)()
if __name__=='__main__':main()

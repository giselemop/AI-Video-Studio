"""Resumable two-actor/four-clip acceptance controller. Never auto-approves images.

prepare -> keyframe SLOT -> tick -> inspect SLOT --note ... -> video SLOT -> tick
Inspect the ACTUAL image before invoking inspect. Scope remains PreviewInspection.
This controller refuses to create work while migration010 is unavailable.
"""
from pathlib import Path
import argparse,json,uuid,requests,sys,msvcrt
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0,str(Path(__file__).parent))
from setup import OUT,DATA,ROOT,write,sha
SPECS=[
 dict(key='a-face',name='A人物面部',framing='closeUp',roles=['林安'],positions=['center'],refFraming='closeUp',action='Lin An looks calmly toward camera and makes one very small natural nod. Mouth stays closed.'),
 dict(key='a-body',name='A人物全身',framing='fullBody',roles=['林安'],positions=['center'],refFraming='fullBody',action='Lin An stands naturally, makes a subtle weight shift and a slight thirty degree torso turn. Feet remain on the floor, hands relaxed.'),
 dict(key='b-action',name='B人物简单动作',framing='medium',roles=['周言'],positions=['center'],refFraming='closeUp',action='Zhou Yan stands upright and gently nods once, hands relaxed. Mouth stays closed.'),
 dict(key='ab-frame',name='两人同框',framing='twoShot',roles=['林安','周言'],positions=['left','right'],refFraming='fullBody',action='Lin An on picture left and Zhou Yan on picture right stand half a meter apart. Both remain in their own places and exchange a small natural nod, with no crossing or contact.')]
SCENE='A quiet contemporary reading room with plain warm gray walls and softly lit bookshelves in the background. Soft even daylight. No other people.'
class Pilot:
 def __init__(self):
    self.path=OUT/'pilot.json';self.state=json.loads(self.path.read_text()) if self.path.exists() else dict(runId=str(uuid.uuid4()),stage='NotPrepared',actors=[dict(characterId=19,versionId=4),dict(characterId=20,versionId=5)],slots={},maxBaseClips=4,maxRepairsPerSlot=2,newModels=0,newCloudCalls=0)
    self.base='http://127.0.0.1:18080';self.s=requests.Session();a=self.api('/api/auth/status');assert a['accessMode']=='LocalOnly' and not a['loginRequired'];self.s.headers['X-CSRF-Token']=a['csrfToken']
    if not self.path.exists():self.save()
 def save(self):write(self.path,self.state)
 def api(self,path,body=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(path+' '+str(r.status_code)+' '+r.text[:700])
    return r.json()
 def ready(self):
    r=self.api('/api/character-story/readiness')
    if not r['ready']:
        self.state.update(stage='BlockedCharacterSchema',blocker=r,gpuSubmitted=sum(1 for slot in self.state['slots'].values() for kind in ['Keyframe','Video'] if slot.get(kind,{}).get('id')));self.save();raise RuntimeError(r['message'])
    if self.state.pop('blocker',None) is not None:self.save()
 def key(self,name):return 'story-pilot:'+self.state['runId']+':'+name
 def prepare(self):
    self.ready();name='人物剧情四片验收_'+self.state['runId'][:8]
    if not self.state.get('projectId'):
        old=next((p for p in self.api('/api/projects') if p['name']==name),None);self.state['projectId']=old['id'] if old else self.api('/api/projects',dict(name=name,description='Two original actors; four base review clips maximum. Static keyframes inspected first. NeedReview, publicationBlocked.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id'];self.save()
    pid=self.state['projectId']
    if not self.state.get('castId'):
        self.state['castId']=self.api(f'/api/character-story/projects/{pid}/cast',dict(roles=[dict(role='林安',versionId=4),dict(role='周言',versionId=5)],audioStrategy='PostDubbing',idempotencyKey=self.key('project-cast')))['id'];self.save()
    if not self.state.get('episodeId'):
        old=next((e for e in self.api(f'/api/projects/{pid}/episodes') if e['name']=='阅读室有限验收'),None);self.state['episodeId']=old['id'] if old else self.api('/api/episodes',dict(projectId=pid,name='阅读室有限验收',episodeNumber=1,outputWidth=864,outputHeight=480,outputFps=24,targetSeconds=124*4/24))['id'];self.save()
    eid=self.state['episodeId']
    if not self.state.get('episodeCastId'):self.state['episodeCastId']=self.api(f'/api/character-story/episodes/{eid}/cast',dict(idempotencyKey=self.key('episode-cast')))['id'];self.save()
    for i,spec in enumerate(SPECS):
        item=self.state['slots'].setdefault(spec['key'],{})
        if not item.get('shotId'):
            old=next((s for s in self.api(f'/api/episodes/{eid}/shots') if s['title']==spec['name']),None);item['shotId']=old['id'] if old else self.api('/api/shots',dict(projectId=pid,episodeId=eid,shotNumber=i+1,title=spec['name'],width=864,height=480,frames=124,fps=24,durationSeconds=124/24))['id'];self.save()
        if not item.get('planId'):
            actors=[dict(role=role,view='front',framing=spec['refFraming'],position=position,action=spec['action']) for role,position in zip(spec['roles'],spec['positions'])]
            item['planId']=self.api(f"/api/character-story/shots/{item['shotId']}",dict(episodeCastId=self.state['episodeCastId'],actors=actors,shotFraming=spec['framing'],scene=SCENE,action=spec['action'],camera='Eye-level locked camera. No pan, zoom or scene cut.',props='No handheld props; relaxed separated hands.',idempotencyKey=self.key('plan-'+spec['key'])))['id'];self.save()
    self.state['stage']='Prepared';self.save()
 def submit(self,slot,kind):
    self.ready();item=self.state['slots'][slot];entry=item.setdefault(kind,{})
    if entry.get('id'):print('Preserved existing task '+str(entry['id']));return
    index=next(i for i,s in enumerate(SPECS) if s['key']==slot)
    body=dict(planId=item['planId'],profile='baseline480',seed=2026102701+index,idempotencyKey=self.key(kind+'-'+slot))
    if kind=='Video':
        task=item['Keyframe'];inspection=task.get('inspection')
        if not inspection or inspection['payload']['decision']!='Passed':raise RuntimeError('Inspect actual static keyframe first; do not automatically continue')
        body.update(keyframeTaskId=task['id'],reviewId=inspection['id'])
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen acceptance request changed')
    entry['body']=body;self.save();resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(slot+'-'+kind+'-resolved.json'),resolved)
    result=self.api('/api/character-story/generate/'+kind,body);entry.update(id=result['id'],status='Pending');self.state['stage']=kind+'Queued';self.save();print(kind+' queued '+str(result['id']))
 def tick(self):
    for slot,item in self.state['slots'].items():
        shot=self.api('/api/character-story/shots/'+str(item['shotId']))
        for kind in ['Keyframe','Video']:
            record=item.get(kind)
            if not record or not record.get('id'):continue
            detail=self.api('/api/tasks/'+str(record['id']));record['status']=detail['task']['status'];write(OUT/(slot+'-'+kind+'-task.json'),detail)
            current=next((t for t in shot['tasks'] if t['id']==record['id']),None)
            if current and current.get('review'):record['inspection']=current['review']
            if record['status']=='Succeeded':
                result=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.png' if kind=='Keyframe' else '.mp4'));path=(DATA/result['assetPath']).resolve(strict=True)
                if not path.is_relative_to(DATA.resolve()):raise RuntimeError('Media path boundary')
                record.update(assetPath=result['assetPath'],sha256=sha(path))
        self.save()
    print(json.dumps(dict(stage=self.state['stage'],slots=self.state['slots']),ensure_ascii=False,indent=2))
 def inspect(self,slot,kind,note,decision):
    self.ready();record=self.state['slots'][slot][kind]
    if not note:raise RuntimeError('Actual visible identity, outfit, hands, pose and props inspection note required')
    record['inspection']=self.api('/api/character-story/inspect',dict(taskId=record['id'],scope='PreviewInspection',decision=decision,note=note,idempotencyKey=self.key('inspect-'+kind+'-'+slot+'-'+str(uuid.uuid4()))));self.save();print('PreviewInspection recorded; content remains NeedReview, publicationBlocked.')
 def repair(self,slot,kind,note,adjustment):
    self.ready();item=self.state['slots'][slot];old=item[kind];history=item.setdefault(kind+'History',[])
    if not note or not adjustment:raise RuntimeError('Targeted repair requires failure reason and actual changed prompt')
    pending=item.get(kind+'RepairPending')
    if pending is None:
        if old.get('status')!='Failed' and old.get('inspection',{}).get('payload',{}).get('decision')!='Failed':raise RuntimeError('Inspect the actual failed output before repair')
        attempt=len(history)+1
        if attempt>2:raise RuntimeError('Two targeted repairs exhausted; keep failure and block this clip')
        body=dict(old['body'],seed=old['body']['seed']+100,repairOfTaskId=old['id'],changeReason=note,promptAdjustment=adjustment,idempotencyKey=self.key(kind+'-'+slot+'-repair-'+str(attempt)))
        pending=dict(body=body,repairAttempt=attempt);item[kind+'RepairPending']=pending;self.save()
    body=pending['body'];resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(slot+'-'+kind+'-repair'+str(pending['repairAttempt'])+'-resolved.json'),resolved)
    result=self.api('/api/character-story/generate/'+kind,body);pending.update(id=result['id'],status='Pending')
    if not any(h['id']==old['id'] for h in history):history.append(old)
    item[kind]=pending;item.pop(kind+'RepairPending',None);self.state['stage']=kind+'RepairQueued';self.save();print(kind+' targeted repair queued '+str(result['id']))
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','keyframe','video','tick','inspect','inspect-video','repair-keyframe','repair-video']);p.add_argument('--slot',choices=[s['key'] for s in SPECS]);p.add_argument('--note');p.add_argument('--prompt');p.add_argument('--decision',choices=['Passed','Failed','NeedReview'],default='NeedReview');a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'pilot-controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        r=Pilot()
        if a.command=='prepare':r.prepare()
        elif a.command=='tick':r.tick()
        elif a.command.startswith('inspect'):r.inspect(a.slot,'Video' if a.command=='inspect-video' else 'Keyframe',a.note,a.decision)
        elif a.command.startswith('repair'):r.repair(a.slot,'Video' if a.command=='repair-video' else 'Keyframe',a.note,a.prompt)
        else:r.submit(a.slot,'Keyframe' if a.command=='keyframe' else 'Video')
if __name__=='__main__':main()

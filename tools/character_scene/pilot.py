"""Two actors, one fixed room, four new real keyframes before any video.

Every base/repair request is checkpointed before submission. Inspection is
explicit PreviewInspection; this controller never signs human approval.
"""
from pathlib import Path
import sys,json,requests,argparse,msvcrt,uuid
sys.path.insert(0,str(Path(__file__).parent))
from common import ROOT,DATA,OUT,sha,write

SCENE='The same reading room as the frozen composition: rear wooden bookcases beneath a plain warm gray wall, the same bookshelf divisions and existing books, white outlet below the central gap, nearer bookcases flanking both edges, soft even warm daylight. Keep all room geometry, perspective and book arrangements fixed.'
CAMERA='Eye-level locked camera, identical framing and fixed screen positions. No camera motion, zoom, crop or scene cut.'
REGIONS=[dict(side='left',x=300,y=50,width=420,height=814,feather=32),dict(side='right',x=820,y=8,width=430,height=856,feather=32)]
REPAIR_REGIONS=[dict(side='left',x=270,y=32,width=480,height=832,feather=32),dict(side='right',x=770,y=0,width=500,height=864,feather=32)]
SPECS=[
 dict(key='search',name='寻找书架',views=['threeQuarterLeft','front'],start='Lin An on the left has just noticed the bookshelf at picture LEFT; she looks gently toward that shelf. Zhou Yan on the right remains relaxed and faces almost forward.',action='Lin An makes one small calm head turn toward the bookshelf at picture LEFT and holds the gaze. Zhou Yan remains still. Both mouths stay closed, arms stay down.'),
 dict(key='notice',name='共同注意',views=['threeQuarterLeft','threeQuarterLeft'],start='Lin An on the left continues looking toward the same picture-LEFT shelf. Zhou Yan on the right has also gently turned his eyes and head toward that same shelf, following her gaze.',action='Zhou Yan makes one small head turn toward the same picture-LEFT bookshelf, following Lin An gaze, then pauses. Lin An remains still. Mouths closed, hands stay down.'),
 dict(key='confirm',name='相互确认',views=['threeQuarterRight','threeQuarterLeft'],start='Lin An on the left has turned slightly toward Zhou Yan on her right. Zhou Yan on the right looks slightly left toward Lin An. They calmly make eye contact without moving their bodies or hands.',action='Lin An and Zhou Yan exchange one small natural eye-contact response and a subtle acknowledging nod. Faces stay calm and mouths closed; no speech, no hand gestures or body crossing.'),
 dict(key='respond',name='点头回应',views=['threeQuarterRight','threeQuarterLeft'],start='Lin An on the left and Zhou Yan on the right face slightly toward each other with a calm friendly expression. Both hold a neutral starting head angle, ready for a small acknowledging nod.',action='Zhou Yan gives one very small acknowledging nod to Lin An. Lin An responds with a restrained warm expression. Then both hold their pose. Mouths stay closed, no speaking, hands stay relaxed at their sides.')]

class Pilot:
 def __init__(self):
    self.path=OUT/'run.json';self.state=json.loads(self.path.read_text(encoding='utf-8'));self.base='http://127.0.0.1:18080';self.s=requests.Session();auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];self.s.headers['X-CSRF-Token']=auth['csrfToken']
 def save(self):write(self.path,self.state)
 def key(self,label):return 'character-scene:'+self.state['runId']+':'+label
 def require_generation_allowed(self):
    if self.state.get('generationHold',{}).get('active'):
        raise RuntimeError('User requested 保持待审; no new image or video task may be submitted until explicitly resumed with reviewed actor versions. Existing outputs remain readable.')
 def api(self,path,body=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP'+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def prepare(self):
    assert not self.state['completed'],'Completed run is read-only; do not prepare another generation'
    assert self.api('/api/character-story/readiness')['ready']
    name='阅读室找书_场景连续性_'+self.state['runId'][:8]
    if not self.state.get('projectId'):
        old=next((p for p in self.api('/api/projects') if p['name']==name),None);self.state['projectId']=old['id'] if old else self.api('/api/projects',dict(name=name,description='Two original actors, one fixed room, four new keyframes before H3. ReviewPreview, final content NeedReview.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id'];self.save()
    pid=self.state['projectId']
    if not self.state.get('castId'):self.state['castId']=self.api(f'/api/character-story/projects/{pid}/cast',dict(roles=[dict(role='林安',versionId=4),dict(role='周言',versionId=5)],audioStrategy='PostDubbing',idempotencyKey=self.key('cast')))['id'];self.save()
    if not self.state.get('episodeId'):
        old=next((e for e in self.api(f'/api/projects/{pid}/episodes') if e['name']=='阅读室·找到要看的书'),None);self.state['episodeId']=old['id'] if old else self.api('/api/episodes',dict(projectId=pid,name='阅读室·找到要看的书',episodeNumber=1,outputWidth=864,outputHeight=480,outputFps=24,targetSeconds=496/24))['id'];self.save()
    eid=self.state['episodeId']
    if not self.state.get('episodeCastId'):self.state['episodeCastId']=self.api(f'/api/character-story/episodes/{eid}/cast',dict(idempotencyKey=self.key('episode-cast')))['id'];self.save()
    original=json.loads((DATA/'CharacterStory20261027/pilot.json').read_text(encoding='utf-8'));source=original['slots']['ab-frame']['Keyframe'];assert source['id']==1514 and sha(DATA/source['assetPath'])==source['sha256']
    if not self.state.get('sceneId'):
        old=next((s for s in self.api(f'/api/scenes?projectId={pid}') if s['name']=='固定阅读室构图'),None)
        self.state['sceneId']=old['id'] if old else self.api('/api/scenes',dict(projectId=pid,name='固定阅读室构图',description=SCENE,fixedPrompt=SCENE,anchorPath=source['assetPath'],style='Photorealistic fixed-camera medium two-shot',metadata=dict(sourceTaskId=1514,purpose='Scene composition including the same two actors; not an empty-room asset',contentReview='NeedReview')))['id'];self.save()
    if not self.state.get('sceneVersionId'):
        result=self.api(f'/api/character-story/scenes/{self.state["sceneId"]}/capture',dict(sourceTaskId=1514,description=SCENE,regions=REGIONS,idempotencyKey=self.key('scene-version')));self.state['sceneVersionId']=result['id'];self.state['sceneVersionSha256']=result['sha256'];self.save();write(OUT/'scene-version.json',result)
    for i,spec in enumerate(SPECS):
        item=self.state['slots'].setdefault(spec['key'],dict(label=spec['name']))
        if not item.get('shotId'):
            old=next((s for s in self.api(f'/api/episodes/{eid}/shots') if s['title']==spec['name']),None);item['shotId']=old['id'] if old else self.api('/api/shots',dict(projectId=pid,episodeId=eid,shotNumber=i+1,title=spec['name'],width=864,height=480,frames=124,fps=24,durationSeconds=124/24))['id'];self.save()
        if not item.get('planId'):
            body=dict(episodeCastId=self.state['episodeCastId'],sceneVersionId=self.state['sceneVersionId'],shotFraming='twoShot',scene=SCENE,action=spec['action'],camera=CAMERA,props='Existing books remain on their shelves. No handheld prop or handoff; both hands remain relaxed at the sides.',actors=[dict(role=role,view=view,framing='fullBody',position=pos,action=spec['start']) for role,view,pos in zip(['林安','周言'],spec['views'],['left','right'])],idempotencyKey=self.key('plan-'+spec['key']))
            record=self.api(f'/api/character-story/shots/{item["shotId"]}',body);item.update(planId=record['id'],planSha256=record['sha256'],planBody=body);self.save()
    self.state['stage']='Prepared';self.save();print('Four original Shot plans pinned to one frozen scene and actor versions4/5.')
 def revise_failed_scene(self,note):
    if not note:raise RuntimeError('Explicit diagnosed reason required for scene revision')
    if not self.state.get('repairSceneVersionId'):
        result=self.api(f'/api/character-story/scenes/{self.state["sceneId"]}/capture',dict(sourceTaskId=1514,description=SCENE,regions=REPAIR_REGIONS,workflowVersion='character-scene-klein4b-five-masked-locked-1536-v1',idempotencyKey=self.key('scene-pose-repair-version')))
        self.state.update(repairSceneVersionId=result['id'],repairSceneVersionSha256=result['sha256'],sceneRepairReason=note);self.save();write(OUT/'scene-repair-version.json',result)
    for slot,item in self.state['slots'].items():
        if item['Keyframe'].get('inspection',{}).get('payload',{}).get('decision')!='Failed':continue
        if item.get('revisedSceneVersionId')==self.state['repairSceneVersionId']:continue
        body=dict(item['planBody'],sceneVersionId=self.state['repairSceneVersionId'],idempotencyKey=self.key('scene-pose-repair-plan-'+slot))
        record=self.api('/api/character-story/shots/'+str(item['shotId']),body)
        item.setdefault('PlanHistory',[]).append(dict(id=item['planId'],sha256=item['planSha256'],body=item['planBody'],changeReason=note))
        item.update(planId=record['id'],planSha256=record['sha256'],planBody=body,revisedSceneVersionId=self.state['repairSceneVersionId']);self.save()
    self.state.update(stage='FailedScenePlansRevised',staticContinuityPassed=False);self.save();print('Only failed Shot plans revised; original source image, old scene/plan versions and per-Shot repair budget retained.')
 def submit(self,slot,kind):
    if self.state['completed']:raise RuntimeError('Run completed; inspect existing outputs instead of resubmitting')
    item=self.state['slots'][slot];entry=item.setdefault(kind,{})
    if entry.get('id'):print('Preserved existing '+kind+' task '+str(entry['id']));return
    self.require_generation_allowed()
    if kind=='Video':
        if not all(v.get('Keyframe',{}).get('inspection',{}).get('payload',{}).get('decision')=='Passed' for v in self.state['slots'].values()):raise RuntimeError('Inspect ALL four static frames and cross-frame continuity before any H3 video')
        if not self.state.get('staticContinuityPassed'):raise RuntimeError('Explicit four-frame continuity inspection required')
    index=next(i for i,s in enumerate(SPECS) if s['key']==slot);body=dict(planId=item['planId'],profile=self.state['profile'],seed=2026102731+index,idempotencyKey=self.key(kind+'-'+slot))
    if kind=='Video':body.update(keyframeTaskId=item['Keyframe']['id'],reviewId=item['Keyframe']['inspection']['id'])
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen request differs')
    entry['body']=body;self.save();resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(slot+'-'+kind+'-resolved.json'),resolved)
    result=self.api('/api/character-story/generate/'+kind,body);entry.update(id=result['id'],status='Pending');self.state['stage']=kind+'Queued';self.save();print(kind+' queued '+str(result['id']))
 def tick(self):
    for slot,item in self.state['slots'].items():
        context=self.api('/api/character-story/shots/'+str(item['shotId']))
        for kind in ['Keyframe','Video']:
            entry=item.get(kind,{})
            if not entry.get('id'):continue
            detail=self.api('/api/tasks/'+str(entry['id']));entry['status']=detail['task']['status'];write(OUT/(slot+'-'+kind+'-task.json'),detail)
            record=next((t for t in context['tasks'] if t['id']==entry['id']),None)
            if record and record.get('review'):entry['inspection']=record['review']
            if entry['status']=='Succeeded':
                asset=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.png' if kind=='Keyframe' else '.mp4'));entry.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
    self.save();print([(k,{t:v[t]['status'] for t in ['Keyframe','Video'] if v.get(t,{}).get('id')}) for k,v in self.state['slots'].items()])
 def inspect(self,slot,kind,decision,note):
    if not note:raise RuntimeError('Actual image/video inspection notes required')
    entry=self.state['slots'][slot][kind];entry['inspection']=self.api('/api/character-story/inspect',dict(taskId=entry['id'],decision=decision,scope='PreviewInspection',humanConfirmed=False,note=note,idempotencyKey=self.key('inspection-'+str(entry['id'])+'-'+str(uuid.uuid4()))));self.save();print('PreviewInspection '+decision+'; final human content remains NeedReview.')
 def repair(self,slot,kind,note,prompt):
    self.require_generation_allowed()
    item=self.state['slots'][slot];old=item[kind];history=item.setdefault(kind+'History',[])
    if not note or not prompt:raise RuntimeError('Targeted failure reason and changed prompt required')
    pending=item.get(kind+'RepairPending')
    if pending is None:
        if old['status']!='Failed' and old.get('inspection',{}).get('payload',{}).get('decision')!='Failed':raise RuntimeError('Record actual failure before repair')
        attempt=len(history)+1
        if attempt>2:raise RuntimeError('Two targeted repairs exhausted; retain failure evidence')
        pending=dict(body=dict(old['body'],planId=item['planId'],seed=old['body']['seed']+100,repairOfTaskId=old['id'],changeReason=note,promptAdjustment=prompt,idempotencyKey=self.key(kind+'-'+slot+'-repair-'+str(attempt))),repairAttempt=attempt);item[kind+'RepairPending']=pending;self.save()
    body=pending['body'];resolved=self.api('/api/character-story/resolve/'+kind,body);write(OUT/(slot+'-'+kind+'-repair'+str(pending['repairAttempt'])+'-resolved.json'),resolved);result=self.api('/api/character-story/generate/'+kind,body)
    pending.update(id=result['id'],status='Pending');history.append(old);item[kind]=pending;item.pop(kind+'RepairPending',None);self.state['stage']=kind+'RepairQueued';self.state['staticContinuityPassed']=False if kind=='Keyframe' else self.state.get('staticContinuityPassed',False);self.save();print('Targeted '+kind+' repair queued '+str(result['id']))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','keyframe','video','tick','inspect','inspect-video','repair-keyframe','repair-video','continuity','revise-scene']);parser.add_argument('--slot',choices=[s['key'] for s in SPECS]);parser.add_argument('--note');parser.add_argument('--prompt');parser.add_argument('--decision',choices=['Passed','Failed','NeedReview'],default='NeedReview');a=parser.parse_args()
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);p=Pilot()
        if a.command=='prepare':p.prepare()
        elif a.command=='revise-scene':p.revise_failed_scene(a.note)
        elif a.command=='tick':p.tick()
        elif a.command=='continuity':
            assert a.note and all(v.get('Keyframe',{}).get('inspection',{}).get('payload',{}).get('decision')=='Passed' for v in p.state['slots'].values());p.state.update(staticContinuityPassed=a.decision=='Passed',staticContinuityNote=a.note);p.save();print('Cross-frame static inspection recorded: '+a.decision)
        elif a.command.startswith('inspect'):p.inspect(a.slot,'Video' if a.command.endswith('video') else 'Keyframe',a.decision,a.note)
        elif a.command.startswith('repair'):p.repair(a.slot,'Video' if a.command.endswith('video') else 'Keyframe',a.note,a.prompt)
        else:p.submit(a.slot,'Keyframe' if a.command=='keyframe' else 'Video')
if __name__=='__main__':main()

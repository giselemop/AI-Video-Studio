"""Bounded, resumable repair controller. Real Studio tasks, no auto-approvals."""
import argparse, copy, datetime, sys, time, uuid
from pathlib import Path
import requests
from PIL import Image
from inventory import ROOT, DATA, OUT, read, write, sha, media
sys.path.insert(0,str(ROOT/'tools'))
from character_prompt_policy import POLICY, SLOTS, compose

BASE='http://127.0.0.1:18080'
KEYS={19:'linan',20:'zhouyan',21:'xuzhixia',22:'chenyu',23:'suwanqing',24:'zhaomingyuan',25:'shenyulan'}

class Repair:
 def __init__(self):
    self.s=requests.Session();a=self.api('/api/auth/status')
    if a.get('loginRequired') or a.get('accessMode')!='LocalOnly':raise RuntimeError('Existing human login required')
    self.s.headers['X-CSRF-Token']=a['csrfToken']
    exists=(OUT/'run.json').exists()
    self.state=read(OUT/'run.json') if exists else dict(runId=str(uuid.uuid4()),tasks={},completed=False)
    self.before=read(OUT/'inventory-before.json')
    if not exists:self.save()
 def save(self):write(OUT/'run.json',self.state)
 def api(self,path,body=None,method=None):
    r=self.s.request(method or ('POST' if body is not None else 'GET'),BASE+path,json=body,timeout=120)
    if not r.ok:raise RuntimeError(f'{path} HTTP {r.status_code}: {r.text[:700]}')
    return r.json()
 def source(self,cid,view,framing):
    c=next(x for x in self.before['characters'] if x['character']['id']==cid)
    if cid in (19,20):
        v=next(v for v in self.before['versions'] if v['id']==(4 if cid==19 else 5))
        rid=next(r['referenceId'] for r in v['payload']['references'] if r['view']==view and r['framing']==framing)
        return next(r for r in c['references'] if r['id']==rid)
    return next((r for r in c['references'] if r['kind']==view+'-'+framing),None)
 def body(self,cid,view,framing,attempt,adjustment):
    c=self.api('/api/character-workshop/'+str(cid))['character']
    identity=self.source(cid,'front','closeUp');outfit=self.source(cid,'front','fullBody')
    directed=view in ('threeQuarterLeft','threeQuarterRight') and (attempt==2 or self.source(cid,view,'closeUp') is not None)
    if directed:identity=self.source(cid,view,'closeUp')
    if not identity or identity['reviewStatus']=='Rejected':raise RuntimeError('No usable identity')
    inputs={'firstFrame':identity['assetPath']};sourceRefs=[identity]
    # Rejected front-body references never feed new tasks. Derive a new wardrobe master from identity instead.
    if view!='front' and framing=='fullBody' and not directed:
        new=self.state['tasks'].get(f'{cid}-front-fullBody-a1')
        if new and new.get('visualStatus')=='Passed':inputs['wardrobeReference']=new['path']
        elif outfit and outfit['reviewStatus']!='Rejected':inputs['wardrobeReference']=outfit['assetPath'];sourceRefs.append(outfit)
        else:raise RuntimeError('Inspect repaired wardrobe master before dependent repair')
    workflows=self.api('/api/workflows');dual=len(inputs)==2
    workflow=next(w for w in workflows if w['name']=='character_pack_klein4b_'+('dual' if dual else 'single')+'_api')
    traits=c.get('fixedPrompt','')+f" Face: {c.get('faceFeatures','')}. Hair: {c.get('hair','')}. Age: {c.get('ageSetting','')}."
    metadata=__import__('json').loads(c.get('metadataJson') or '{}');extra=metadata.get('referenceStudio',{})
    clothing=(c.get('clothes') or '')+'. Shoes: '+extra.get('shoes','match established shoes')
    proportions=c.get('bodyRatio') or 'natural adult proportions'
    if cid in (19,20):
        version=next(v['payload'] for v in self.before['versions'] if v['id']==(4 if cid==19 else 5))
        clothing=version['outfit'];proportions=version.get('bodyRatio') or proportions
    prompt=compose(view,framing,len(inputs),traits,clothing,proportions)
    if adjustment:prompt='Target view, highest priority: '+POLICY['directions'][view]+' '+prompt+' Targeted correction: '+adjustment
    for r in sourceRefs:
        if sha(media(r['assetPath']))!=r['actualSha256']:raise RuntimeError('Source changed')
    source=self.source(cid,view,framing)
    return dict(projectId=c['projectId'],taskType='Image',workflowId=workflow['id'],inputImagePath=inputs['firstFrame'],maxRetries=0,resourceClass='GPU',stage='Character-Anatomy-Repair',
        parameters=dict(workflowVersion='character-pack-klein4b-'+('dual' if dual else 'single')+'-1536-v1',positive=prompt,negative='',inputSlots=inputs,
            seed=202610270000+cid*100+SLOTS.index((view,framing))*10+attempt,width=1536,height=864,steps=4,cfg=1,
            promptPolicy=POLICY['version'],contentReview='NeedReview',characterReferenceRepair=dict(characterId=cid,view=view,framing=framing,attempt=attempt,
            sourceReferenceId=source['id'] if source else None,inputSha256={p:sha(media(p)) for p in inputs.values()},reason=adjustment)))
 def submit(self,cid,view,framing,attempt,reason):
    if self.state['completed']:raise RuntimeError('Completed state is read-only')
    if attempt not in (1,2) or not reason.strip():raise ValueError('Two bounded, reasoned repair attempts only')
    key=f'{cid}-{view}-{framing}-a{attempt}';entry=self.state['tasks'].get(key)
    if entry and entry.get('id'):print(key,entry['id'],'already registered; use tick',flush=True);return
    previous=self.state['tasks'].get(f'{cid}-{view}-{framing}-a1')
    if attempt==2 and (not previous or previous.get('visualStatus')!='Failed'):raise RuntimeError('Inspect and fail attempt one first')
    if not entry:
        body=self.body(cid,view,framing,attempt,reason);body['idempotencyKey']='character-anatomy:'+self.state['runId']+':'+key
        entry=dict(body=body,reason=reason,visualStatus='NeedReview');self.state['tasks'][key]=entry;self.save()
    q=self.s.get('http://127.0.0.1:8188/queue',timeout=20).json()
    if len(q['queue_running'])>1:raise RuntimeError('GPU concurrency violation')
    entry['id']=self.api('/api/tasks',entry['body'])['id'];self.save();print(key,entry['id'],'registered',flush=True)
 def tick(self):
    samples=self.state.setdefault('resourceSamples',[]);q=self.s.get('http://127.0.0.1:8188/queue',timeout=20).json();stats=self.s.get('http://127.0.0.1:8188/system_stats',timeout=20).json();d=stats['devices'][0]
    if len(q['queue_running'])>1:raise RuntimeError('GPU concurrency violation')
    samples.append(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),running=len(q['queue_running']),pending=len(q['queue_pending']),gpu=d['name'],freeMiB=d['vram_free']//1048576,totalMiB=d['vram_total']//1048576))
    for key,e in self.state['tasks'].items():
        if not e.get('id'):continue
        detail=self.api('/api/tasks/'+str(e['id']));e['status']=detail['task']['status']
        if e['status']=='Succeeded':
            r=next(r for r in detail['results'] if r.get('available') and r['assetPath'].endswith('.png'));e.update(path=r['assetPath'],sha256=sha(media(r['assetPath'])))
            with Image.open(media(e['path'])) as im:
                im.verify()
            write(OUT/'receipts'/f'{key}-task.json',detail)
        print(key,e['id'],e['status'],e.get('visualStatus'),flush=True)
    self.save()
 def inspect(self,key,status,note):
    e=self.state['tasks'][key]
    if e.get('status')!='Succeeded' or status not in ('Passed','Failed') or not note:raise ValueError('Completed output and a concrete inspection note required')
    e.update(visualStatus=status,inspection=dict(reviewer='assistant-visual-inspection',note=note,contentReview='NeedReview',humanApproval=False));self.save()
 def collect(self,key):
    e=self.state['tasks'][key];m=e['body']['parameters']['characterReferenceRepair'];cid=m['characterId']
    if e.get('visualStatus')!='Passed':raise RuntimeError('Inspect candidate before collection')
    if sha(media(e['path']))!=e['sha256']:raise RuntimeError('Output changed')
    reason=f"character-anatomy-v2; task={e['id']}; sourceRef={m['sourceReferenceId']}; {e['reason'][:340]}; assistant inspection, human review pending. Full reason in original task."
    result=self.api(f'/api/character-workshop/{cid}/collect',dict(taskId=e['id'],view=m['view'],framing=m['framing'],changeReason=reason))
    e['referenceId']=result['id'];self.save();print(key,'candidate reference',e['referenceId'])

if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('submit');a.add_argument('cid',type=int);a.add_argument('view');a.add_argument('framing');a.add_argument('--attempt',type=int,default=1);a.add_argument('--reason',required=True)
 sub.add_parser('tick');a=sub.add_parser('inspect');a.add_argument('key');a.add_argument('status');a.add_argument('note');a=sub.add_parser('collect');a.add_argument('key')
 a=p.parse_args();r=Repair()
 if a.command=='submit':r.submit(a.cid,a.view,a.framing,a.attempt,a.reason)
 elif a.command=='tick':r.tick()
 elif a.command=='inspect':r.inspect(a.key,a.status,a.note)
 elif a.command=='collect':r.collect(a.key)

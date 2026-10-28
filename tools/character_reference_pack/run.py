"""Resumable nine-reference packs for the two existing fictional characters."""
from __future__ import annotations
import argparse
import copy
import json
import importlib.util
from pathlib import Path
import sys
import time
import uuid
import requests

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'CharacterReferencePack20261026'
sys.path.insert(0,str(ROOT/'tools/character_library'))
from run_acceptance import read,write,sha,media
sys.path.insert(0,str(ROOT/'tools'))
from character_prompt_policy import compose, POLICY

PEOPLE=[
 dict(key='linan',name='林安',characterId=19,identityVersionId=1,outfit='ivory crew-neck knit sweater, straight-leg charcoal trousers, plain white low-top sneakers',body='natural realistic adult female proportions, consistent slim build, realistic hands and limbs'),
 dict(key='zhouyan',name='周言',characterId=20,identityVersionId=2,outfit='navy blue long-sleeve button-down shirt, straight-leg beige trousers, plain dark brown lace-up shoes',body='natural realistic adult male proportions, consistent medium build, realistic hands and limbs')
]
SLOTS=[('front','closeUp'),('threeQuarterLeft','closeUp'),('threeQuarterRight','closeUp'),('front','fullBody'),('threeQuarterLeft','fullBody'),('left','fullBody'),('back','fullBody'),('right','fullBody'),('threeQuarterRight','fullBody')]
class Run:
 def __init__(self,base='http://127.0.0.1:18080'):
    self.base=base;self.session=requests.Session()
    self.state=read(FOLDER/'run.json') if (FOLDER/'run.json').exists() else dict(runId=str(uuid.uuid4()),stage='Created',tasks={},people={})
 def save(self,**values):self.state.update(values);write(FOLDER/'run.json',self.state)
 def selected_key(self,key):
    return read(FOLDER/'selection.json').get(key,key) if (FOLDER/'selection.json').exists() else key
 def archive_receipt(self,key,record,detail):
    write(FOLDER/(key+'-task.json'),detail)
    spec=importlib.util.spec_from_file_location('library_delivery_helpers',ROOT/'tools/character_library/verify_delivery.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    trace=helper.database_traces([record['id']])[0]
    write(FOLDER/(key+'-trace.json'),trace)
    if trace.get('comfyPromptId'):
        history=self.session.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30)
        history.raise_for_status()
        payload=history.json()
        if trace['comfyPromptId'] not in payload:raise RuntimeError('Archive Comfy receipt before continuing to another task')
        write(FOLDER/(key+'-comfy-history.json'),payload)
 def api(self,path,body=None,method=None,key=None):
    response=self.session.request(method or ('POST' if body is not None else 'GET'),self.base+path,json=body,headers={'Idempotency-Key':key} if key else {},timeout=150)
    if not response.ok:raise RuntimeError(f'{path}: HTTP {response.status_code}: {response.text[:1000]}')
    return response.json()
 def access(self):
    status=self.api('/api/auth/status')
    if status.get('loginRequired',True) or status.get('accessMode')!='LocalOnly':raise RuntimeError('Existing LocalOnly authorization required; login is never bypassed')
    self.session.headers['X-CSRF-Token']=status['csrfToken']
 def preserve(self):
    for item in self.state.get('originalVersions',[]):
        version=next((v for v in self.api('/api/character-library')['versions'] if v['id']==item['id']),None)
        if not version or version['sha256']!=item['sha256']:raise RuntimeError('Original immutable library version changed')
    for record in self.state['tasks'].values():
        if record.get('sha256') and sha(media(record['path']))!=record['sha256']:raise RuntimeError('Frozen pack artifact changed')
    for person in self.state['people'].values():
        if person.get('identityPath') and sha(media(person['identityPath']))!=person['identitySha256']:raise RuntimeError('Original face anchor changed')
 def once(self,key,body,endpoint='/api/tasks'):
    record=self.state['tasks'].setdefault(key,{})
    frozen=dict(body,idempotencyKey='reference-pack:'+self.state['runId']+':'+key)
    if record.get('body') and record['body']!=frozen:raise RuntimeError('Task intent changed: '+key)
    if not record.get('body'):record['body']=frozen;self.save()
    if not record.get('id'):
        result=self.api(endpoint,frozen,key=frozen['idempotencyKey']);record['id']=result['id'];self.save()
    last=None;deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        detail=self.api('/api/tasks/'+str(record['id']));status=detail['task']['status']
        if last!=status:print(key,record['id'],status,flush=True);last=status
        if status=='Succeeded':
            result=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith(('.png','.mp4')))
            record.update(path=result['assetPath'],sha256=sha(media(result['assetPath'])),status=status)
            self.save();self.archive_receipt(key,record,detail);return record
        if status in ['Failed','Cancelled']:
            record.update(status=status,errorMessage=detail['task'].get('errorMessage'));self.save();write(FOLDER/(key+'-task.json'),detail)
            raise RuntimeError(f"Task {record['id']} {status}: "+str(detail['task'].get('errorMessage',''))[:900])
        time.sleep(3)
    raise RuntimeError('Recorded task remains unresolved; do not resubmit with a new key')
 def prepare(self):
    self.access()
    names={w['name'] for w in self.api('/api/workflows')}
    if not {'character_pack_klein4b_single_api','character_pack_klein4b_dual_api'}.issubset(names):
        self.api('/api/workflows/scan',{})
    if not self.state.get('originalVersions'):
        versions=self.api('/api/character-library')['versions'];self.save(originalVersions=versions,localOnly=True,newModels=0,newCloudCalls=0,gpuConcurrency=1)
    self.preserve()
    if not self.state.get('projectId'):
        name='人物九图参考包_'+self.state['runId'][:8]
        existing=next((p for p in self.api('/api/projects') if p['name']==name),None)
        pid=existing['id'] if existing else self.api('/api/projects',dict(name=name,description='Two existing characters, 3 face close-ups + 6 full-body references each; view and framing are separate immutable bindings.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id']
        self.save(projectId=pid)
    for person in PEOPLE:
        if person['key'] not in self.state['people']:
            version=next(v for v in self.state['originalVersions'] if v['id']==person['identityVersionId'])
            anchor=next(r for r in version['payload']['references'] if r['view']=='front')
            self.state['people'][person['key']]=dict(characterId=person['characterId'],identityPath=anchor['assetPath'],identitySha256=anchor['sha256'],sourceVersionId=version['id'],outfit=person['outfit'],bodyDescription=person['body'])
            self.save()
    self.save(stage='Prepared')
 def image_body(self,person,view,framing):
    frozen=self.state['tasks'].get(person['key']+'-'+view+'-'+framing,{}).get('body')
    if frozen:return copy.deepcopy(frozen)
    identity=self.state['people'][person['key']]['identityPath'];dual=framing=='fullBody' and view!='front'
    workflow_name='character_pack_klein4b_dual_api' if dual else 'character_pack_klein4b_single_api'
    workflow=next(w for w in self.api('/api/workflows') if w['name']==workflow_name)
    slots=dict(firstFrame=identity)
    if dual:slots['wardrobeReference']=self.state['tasks'][person['key']+'-front-fullBody']['path']
    prompt=compose(view,framing,len(slots),'Preserve the exact adult identity from image1.',person['outfit'] if framing=='fullBody' else 'Match only the collar and upper garment visible in image1.',person['body'])
    seed=2026102700+PEOPLE.index(person)*20+SLOTS.index((view,framing))
    return dict(projectId=self.state['projectId'],taskType='Keyframe',workflowId=workflow['id'],inputImagePath=identity,stage='Character-Pack-'+view+'-'+framing,maxRetries=0,parameters=dict(promptPolicy=POLICY['version'],workflowVersion='character-pack-klein4b-'+('dual' if dual else 'single')+'-1536-v1',inputSlots=slots,positive=prompt,seed=seed,width=1536,height=864,steps=4,cfg=1))
 def masters(self):
    self.prepare()
    for person in PEOPLE:self.once(person['key']+'-front-fullBody',self.image_body(person,'front','fullBody'))
    self.save(stage='AwaitingMasterInspection')
 def references(self):
    self.access();self.preserve()
    if read(FOLDER/'masters-review.json').get('status')!='Passed':raise RuntimeError('Full-body masters need actual inspection first')
    for person in PEOPLE:
        for view,framing in SLOTS:
            if view=='front' and framing=='fullBody':continue
            self.once(person['key']+'-'+view+'-'+framing,self.image_body(person,view,framing))
    self.save(stage='AwaitingPackInspection')
 def populate(self):
    self.access();self.preserve()
    if read(FOLDER/'references-review.json').get('status')!='Passed':raise RuntimeError('All selected reference views must be inspected first')
    for person in PEOPLE:
        entry=self.state['people'][person['key']];refs=[]
        for view,framing in SLOTS:
            key=person['key']+'-'+view+'-'+framing;record=self.state['tasks'][self.selected_key(key)];field=view+'-'+framing
            if field not in entry:
                reason=self.state['runId']+'|'+view+'|'+framing
                existing=next((ref for ref in self.api(f"/api/characters/{entry['characterId']}/references") if ref.get('changeReason')==reason),None)
                if existing:reference_id=existing['id']
                else:
                    p=media(record['path'])
                    with p.open('rb') as stream:
                        response=self.session.post(self.base+f"/api/characters/{entry['characterId']}/references",files={'file':(p.name,stream,'image/png')},data=dict(kind='identity',isAnchor='false',stage='reference-pack-v2',role='identity',changeReason=reason),timeout=120)
                    if not response.ok:raise RuntimeError('Upload rejected: '+response.text[:500])
                    reference_id=response.json()['id']
                entry[field]=reference_id;self.save()
            refs.append(dict(referenceId=entry[field],view=view,framing=framing))
        workflow=next(w for w in self.api('/api/workflows') if w['name']=='minimax_h3_local_i2v_api')
        body=dict(label='日常造型 · 九图参考包',outfit=person['outfit'],bodyDescription=person['body'],profile='baseline480',workflowId=workflow['id'],references=refs,referencePack='basic-nine-v1',note='3 face close-ups and 6 full-body references; assistant visual inspection only, awaiting user review')
        result=self.api(f"/api/character-library/{entry['characterId']}/versions",body)
        entry.update(versionId=result['id'],version=result['version'],versionSha256=result['sha256'],versionBody=body);self.save()
    self.save(stage='ReferencePacksReady')
 def videos(self):
    self.access();self.preserve()
    for person in PEOPLE:
        body=dict(projectId=self.state['projectId'],versionId=self.state['people'][person['key']]['versionId'],view='front',framing='fullBody',prompt='A full-body locked camera portrait. The same person stands calmly, breathes gently and makes a very small natural weight shift. Keep the entire head, both feet and both shoes inside the frame. Preserve body proportions, hair and complete wardrobe. No walking, no turn, no speech, no cut.',seed=2026102901+PEOPLE.index(person))
        self.once(person['key']+'-fullBody-video',body,'/api/character-library/generate')
    self.save(stage='VideosReady')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','masters','references','populate','videos','check']);args=parser.parse_args();run=Run()
    if args.stage=='check' or run.state.get('completed'):run.access();run.preserve();print('Existing reference pack preserved; no new task submitted',flush=True)
    else:getattr(run,args.stage)()

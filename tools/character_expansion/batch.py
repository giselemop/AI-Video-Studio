"""Five fresh adult identities, nine photos each, through the existing Studio queue."""
from __future__ import annotations
import argparse
import copy
import datetime
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid
import requests

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'CharacterExpansionFive20261026'
sys.path.insert(0,str(ROOT/'tools/character_library'))
from run_acceptance import read,write,sha,media
sys.path.insert(0,str(ROOT/'tools'))
from character_prompt_policy import compose, POLICY

PEOPLE=[
 dict(key='xuzhixia',name='许知夏',age=24,gender='female',ageSetting='24岁成年女性',hair='深棕色长波浪卷发',faceFeatures='椭圆脸，杏仁眼，自然平眉',
      identity='One fictional adult East Asian woman, age 24, oval face, almond-shaped dark brown eyes, natural straight eyebrows, long loose dark brown wavy hair reaching mid-back, natural realistic skin, no glasses or jewelry',
      collar='forest-green cotton crew-neck collar',outfit='forest-green long-sleeve crew-neck cotton top, straight-leg black trousers, plain white low-top canvas sneakers',clothes='青绿色长袖上衣、黑色直筒裤、白色帆布鞋',
      body='natural adult female proportions, slim build, realistic hands and limbs',label='青绿休闲装 · 九图参考'),
 dict(key='chenyu',name='陈屿',age=26,gender='male',ageSetting='26岁成年男性',hair='黑色短碎发',faceFeatures='偏窄脸，清晰下颌，干净无胡须',
      identity='One fictional adult East Asian man, age 26, narrow face with a defined jaw, dark brown eyes, natural thick eyebrows, short slightly textured black hair, clean shaven, natural realistic skin, no glasses or jewelry',
      collar='light-gray cotton sweatshirt crew-neck collar',outfit='light-gray long-sleeve crew-neck sweatshirt, straight-leg dark blue denim jeans, simple black-and-white low-top sneakers',clothes='浅灰卫衣、深蓝直筒牛仔裤、黑白运动鞋',
      body='natural adult male proportions, lean athletic build, realistic hands and limbs',label='浅灰日常装 · 九图参考'),
 dict(key='suwanqing',name='苏晚晴',age=36,gender='female',ageSetting='36岁成年女性',hair='黑色低发髻',faceFeatures='略带棱角的鹅蛋脸，细长眼，自然眉形',
      identity='One fictional adult East Asian woman, age 36, angular oval face, dark brown slightly narrow eyes, natural gently arched eyebrows, black hair neatly pulled into a low bun at the nape, subtle natural adult facial lines and realistic skin, no glasses or jewelry',
      collar='dusty-blue modest blouse neckline',outfit='dusty-blue long-sleeve modest collarless blouse, straight-leg beige trousers, plain taupe leather loafers',clothes='雾蓝长袖衬衣、米色直筒裤、灰褐乐福鞋',
      body='natural adult female proportions, average build, realistic hands and limbs',label='雾蓝通勤装 · 九图参考'),
 dict(key='zhaomingyuan',name='赵明远',age=48,gender='male',ageSetting='48岁成年男性',hair='灰黑相间短发',faceFeatures='宽长方脸，成熟眼纹，干净无胡须',
      identity='One fictional adult East Asian man, age 48, broad rectangular face, dark brown eyes, visible natural forehead and eye lines, short cropped salt-and-pepper hair, clean shaven, realistic mature skin texture, no glasses or jewelry',
      collar='deep-brown knitted crew-neck collar',outfit='deep-brown long-sleeve crew-neck knit sweater, straight-leg navy trousers, simple black leather lace-up shoes',clothes='深棕针织衫、藏蓝直筒裤、黑色系带皮鞋',
      body='natural middle-aged adult male proportions, moderately stocky build, realistic hands and limbs',label='棕色针织装 · 九图参考'),
 dict(key='shenyulan',name='沈玉兰',age=58,gender='female',ageSetting='58岁成年女性',hair='自然灰黑短发',faceFeatures='圆润脸，明显笑纹与自然眼纹',
      identity='One fictional adult East Asian woman, age 58, softly rounded face, dark brown eyes, natural smile lines and eye wrinkles, short natural salt-and-pepper pixie haircut, realistic mature skin without beauty retouching, no glasses or jewelry',
      collar='soft-mauve buttoned knit cardigan neckline',outfit='soft-mauve long-sleeve knit cardigan buttoned closed, straight-leg charcoal trousers, simple black flat walking shoes',clothes='藕紫色扣合开衫、深灰直筒裤、黑色平底鞋',
      body='natural older adult female proportions, average build, realistic hands and limbs',label='藕紫针织装 · 九图参考')
]
SLOTS=[('front','closeUp'),('threeQuarterLeft','closeUp'),('threeQuarterRight','closeUp'),('front','fullBody'),('threeQuarterLeft','fullBody'),('left','fullBody'),('back','fullBody'),('right','fullBody'),('threeQuarterRight','fullBody')]
def trace_tasks(ids):
    spec=importlib.util.spec_from_file_location('character_delivery_helpers',ROOT/'tools/character_library/verify_delivery.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper.database_traces(ids)
def logical(person,view,framing):return person['key']+'-'+view+'-'+framing

class Batch:
 def __init__(self):
    self.base='http://127.0.0.1:18080';self.session=requests.Session()
    self.state=read(FOLDER/'run.json') if (FOLDER/'run.json').exists() else dict(runId=str(uuid.uuid4()),stage='Created',tasks={},people={},startedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
 def save(self,**fields):self.state.update(fields);write(FOLDER/'run.json',self.state)
 def api(self,path,body=None,method=None,key=None):
    response=self.session.request(method or ('POST' if body is not None else 'GET'),self.base+path,json=body,headers={'Idempotency-Key':key} if key else {},timeout=150)
    if not response.ok:raise RuntimeError(path+' HTTP '+str(response.status_code)+': '+response.text[:1000])
    return response.json()
 def access(self):
    status=self.api('/api/auth/status')
    if status.get('loginRequired',True) or status.get('accessMode')!='LocalOnly':raise RuntimeError('Use existing LocalOnly access; never bypass login')
    self.session.headers['X-CSRF-Token']=status['csrfToken']
 def selected_key(self,key):return read(FOLDER/'selection.json').get(key,key) if (FOLDER/'selection.json').exists() else key
 def selected(self,person,view,framing):return self.state['tasks'][self.selected_key(logical(person,view,framing))]
 def preserve(self):
    versions={v['id']:v for v in self.api('/api/character-library')['versions']}
    for v in self.state.get('originalVersions',[]):
        if versions.get(v['id'],{}).get('sha256')!=v['sha256']:raise RuntimeError('Prior immutable library version changed')
    for item in self.state.get('protectedFiles',[]):
        if sha(media(item['assetPath']))!=item['sha256']:raise RuntimeError('Existing library media changed')
    for previous in ['CharacterLibrary20261026','CharacterReferencePack20261026']:
        delivery=DATA/previous/'delivery.json'
        if delivery.exists():
            for item in read(delivery)['outputs']:
                if sha(media(item['assetPath']))!=item['sha256']:raise RuntimeError('Previously delivered photo or video changed')
    for record in self.state['tasks'].values():
        if record.get('sha256') and sha(media(record['path']))!=record['sha256']:raise RuntimeError('Recorded generated image changed')
 def sample(self):
    samples=read(FOLDER/'resource-samples.json') if (FOLDER/'resource-samples.json').exists() else []
    q=self.session.get('http://127.0.0.1:8188/queue',timeout=15).json();stats=self.session.get('http://127.0.0.1:8188/system_stats',timeout=15).json();device=stats['devices'][0]
    item=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),running=len(q['queue_running']),pending=len(q['queue_pending']),gpu=device['name'],usedMiB=(device['vram_total']-device['vram_free'])//1048576,totalMiB=device['vram_total']//1048576)
    samples.append(item);write(FOLDER/'resource-samples.json',samples)
    if item['running']>1:raise RuntimeError('Observed GPU concurrency exceeded one; stop further submissions')
 def once(self,key,body):
    record=self.state['tasks'].setdefault(key,{})
    frozen=dict(body,idempotencyKey='character-expansion:'+self.state['runId']+':'+key)
    if record.get('body') and record['body']!=frozen:raise RuntimeError('Frozen request changed; use a bounded repair key')
    if not record.get('body'):record['body']=frozen;self.save()
    if not record.get('id'):
        result=self.api('/api/tasks',frozen,key=frozen['idempotencyKey']);record['id']=result['id'];self.save()
    last=None;deadline=time.monotonic()+3600;sampled=0
    while time.monotonic()<deadline:
        detail=self.api('/api/tasks/'+str(record['id']));status=detail['task']['status']
        if status!=last:print(key,record['id'],status,flush=True);last=status
        if status=='Succeeded':
            output=next(item for item in detail['results'] if item.get('available') and str(item.get('assetPath','')).endswith('.png'))
            record.update(status=status,path=output['assetPath'],sha256=sha(media(output['assetPath'])));self.save()
            write(FOLDER/(key+'-task.json'),detail)
            trace=trace_tasks([record['id']])[0];write(FOLDER/(key+'-trace.json'),trace)
            receipt=self.session.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30);receipt.raise_for_status();history=receipt.json()
            if trace['comfyPromptId'] not in history:raise RuntimeError('Native history missing; preserve task before continuing')
            write(FOLDER/(key+'-comfy-history.json'),history);return record
        if status in ['Failed','Cancelled']:
            record.update(status=status,errorMessage=detail['task'].get('errorMessage'));self.save();write(FOLDER/(key+'-task.json'),detail)
            raise RuntimeError('Recorded task '+str(record['id'])+' '+status+': '+str(record.get('errorMessage',''))[:500])
        if time.monotonic()-sampled>12:self.sample();sampled=time.monotonic()
        time.sleep(3)
    raise RuntimeError('Task still unresolved; inspect this recorded ID before another submission')
 def prepare(self):
    self.access()
    if not self.state.get('originalVersions'):
        q=self.session.get('http://127.0.0.1:8188/queue',timeout=15).json();runtime=self.api('/api/minimax/local/status')
        if q['queue_running'] or q['queue_pending'] or runtime['queue']['activeTasks'] or runtime['queue']['paused']:raise RuntimeError('Preserve existing active or paused work; idle enabled queue required')
        library=self.api('/api/character-library');protected={ref['assetPath']:ref['sha256'] for version in library['versions'] for ref in version['payload']['references']}
        for folder in ['CharacterLibrary20261026','CharacterReferencePack20261026']:
            previous=read(DATA/folder/'run.json')
            if not previous.get('completed'):raise RuntimeError('Previous accepted flow is not completed')
            for item in previous.get('tasks',{}).values():
                if item.get('sha256'):protected[item['path']]=item['sha256']
        self.save(originalVersions=library['versions'],protectedFiles=[dict(assetPath=p,sha256=h) for p,h in protected.items()],environment=dict(health=self.api('/api/health'),queue=runtime['queue']),newModels=0,newCloudCalls=0,gpuConcurrency=1,requestedCharacters=5,requestedPhotos=45)
    self.preserve()
    names={w['name'] for w in self.api('/api/workflows')}
    if not {'realvisxl_reference_api','character_pack_klein4b_single_api','character_pack_klein4b_dual_api'}.issubset(names):raise RuntimeError('Use only existing admitted workflows')
    if not self.state.get('projectId'):
        name='五位人物九图参考_'+self.state['runId'][:8]
        existing=next((p for p in self.api('/api/projects') if p['name']==name),None)
        self.save(projectId=existing['id'] if existing else self.api('/api/projects',dict(name=name,description='Five new fictional adult characters, each 3 face close-ups and 6 full-body references. Images only; user content review pending.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id'])
    for person in PEOPLE:
        entry=self.state['people'].setdefault(person['key'],{})
        if not entry.get('characterId'):
            existing=next((c for c in self.api('/api/characters') if c.get('projectId')==self.state['projectId'] and c['name']==person['name']),None)
            body=dict(name=person['name'],projectId=self.state['projectId'],ageSetting=person['ageSetting'],hair=person['hair'],faceFeatures=person['faceFeatures'],clothes=person['clothes'],bodyRatio=person['body'],fixedPrompt=person['identity']+'. Keep exactly the same person, hairstyle and age as the reference.',negativePrompt='child, cartoon, duplicate person, text, watermark',voiceId='',voiceSpeed=1,voicePitch=0)
            entry['characterId']=existing['id'] if existing else self.api('/api/characters',body)['id'];self.save()
    self.save(stage='Prepared')
 def head_body(self,person):
    frozen=self.state['tasks'].get(person['key']+'-front-closeUp',{}).get('body')
    if frozen:return copy.deepcopy(frozen)
    workflow=next(w for w in self.api('/api/workflows') if w['name']=='realvisxl_reference_api')
    prompt=compose('front','closeUp',0,person['identity'],person['collar'])
    return dict(projectId=self.state['projectId'],taskType='Image',workflowId=workflow['id'],stage='Five-Characters-Fresh-Identity',maxRetries=0,parameters=dict(promptPolicy=POLICY['version'],workflowVersion='realvisxl-reference-1536-v1',positive=prompt,negative=POLICY['negative'],seed=20261026001+PEOPLE.index(person)*100,width=1536,height=864,steps=35,cfg=5.5))
 def image_body(self,person,view,framing):
    frozen=self.state['tasks'].get(logical(person,view,framing),{}).get('body')
    if frozen:return copy.deepcopy(frozen)
    dual=framing=='fullBody' and view!='front';identity=self.selected(person,'front','closeUp')['path']
    workflow=next(w for w in self.api('/api/workflows') if w['name']=='character_pack_klein4b_'+('dual' if dual else 'single')+'_api')
    slots=dict(firstFrame=identity)
    if dual:slots['wardrobeReference']=self.selected(person,'front','fullBody')['path']
    prompt=compose(view,framing,len(slots),person['identity'],person['collar'] if framing=='closeUp' else person['outfit'],person['body'])
    return dict(projectId=self.state['projectId'],taskType='Keyframe',workflowId=workflow['id'],inputImagePath=identity,stage='Five-Characters-'+view+'-'+framing,maxRetries=0,parameters=dict(promptPolicy=POLICY['version'],workflowVersion='character-pack-klein4b-'+('dual' if dual else 'single')+'-1536-v1',inputSlots=slots,positive=prompt,seed=20261026101+PEOPLE.index(person)*100+SLOTS.index((view,framing)),width=1536,height=864,steps=4,cfg=1))
 def heads(self):
    self.prepare()
    self.save(stage='GeneratingHeads')
    for person in PEOPLE:self.once(logical(person,'front','closeUp'),self.head_body(person))
    self.save(stage='AwaitingHeadsInspection')
 def masters(self):
    self.access();self.preserve()
    if read(FOLDER/'heads-review.json')['status']!='Passed':raise RuntimeError('Actually inspect the five independent faces first')
    self.save(stage='GeneratingMasters')
    for person in PEOPLE:self.once(logical(person,'front','fullBody'),self.image_body(person,'front','fullBody'))
    self.save(stage='AwaitingMastersInspection')
 def references(self):
    self.access();self.preserve()
    if read(FOLDER/'masters-review.json')['status']!='Passed':raise RuntimeError('Actually inspect full-body masters before deriving views')
    self.save(stage='GeneratingReferences')
    for person in PEOPLE:
        for view,framing in SLOTS:
            if view=='front':continue
            key=logical(person,view,framing)
            self.once(key,self.state['tasks'].get(key,{}).get('body') or self.image_body(person,view,framing))
        print(person['key']+' nine-reference candidates ready for inspection',flush=True)
    self.save(stage='AwaitingPackInspection')
 def populate(self):
    self.access();self.preserve()
    if read(FOLDER/'references-review.json')['status']!='Passed':raise RuntimeError('Inspect all 45 selected references before library capture')
    for person in PEOPLE:
        entry=self.state['people'][person['key']];refs=[]
        for view,framing in SLOTS:
            field=view+'-'+framing;record=self.selected(person,view,framing);reason=self.state['runId']+'|'+field
            if field not in entry:
                existing=next((ref for ref in self.api(f"/api/characters/{entry['characterId']}/references") if ref.get('changeReason')==reason),None)
                if existing:entry[field]=existing['id']
                else:
                    path=media(record['path'])
                    with path.open('rb') as stream:
                        response=self.session.post(self.base+f"/api/characters/{entry['characterId']}/references",files={'file':(path.name,stream,'image/png')},data=dict(kind='identity',isAnchor=str(view=='front' and framing=='closeUp').lower(),stage='reference-pack-v2',role='identity',changeReason=reason),timeout=120)
                    if not response.ok:raise RuntimeError('Reference upload rejected: '+response.text[:600])
                    entry[field]=response.json()['id']
                self.save()
            refs.append(dict(referenceId=entry[field],view=view,framing=framing))
        workflow=next(w for w in self.api('/api/workflows') if w['name']=='minimax_h3_local_i2v_api')
        body=dict(label=person['label'],outfit=person['outfit'],bodyDescription=person['body'],profile='baseline480',workflowId=workflow['id'],references=refs,referencePack='basic-nine-v1',note='Five fresh fictional adult characters; 3 face + 6 full-body photos each. Assistant framing inspection only, awaiting user content review.')
        version=self.api(f"/api/character-library/{entry['characterId']}/versions",body)
        entry.update(versionId=version['id'],version=version['version'],versionSha256=version['sha256'],versionBody=body);self.save()
    self.save(stage='ReferencePacksReady')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','heads','masters','references','populate','check']);args=parser.parse_args();batch=Batch()
    if args.stage=='check' or batch.state.get('completed'):batch.access();batch.preserve();print('Existing expansion preserved; no task submitted',flush=True)
    else:getattr(batch,args.stage)()

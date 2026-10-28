"""Fresh two-character library acceptance. All generation goes through Studio APIs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'CharacterLibrary20261026'
PEOPLE = [
    dict(key='linan', name='林安', ageSetting='27岁成年女性', hair='黑色齐肩直发',
         faceFeatures='鹅蛋脸，深棕眼睛，自然眉形', clothes='米白色针织上衣',
         fixedPrompt='One adult East Asian woman, age 27, oval face, dark brown eyes, straight shoulder-length black hair, natural eyebrows, ivory knit sweater, realistic natural skin. Keep the same person and wardrobe as the reference image.'),
    dict(key='zhouyan', name='周言', ageSetting='30岁成年男性', hair='黑色短发',
         faceFeatures='略方脸，浓眉，干净无胡须', clothes='深蓝色衬衫',
         fixedPrompt='One adult East Asian man, age 30, slightly square face, thick natural eyebrows, short neat black hair, clean shaven, navy blue shirt, realistic natural skin. Keep the same person and wardrobe as the reference image.')
]

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(p)
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def media(p):
    full = (DATA / p).resolve(strict=True)
    if not full.is_relative_to(DATA.resolve()) or not full.is_file(): raise ValueError('Controlled Data file required')
    return full

class Run:
    def __init__(self, base):
        self.base = base.rstrip('/'); self.session = requests.Session()
        self.state = read(FOLDER/'run.json') if (FOLDER/'run.json').exists() else dict(runId=str(uuid.uuid4()), stage='Created', people={})
    def save(self, **values):
        self.state.update(values); write(FOLDER/'run.json', self.state)
    def access(self):
        result = self.api('/api/auth/status')
        if result.get('loginRequired', True) or result.get('accessMode') != 'LocalOnly': raise RuntimeError('LocalOnly mode required; login is never bypassed')
        self.session.headers['X-CSRF-Token'] = result['csrfToken']
    def api(self, path, body=None, method=None, key=None):
        headers = {'Idempotency-Key': key} if key else {}
        response = self.session.request(method or ('POST' if body is not None else 'GET'), self.base+path, json=body, headers=headers, timeout=120)
        if not response.ok: raise RuntimeError(f'{path}: HTTP {response.status_code}: {response.text[:1000]}')
        return response.json()
    def once(self, key, body, endpoint='/api/tasks'):
        record = self.state.setdefault('tasks', {}).setdefault(key, {})
        frozen = dict(body); frozen['idempotencyKey'] = 'charlib:'+self.state['runId']+':'+key
        if record.get('body') and record['body'] != frozen: raise RuntimeError('Frozen task changed: '+key)
        if not record.get('body'): record['body'] = frozen; self.save()
        if not record.get('id'):
            result = self.api(endpoint, frozen, key=frozen['idempotencyKey']); record['id'] = result['id']; self.save()
        last = None
        deadline = time.monotonic()+7200
        while time.monotonic()<deadline:
            result = self.api('/api/tasks/'+str(record['id'])); status = result['task']['status']
            if status != last:
                print(key, record['id'], status, flush=True); last=status
            if status == 'Succeeded':
                chosen = next(item for item in result['results'] if item.get('available') and str(item.get('assetPath','')).lower().endswith(('.png','.mp4')))
                record.update(path=chosen['assetPath'], sha256=sha(media(chosen['assetPath'])), status=status)
                self.save(); write(FOLDER/(key+'-task.json'), result); return record
            if status in ('Failed','Cancelled'): raise RuntimeError('Task '+str(record['id'])+' '+status+': '+str(result['task'].get('errorMessage',''))[:1000])
            time.sleep(4)
        raise RuntimeError('Task still unresolved; inspect before resubmitting')
    def preserve(self):
        for key, record in self.state.get('tasks',{}).items():
            if record.get('sha256') and sha(media(record['path'])) != record['sha256']: raise RuntimeError('Frozen artifact changed: '+key)
        if self.state.get('browserTaskPath') and sha(media(self.state['browserTaskPath']))!=self.state.get('browserTaskSha256'):
            raise RuntimeError('Browser-submitted video changed')
    def prepare(self):
        self.access()
        if not self.state.get('environment'):
            health = self.api('/api/health'); comfy = requests.get('http://127.0.0.1:8188/queue',timeout=10).json()
            if comfy['queue_running'] or comfy['queue_pending']: raise RuntimeError('Existing Comfy tasks must finish before acceptance')
            self.save(environment=dict(health=health, comfyQueue=comfy), localOnly=True, gpuConcurrency=1, newModels=0, newCloudCalls=0)
        if not self.state.get('projectId'):
            name='两个人物库调用验收_'+self.state['runId'][:8]
            existing=next((p for p in self.api('/api/projects') if p['name']==name),None)
            pid=existing['id'] if existing else self.api('/api/projects',dict(name=name,description='Two fresh fixed characters; immutable library versions and real local video calls. Content remains NeedReview.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id']
            self.save(projectId=pid)
        self.save(stage='Prepared')
    def seed(self):
        self.prepare()
        workflows={w['name']:w['id'] for w in self.api('/api/workflows')}
        for index, person in enumerate(PEOPLE):
            key=person['key']; entry=self.state['people'].setdefault(key,{})
            if not entry.get('characterId'):
                name=person['name']+'（人物库试用）'
                existing=next((c for c in self.api('/api/characters') if c['name']==name and c.get('projectId')==self.state['projectId']),None)
                body={k:v for k,v in person.items() if k!='key'};body.update(name=name,projectId=self.state['projectId'],voiceId='',voiceSpeed=1,voicePitch=0)
                entry['characterId']=existing['id'] if existing else self.api('/api/characters',body)['id'];self.save()
            prompt=person['fixedPrompt']+' Medium close-up portrait from waist up, exact frontal view facing camera, relaxed neutral closed mouth, shoulders level, looking directly at camera, seated in a quiet sunlit reading room, soft window light, single person, documentary photograph, clear unobstructed face.'
            self.once(key+'-master',dict(projectId=self.state['projectId'],taskType='Image',workflowId=workflows['realvisxl_reference_api'],stage='Character-Library-Fresh-Master',maxRetries=0,parameters=dict(workflowVersion='realvisxl-reference-1536-v1',positive=prompt,negative='child, illustration, cartoon, CGI, deformed face, blurry eyes, extra person, duplicate face, text, watermark',seed=2026102601+index,width=1536,height=864,steps=35,cfg=5.5)))
        self.save(stage='FreshMastersReady')
    def views(self):
        self.access();self.preserve();workflows={w['name']:w['id'] for w in self.api('/api/workflows')}
        contracts=read(ROOT/'config/workflow-contracts.json')
        values=contracts.get('contracts',[]) if isinstance(contracts,dict) else contracts
        contract=next(c for c in values if c['fileName']=='flux2_klein4b_keyframe_v2_api.json')
        for index,person in enumerate(PEOPLE):
            source=self.state['tasks'][person['key']+'-master']['path']
            prompt='Keep exactly the same adult person, face identity, hair, age and clothing in the input photograph. Change only the camera angle to a gentle three-quarter right view, about 25 degrees. Chest-up framing, eyes clearly visible, relaxed neutral closed mouth, same reading room and soft light, photorealistic. No added person, text or accessories.'
            self.once(person['key']+'-threeQuarterRight',dict(projectId=self.state['projectId'],taskType='Keyframe',workflowId=workflows['flux2_klein4b_keyframe_v2_api'],inputImagePath=source,stage='Character-Library-Reference-View',maxRetries=0,parameters=dict(workflowVersion=contract['id'],inputSlots=dict(firstFrame=source),positive=prompt,seed=2026102621+index,width=1024,height=576,steps=4,cfg=1)))
        self.save(stage='FreshViewsReady')
    def populate(self):
        self.access();self.preserve();workflows={w['name']:w['id'] for w in self.api('/api/workflows')}
        for person in PEOPLE:
            entry=self.state['people'][person['key']];refs=[]
            for view,taskkey in [('front',person['key']+'-master'),('threeQuarterRight',person['key']+'-threeQuarterRight')]:
                path=media(self.state['tasks'][taskkey]['path']); field=view+'ReferenceId'
                if not entry.get(field):
                    existing=next((r for r in self.api(f"/api/characters/{entry['characterId']}/references") if r.get('changeReason')==self.state['runId']+':'+view),None)
                    if existing:entry[field]=existing['id']
                    else:
                        with path.open('rb') as image:
                            response=self.session.post(self.base+f"/api/characters/{entry['characterId']}/references",files={'file':(path.name,image,'image/png')},data=dict(kind='identity',isAnchor=str(view=='front').lower(),stage='base',role='identity',changeReason=self.state['runId']+':'+view),timeout=120)
                        if not response.ok:raise RuntimeError('Reference upload rejected: '+response.text[:500])
                        entry[field]=response.json()['id']
                    self.save()
                refs.append(dict(referenceId=entry[field],view=view))
            body=dict(label='阅读室日常装',outfit=person['clothes'],profile='baseline480',workflowId=workflows['minimax_h3_local_i2v_api'],references=refs,note='Fresh two-character library acceptance; awaiting user content review')
            version=self.api(f"/api/character-library/{entry['characterId']}/versions",body)
            entry.update(versionId=version['id'],version=version['version'],versionSha256=version['sha256'],versionBody=body);self.save()
        self.save(stage='LibraryVersionsReady')
    def render(self):
        self.access();self.preserve()
        for index,person in enumerate(PEOPLE):
            for shot,view in enumerate(['front','threeQuarterRight']):
                key=person['key']+'-video-'+view
                scene='A quiet continuous portrait shot. The person breathes gently, blinks naturally once, and gives a subtle relaxed smile. Keep the face, hair, clothing and room consistent with the first frame. Fixed camera, small natural motion, no speech, no subtitles, no scene cut.' if shot==0 else 'A quiet continuous portrait shot. The person keeps the three-quarter pose, makes a small thoughtful nod and returns to a relaxed expression. Keep the same face, hair, clothing and room as the first frame. Fixed camera, small natural motion, no speech, no subtitles, no scene cut.'
                body=dict(projectId=self.state['projectId'],versionId=self.state['people'][person['key']]['versionId'],view=view,prompt=scene,seed=2026102651+index*10+shot)
                self.once(key,body,'/api/character-library/generate')
        self.save(stage='VideosReady')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','seed','views','populate','render','check']);parser.add_argument('--base',default='http://127.0.0.1:18080');args=parser.parse_args()
    run=Run(args.base)
    if args.stage=='check' or run.state.get('completed'):
        run.preserve();print('Frozen artifacts verified; no new task submitted',flush=True)
    else:getattr(run,args.stage)()

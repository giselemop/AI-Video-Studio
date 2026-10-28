"""Local, queue-only reference/expression revision; preserve original voice and all prior takes."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw
import requests

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'FaceActing20261024'
OLD=DATA/'DialogueThreeShot20261023'
API='http://127.0.0.1:18080'
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
PYTHON=ROOT.parent/'ComfyUI/venv/Scripts/python.exe'
sys.path.insert(0,str(ROOT/'tools/minimax'))
from run_local_acceptance import Acceptance,TaskFailure


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def media(value):
    path=(DATA/value).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():raise RuntimeError('Expected controlled Data input')
    return path
def preserve(run):
    for item in run.state['preserved']:
        if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Prior media or approved audio changed: '+item['path'])
    for index,digest in run.state.get('referenceHashes',{}).items():
        if sha(FOLDER/f'reference-{index}.png')!=digest:raise RuntimeError('Frozen expression reference changed')
    if run.state.get('selectedMasterSha256') and sha(media(run.state['selectedMasterPath']))!=run.state['selectedMasterSha256']:
        raise RuntimeError('Frozen two-person master changed')
    if run.state.get('finalSha256') and sha(media(run.state['finalPath']))!=run.state['finalSha256']:
        raise RuntimeError('Delivered final file changed')


class Run(Acceptance):
    def poll(self,task_id,limit=7200):
        import psutil
        start=time.monotonic();last=0
        while time.monotonic()-start<limit:
            detail=self.api(f'/api/tasks/{task_id}');task=detail['task']
            sample=dict(epoch=time.time(),taskId=task_id,status=task['status'],progress=task.get('progress'),
                        availableRamMiB=psutil.virtual_memory().available//1024**2)
            raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu',
                '--format=csv,noheader,nounits'],text=True,timeout=10)
            sample['gpu']=[int(x.strip()) for x in raw.strip().split(',')]
            with (FOLDER/'resources.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(sample)+'\n')
            if time.monotonic()-last>=45:print(json.dumps(sample),flush=True);last=time.monotonic()
            if task['status']=='Succeeded':
                write(FOLDER/f'task-{task_id}.json',detail);return detail
            if task['status'] in ['Failed','Cancelled']:
                write(FOLDER/f'task-{task_id}.json',detail)
                raise TaskFailure(task_id,task['status'],str(task.get('errorMessage'))[:2000])
            time.sleep(5)
        raise RuntimeError(f'Existing task {task_id} unresolved; no duplicate submission')


def once(run,field,body):
    preserve(run)
    if run.state.get(field+'Input') not in [None,body]:raise RuntimeError('Frozen task parameters changed')
    if not run.state.get(field):
        if run.state.get(field+'Started'):raise RuntimeError('Submission outcome unresolved; query existing tasks')
        pre=run.api('/api/tasks/preflight',body,timeout=600);write(FOLDER/(field+'-preflight.json'),pre)
        if not pre['passed']:raise RuntimeError(str(pre['issues']))
        run.save(**{field+'Input':body,field+'Started':True})
        response=run.api('/api/tasks',body,key=field,timeout=600)
        run.save(**{field:response.get('id') or response.get('taskId')})
        print(field,run.state[field],flush=True)
    return run.poll(run.state[field])


def result(detail,suffix):
    return next(x['assetPath'] for x in detail['results'] if x.get('available') and x.get('assetPath','').endswith(suffix))


def prepare(run):
    if run.state.get('prepared'):preserve(run);print('Existing preparation preserved');return
    old=read(OLD/'run.json');qhd=read(DATA/'Dialogue2KSeedVR220261024/run.json');skin=read(DATA/'SkinPilot20261024/run.json')
    records=[]
    for path in [old['finalPath'],qhd['finalPath'],skin['finalPath'],old['mixPath'],
                 'DialogueThreeShot20261023/run.json','Dialogue2KSeedVR220261024/run.json','SkinPilot20261024/run.json',
                 'DialogueThreeShot20261023/audio/dialogue.srt']:
        records.append(dict(path=path,sha256=sha(media(path))))
    for index in range(1,4):
        for role in ['female','male']:
            path=f'DialogueThreeShot20261023/audio/shot-{index}-{role}-native.wav'
            records.append(dict(path=path,sha256=sha(media(path))))
    run.save('PreparingReferences',preserved=records,timeline=old['timeline'],shots=read(OLD/'audio/shot-definitions.json'),
             originalPath=old['finalPath'],previousQhdPath=qhd['finalPath'],previousSkinPath=skin['finalPath'],
             sourceReference='Artifacts/project-32/image/task-1216/v0001/v0001_task_1216_task_1216_attempt_1_20013b81_00001__0a56bd1c7561.png',
             referenceRepairLimit=2,shotRepairLimit=2,deliveryFrames=240,deliveryFps=24,deliverySeconds=10)
    records.append(dict(path=run.state['sourceReference'],sha256=sha(media(run.state['sourceReference']))))
    run.save(preserved=records)
    names=['config/workflow-contracts.json','项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
    for name in names:
        dest=FOLDER/'source-before'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(ROOT/name,dest)
    (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),encoding='utf-8')
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
    from identity_foundation import import_runtime
    _,_,_,FaceAnalysis=import_runtime()
    models=ROOT.parent/'Models/InsightFace'
    for name in ['det_10g.onnx','1k3d68.onnx']:
        if not (models/'models/buffalo_l'/name).is_file():raise RuntimeError('Missing offline CPU geometry model')
    app=FaceAnalysis(name='buffalo_l',root=str(models),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68'])
    app.prepare(ctx_id=-1,det_size=(640,640),det_thresh=.4)
    source=cv2.imread(str(media(run.state['sourceReference'])))
    faces=sorted(app.get(source),key=lambda f:f.bbox[0])
    if len(faces)!=2:raise RuntimeError('Original reference must have two detected faces')
    geometry={}
    for role,face in zip(['female','male'],faces):
        p=face.landmark_3d_68[:,:2]
        lo=p.min(axis=0);hi=p.max(axis=0);size=round(max(hi-lo)*1.8/8)*8
        center=(lo+hi)/2;center[1]-=(hi[1]-lo[1])*.16
        x=int(np.clip(round(center[0]-size/2),0,source.shape[1]-size));y=int(np.clip(round(center[1]-size/2),0,source.shape[0]-size))
        crop=cv2.resize(source[y:y+size,x:x+size],(768,768),interpolation=cv2.INTER_LANCZOS4)
        points=(p-[x,y])*(768/size)
        mask=np.zeros((768,768),np.uint8)
        # Edit cheeks, nose wing transitions, lips and chin together; preserve upper identity landmarks.
        hull=cv2.convexHull(np.concatenate([points[:17],points[[17,21,22,26]]]).astype(np.int32))
        cv2.fillConvexPoly(mask,hull,255)
        eye_protection=np.zeros_like(mask)
        for indexes in [range(36,42),range(42,48),range(17,22),range(22,27),range(27,31)]:
            part=np.zeros_like(mask);cv2.fillConvexPoly(part,cv2.convexHull(points[list(indexes)].astype(np.int32)),255)
            eye_protection=cv2.bitwise_or(eye_protection,cv2.dilate(part,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(21,21))))
        mask[eye_protection>0]=0
        mask=cv2.GaussianBlur(mask,(0,0),4)
        mask[eye_protection>0]=0
        folder=FOLDER/'references'/role;folder.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(folder/'input.png'),crop);cv2.imwrite(str(folder/'mask.png'),cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
        geometry[role]=dict(roi=[x,y,size,size],points=points.tolist(),input=str((folder/'input.png').relative_to(DATA)),
                            mask=str((folder/'mask.png').relative_to(DATA)))
    write(FOLDER/'reference-geometry.json',geometry)
    run.save('ReferencesPrepared',prepared=True,geometry=geometry)
    print({role:g['roi'] for role,g in geometry.items()},flush=True)


EXPRESSIONS={
    1:'a calm relaxed neutral expression, lips gently touching and fully closed, no visible teeth, relaxed cheeks and jaw',
    2:'a very slight warm closed-lip smile, no visible teeth, relaxed cheeks, a subtle natural lift at the mouth corners',
    3:'a restrained playful half-smile in the original three-quarter angle, lips resting together, no wide grin, relaxed cheek muscles'
}


def register(run):
    doc=read(ROOT/'config/workflow-contracts.json')
    graph=read(ROOT.parent/'Workflows/realvisxl_skin_patch_768_api.json')
    graph['9']['inputs'].update(denoise=.48,cfg=4.5,steps=32)
    graph['12']['inputs']['filename_prefix']='face_acting/reference'
    template=copy.deepcopy(next(c for c in doc['contracts'] if c['id']=='realvisxl-skin-patch-768-v1'))
    path=ROOT.parent/'Workflows/realvisxl_expression_reference_768_api.json'
    write(path,graph)
    template.update(id='realvisxl-expression-reference-768-v1',version='realvisxl-expression-reference-768-v1',fileName=path.name,
        notes='sha256='+sha(path)+' | Same-angle original-conditioned mouth/cheek/jaw expression repair, original eyes/upper nose/hair preserved. Experimental local preview, human review required.')
    new=[template]
    for index in range(1,4):
        graph=read(ROOT.parent/f'Workflows/dialogue_three_shot_{index}_v1_api.json')
        template=copy.deepcopy(next(c for c in doc['contracts'] if c['id']==f'dialogue-three-shot-{index}-v1'))
        # More sampling steps and a bounded shorter window; preserve all pretrained weights.
        graph['14']['inputs']['frame_window_size']=57
        graph['14']['inputs']['motion_frame']=9
        graph['15']['inputs']['steps']=8
        graph['7']['inputs']['audio_scale']=.95
        prompts={
          1:'Live-action close-up of the exact same adult woman in the reference, seated on the same sofa in beige cardigan. She looks toward screen right at the man. She says her Mandarin line naturally with a small teasing eyebrow lift, restrained cheek movement and relaxed jaw. No fixed broad smile. Her cheeks and lips move together, then her lips close and she listens. Gentle breathing and one natural blink. Same head proportions and identity, soft natural skin, unchanged room and window lighting, static camera.',
          2:'Live-action reverse close-up of the exact same adult man in the reference, olive cardigan and dark shirt. His eyes turn toward the LEFT edge of the image to the woman. He gives a brief mildly amused Mandarin answer with restrained mouth movement and one small eyebrow reaction. His lips close at the end, then he listens attentively to screen left. Keep his head stable, same identity and face proportions, soft natural skin, same window lighting, static camera.',
          3:'Live-action two-shot of the exact same woman on the LEFT and man on the RIGHT, seated on the cream sofa. The woman speaks her own Mandarin line with a warm restrained expression while the man listens silently. Then the man answers his own audio with a small satisfied smile and tiny nod. They keep their gaze engaged toward each other until the end. Lips close between turns. Natural cheek and eyebrow reactions together with lip movement, no frozen grin. Same faces, hair, clothes, phone, hands and room, soft natural skin, static camera, no large head turns.'}
        graph['5']['inputs']['positive']=prompts[index]
        graph['5']['inputs']['negative']+=' , rigid grin, stretched cheeks, deep carved smile lines, rubber mouth, floating lips, fixed teeth, reshaped jaw, overacting'
        graph['18']['inputs']['filename_prefix']=f'face_acting/shot_{index}'
        version=f'face-acting-shot-{index}-v1';path=ROOT.parent/f'Workflows/face_acting_shot_{index}_v1_api.json'
        write(path,graph)
        template.update(id=version,version=version,fileName=path.name,notes='sha256='+sha(path)+' | Same approved actors/audio; corrected reference expression, 8 steps, 57-frame window, audio_scale .95; exact output trim and content review required.')
        new.append(template)
    for item in new:
        existing=[c for c in doc['contracts'] if c['id']==item['id']]
        if existing and existing!=[item]:raise RuntimeError('An existing contract differs; version it')
        if not existing:doc['contracts'].append(item)
    write(ROOT/'config/workflow-contracts.json',doc)
    run.save(registeredWorkflows=[c['id'] for c in new],referenceWorkflow='realvisxl-expression-reference-768-v1')
    print('Four new experimental workflows pinned; prior contracts preserved',flush=True)


def project(run):
    run.access()
    if run.state.get('projectId'):return
    name='同人物表情与结构重建_'+run.state['runId'][:8]
    matches=[p for p in run.api('/api/projects') if p['name']==name]
    if matches:pid=matches[0]['id']
    elif run.state.get('projectStarted'):raise RuntimeError('Project creation unresolved')
    else:
        run.save(projectStarted=True)
        pid=run.api('/api/projects',dict(name=name,description='Local expression/reference repair, 2s pilot and 10s three-shot QHD film; original dialogue/audio retained.',defaultWidth=2560,defaultHeight=1440,defaultFps=24))['id']
    run.save(projectId=pid)
    run.api('/api/workflows/scan',{},timeout=600)


def references(run,role,attempt):
    if attempt not in [1,2,3]:raise RuntimeError('Maximum initial plus two targeted reference repairs')
    project(run)
    if attempt>1 and not (FOLDER/f'{role}-reference-repair-{attempt}.json').is_file():raise RuntimeError('Record a targeted repair reason first')
    wf=next(w for w in run.api('/api/workflows') if w['name']=='realvisxl_expression_reference_768_api')
    for index in ([1,2,3] if role=='female' else [1]):
        gender='woman with long dark hair' if role=='female' else 'man with short dark hair and light stubble'
        prompt=f'Photorealistic close-up of the exact same adult East Asian {gender} in the input photograph, {EXPRESSIONS[index]}. Preserve original eye and nose shape, age, facial identity, original head angle, hair, light direction and exposure. Anatomically coherent lips, natural mouth width, soft realistic transitions from cheeks to mouth corners and chin. Unretouched natural skin, subtle asymmetry, no makeup change.'
        negative='different person, different face, wide grin, teeth, open mouth, laughing, stretched lips, deep carved smile lines, plastic skin, beauty filter, doll, distorted jaw, exaggerated cheekbones, big eyes, anime, wrinkles, freckles, moles, text'
        input_path=run.state['geometry'][role]['input']
        mask_path=run.state['geometry'][role]['mask']
        if attempt>1 or role=='male':
            input_path=str((FOLDER/'references'/role/'closed-guide.png').relative_to(DATA))
        if attempt>1:
            repair=read(FOLDER/f'{role}-reference-repair-{attempt}.json')
            mask_path=repair.get('mask',mask_path)
            input_path=repair.get('input',input_path)
        if attempt==3:
            repair=read(FOLDER/f'{role}-reference-repair-3.json')
            input_path=repair['input'];mask_path=repair['mask']
        params=dict(workflowVersion=run.state['referenceWorkflow'],width=768,height=768,
          prompt=prompt,negative=negative,seed=2026102410+index+(attempt-1)*100,steps=32,cfg=4.5 if attempt==1 and role=='female' else 5.0,
          denoise=.48 if attempt==1 and role=='female' else .62,inputSlots=dict(firstFrame=input_path,editMask=mask_path))
        body=dict(projectId=run.state['projectId'],taskType='Image',resourceClass='GPU',workflowId=wf['id'],maxRetries=0,
                  stage=f'Expression-Reference-{role}-{index}-Attempt-{attempt}',parameters=params)
        detail=once(run,f'{role}Ref{index}Attempt{attempt}TaskId',body)
        path=result(detail,('.png','.jpg','.webp'))
        run.save(**{f'{role}Ref{index}Attempt{attempt}Path':path})
    run.save(f'Awaiting{role.title()}ReferenceInspection')


def video(run,index,attempt):
    if attempt not in [1,2,3]:raise RuntimeError('Maximum initial plus two targeted shot repairs')
    project(run)
    if not (FOLDER/'reference-selection.json').exists():raise RuntimeError('Actual reference selection required')
    if index>1 and not (FOLDER/'pilot-review.json').exists():raise RuntimeError('Review the two-second pilot before extending')
    if attempt>1 and not (FOLDER/f'shot-{index}-repair-{attempt}.json').exists():raise RuntimeError('Targeted shot repair reason required')
    wf=next(w for w in run.api('/api/workflows') if w['name']==f'face_acting_shot_{index}_v1_api')
    shot=run.state['shots'][index-1]
    frames=math.ceil(shot['durationSeconds']*25)+1
    first=f'FaceActing20261024/reference-{index}.png'
    slots=dict(firstFrame=first)
    if index<3:
        role='female' if index==1 else 'male';slots['speakerAudio']=f'DialogueThreeShot20261023/audio/shot-{index}-{role}-native.wav'
    else:slots.update(femaleAudio='DialogueThreeShot20261023/audio/shot-3-female-native.wav',maleAudio='DialogueThreeShot20261023/audio/shot-3-male-native.wav')
    body=dict(projectId=run.state['projectId'],taskType='ImageToVideo',resourceClass='GPU',workflowId=wf['id'],inputImagePath=first,
              maxRetries=0,stage=f'Face-Acting-Shot-{index}-Attempt-{attempt}',parameters=dict(workflowVersion=f'face-acting-shot-{index}-v1',
              width=832,height=480,fps=25,frames=frames,duration=frames/25,steps=8,cfg=1,seed=2026102450+index+(attempt-1)*100,inputSlots=slots))
    if attempt>1:
        repair=read(FOLDER/f'shot-{index}-repair-{attempt}.json')
        overrides=repair.get('parameters',{})
        if not overrides or set(overrides)-{'positive','negative','steps','cfg','seed'}:raise RuntimeError('Targeted repair needs bounded prompt/sampling changes')
        body['parameters'].update(overrides)
    detail=once(run,f'shot{index}Attempt{attempt}TaskId',body);path=result(detail,'.mp4')
    run.save(f'AwaitingShot{index}Inspection',**{f'shot{index}Attempt{attempt}Path':path})
    print(path,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,choices=['prepare','register','references','video','check'])
    parser.add_argument('--role',choices=['female','male'],default='female');parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--shot',type=int,choices=[1,2,3],default=1)
    args=parser.parse_args();FOLDER.mkdir(parents=True,exist_ok=True);run=Run(API,FOLDER/'run.json')
    if args.stage=='check' or run.state.get('stage')=='ReadyForUserPreview':preserve(run);print('Preserved existing files; no new task');return
    if args.stage=='prepare':prepare(run)
    elif args.stage=='register':register(run)
    elif args.stage=='references':references(run,args.role,args.attempt)
    else:video(run,args.shot,args.attempt)


if __name__=='__main__':main()

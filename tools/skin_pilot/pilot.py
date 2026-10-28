"""Two-second, local skin-detail experiment. All generated deliverables use the queue."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'SkinPilot20261024'
API = 'http://127.0.0.1:18081'
PYTHON = ROOT.parent / 'ComfyUI/venv/Scripts/python.exe'
FFMPEG = Path(r'C:\install\FFmpeg\bin\ffmpeg.exe')
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from run_local_acceptance import Acceptance, TaskFailure


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def media(value):
    path = (DATA / value).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise ValueError('Expected existing file within Data')
    return path


class Run(Acceptance):
    def poll(self, task_id, limit=2400):
        import psutil
        start = time.monotonic()
        while time.monotonic()-start < limit:
            detail = self.api(f'/api/tasks/{task_id}')
            task = detail['task']
            sample = dict(epoch=time.time(), taskId=task_id, status=task['status'],
                          availableRamMiB=psutil.virtual_memory().available//1024**2)
            raw = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu',
                                          '--format=csv,noheader,nounits'], text=True, timeout=10)
            sample['gpu'] = [int(x.strip()) for x in raw.strip().split(',')]
            with (FOLDER/'resources.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(sample)+'\n')
            if task['status'] == 'Succeeded':
                write(FOLDER/f'task-{task_id}.json', detail)
                return detail
            if task['status'] in ['Failed','Cancelled']:
                raise TaskFailure(task_id, task['status'], str(task.get('errorMessage'))[:1800])
            time.sleep(4)
        raise RuntimeError(f'Task {task_id} unresolved; do not submit a duplicate')


def preserve(run):
    for entry in run.state['preserved']:
        if sha(media(entry['path'])) != entry['sha256']:
            raise RuntimeError('A preserved source changed')


def once(run, field, body):
    preserve(run)
    if run.state.get(field+'Input') and run.state[field+'Input'] != body:
        raise RuntimeError('Frozen submission changed')
    if not run.state.get(field):
        if run.state.get(field+'Started'):
            raise RuntimeError('Unresolved submission; inspect existing tasks')
        preflight = run.api('/api/tasks/preflight', body, timeout=300)
        write(FOLDER/(field+'-preflight.json'), preflight)
        if not preflight['passed']:
            raise RuntimeError(str(preflight['issues']))
        run.save(**{field+'Started':True,field+'Input':body})
        response = run.api('/api/tasks', body, key=field, timeout=300)
        run.save(**{field:response.get('id') or response.get('taskId')})
        print(field, run.state[field], flush=True)
    return run.poll(run.state[field])


def result(detail, suffix):
    return next(item['assetPath'] for item in detail['results']
                if item.get('available') and item.get('assetPath','').lower().endswith(suffix))


def skin_mask(image, points):
    h,w = image.shape[:2]
    p = points.astype(np.float32)
    face_height = float(p[8,1]-min(p[19,1],p[24,1]))
    forehead = p[17:27].copy()
    forehead[:,1] -= .42*face_height
    hull = cv2.convexHull(np.concatenate([p[:17],forehead]).astype(np.int32))
    region = np.zeros((h,w), np.uint8)
    cv2.fillConvexPoly(region,hull,255)
    region = cv2.erode(region,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(17,17)))
    protected = np.zeros_like(region)
    for indexes,margin in [(range(36,42),17),(range(42,48),17),(range(48,68),28),
                           (range(17,22),11),(range(22,27),11),(range(27,36),10)]:
        part = np.zeros_like(region)
        cv2.fillConvexPoly(part,cv2.convexHull(p[list(indexes)].astype(np.int32)),255)
        part = cv2.dilate(part,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(margin*2+1,margin*2+1)))
        protected = cv2.bitwise_or(protected,part)
    color = cv2.cvtColor(image,cv2.COLOR_BGR2YCrCb)
    color_ok = cv2.inRange(color,np.array([30,130,72]),np.array([255,190,142]))
    support = (region>0)&(protected==0)&(color_ok>0)
    # Distance feathering stays INSIDE the support: no bleed into lips, eyes or the background.
    distance = cv2.distanceTransform(support.astype(np.uint8),cv2.DIST_L2,5)
    alpha = np.clip(distance/12,0,1)
    return np.round(alpha*255).astype(np.uint8), protected


def prepare(run):
    FOLDER.mkdir(parents=True,exist_ok=True)
    if run.state.get('prepared'):
        preserve(run)
        print('Prepared files preserved; no new task',flush=True)
        return
    old = read(DATA/'DialogueThreeShot20261023/run.json')
    qhd = read(DATA/'Dialogue2KSeedVR220261024/run.json')
    if old['stage'] != 'ReadyForUserPreview' or qhd['stage'] != 'ReadyForUserPreview':
        raise RuntimeError('Completed original and QHD sources required')
    run.save('Preparing',originalPath=old['finalPath'],qhdPath=qhd['finalPath'],startFrame=5,
             frameCount=48,fps=24,line='哟，约会回来了？',keyframes=[0,12,24,36,47],
             preserved=[dict(path=old['finalPath'],sha256=old['finalSha256']),
                        dict(path=qhd['finalPath'],sha256=qhd['finalSha256']),
                        dict(path=str((DATA/'DialogueThreeShot20261023/run.json').relative_to(DATA)),sha256=sha(DATA/'DialogueThreeShot20261023/run.json')),
                        dict(path=str((DATA/'Dialogue2KSeedVR220261024/run.json').relative_to(DATA)),sha256=sha(DATA/'Dialogue2KSeedVR220261024/run.json'))])
    preserve(run)
    # Back up only intended edit targets; no reset or deletion of prior work.
    targets=['server/TaskSubmissionPreflightService.cs','server/GenerationQueue.cs','config/workflow-contracts.json',
             '项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md',
             'docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
    for name in targets:
        dst=FOLDER/'source-before'/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists():shutil.copy2(ROOT/name,dst)
    (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),encoding='utf-8')
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
    from identity_foundation import import_runtime
    _,_,_,FaceAnalysis=import_runtime()
    models=ROOT.parent/'Models/InsightFace'
    for file in ['det_10g.onnx','1k3d68.onnx']:
        if not (models/'models/buffalo_l'/file).is_file():raise RuntimeError('Offline landmark weights missing')
    face_app=FaceAnalysis(name='buffalo_l',root=str(models),providers=['CPUExecutionProvider'],
                          allowed_modules=['detection','landmark_3d_68'])
    face_app.prepare(ctx_id=-1,det_size=(640,640),det_thresh=.45)
    if any(m.session.get_providers()!=['CPUExecutionProvider'] for m in face_app.models.values()):
        raise RuntimeError('CPU landmark execution required')
    cap=cv2.VideoCapture(str(media(run.state['qhdPath'])))
    landmarks=[]
    for global_index in range(53):
        ok,frame=cap.read()
        if not ok:raise RuntimeError('QHD decode failed')
        if global_index<5:continue
        index=global_index-5
        (FOLDER/'source-frames').mkdir(exist_ok=True)
        cv2.imwrite(str(FOLDER/'source-frames'/f'{index:03}.png'),frame)
        faces=face_app.get(cv2.resize(frame,(1280,720),interpolation=cv2.INTER_AREA))
        if len(faces)!=1:raise RuntimeError(f'Expected exactly one close-up face at {index}')
        points=faces[0].landmark_3d_68[:,:2]*2
        landmarks.append(points.tolist())
        mask,protected=skin_mask(frame,points)
        (FOLDER/'masks').mkdir(exist_ok=True)
        cv2.imwrite(str(FOLDER/'masks'/f'{index:03}.png'),mask)
        cv2.imwrite(str(FOLDER/'masks'/f'{index:03}-protected.png'),protected)
    cap.release()
    points=np.asarray(landmarks)
    lo=points.min(axis=(0,1));hi=points.max(axis=(0,1))
    center=(lo+hi)/2;center[1]-=(hi[1]-lo[1])*.16
    size=int(np.ceil(max(hi-lo)*1.35/8)*8)
    x=int(np.clip(round(center[0]-size/2),0,2560-size));y=int(np.clip(round(center[1]-size/2),0,1440-size))
    roi=[x,y,size,size]
    for index in run.state['keyframes']:
        frame=cv2.imread(str(FOLDER/'source-frames'/f'{index:03}.png'))
        mask=cv2.imread(str(FOLDER/'masks'/f'{index:03}.png'),cv2.IMREAD_GRAYSCALE)
        folder=FOLDER/'keys'/f'{index:03}'
        folder.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(folder/'input.png'),cv2.resize(frame[y:y+size,x:x+size],(768,768),interpolation=cv2.INTER_LANCZOS4))
        crop=cv2.resize(mask[y:y+size,x:x+size],(768,768),interpolation=cv2.INTER_LINEAR)
        cv2.imwrite(str(folder/'mask.png'),cv2.cvtColor(crop,cv2.COLOR_GRAY2BGR))
    write(FOLDER/'landmarks.json',dict(provider='CPUExecutionProvider',points=landmarks,roi=roi))
    run.save('ReadyForLocalSkinKeys',prepared=True,roi=roi,landmarkModel='buffalo_l/1k3d68.onnx')
    print(dict(roi=roi,keyframes=run.state['keyframes'],frames=48),flush=True)


def register(run):
    graph=read(ROOT.parent/'Workflows/realvisxl_book_reference_api.json')
    graph['2']['inputs']['text']='Close-up photograph of the same adult East Asian woman, natural unretouched facial skin, subtle fine skin texture, delicate pores, natural uneven skin tone, soft window daylight, preserve original face, age, expression and lighting'
    graph['3']['inputs']['text']='beauty filter, airbrushed, waxy skin, plastic, doll, harsh sharpening, gritty skin, freckles, new moles, wrinkles, different person, makeup change, lighting change, deformed face, oversaturated'
    graph['9']['inputs'].update(seed=2026102401,steps=32,cfg=3.5,sampler_name='dpmpp_2m',scheduler='karras',denoise=.24)
    graph['12']['inputs']['filename_prefix']='skin_pilot/key'
    path=ROOT.parent/'Workflows/realvisxl_skin_patch_768_api.json'
    if path.exists() and read(path)!=graph:raise RuntimeError('Existing skin workflow differs')
    write(path,graph)
    doc=read(ROOT/'config/workflow-contracts.json')
    contract=copy.deepcopy(next(c for c in doc['contracts'] if c['id']=='realvisxl-book-reference-1536-v1'))
    contract.update(id='realvisxl-skin-patch-768-v1',version='realvisxl-skin-patch-768-v1',fileName=path.name,
        media=dict(defaultWidth=768,defaultHeight=768,allowedDimensions=[dict(width=768,height=768)],nativeFps=1,
                   allowedFps=[],exactFrameCount=False,preserveAudio=False),
        notes='sha256='+sha(path)+' | Local skin-only low-denoise patch; original pixels protect eyes/lips/contour; not an identity replacement route.')
    matches=[c for c in doc['contracts'] if c['id']==contract['id']]
    if matches and matches!=[contract]:raise RuntimeError('Existing contract differs')
    if not matches:
        doc['contracts'].append(contract)
        write(ROOT/'config/workflow-contracts.json',doc)
    run.save(workflowVersion=contract['version'],workflowSha256=sha(path),modelSha256=contract['modelSha256'])
    print('Pinned local workflow registered; preview server restart required',flush=True)


def keys(run,attempt):
    if attempt not in [1,2,3]:raise RuntimeError('Initial plus at most two targeted repairs')
    run.access()
    if not run.state.get('projectId'):
        name='局部肤质跨帧稳定两秒_'+run.state['runId'][:8]
        matches=[p for p in run.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        elif run.state.get('projectStarted'):raise RuntimeError('Unresolved project creation')
        else:
            run.save(projectStarted=True)
            pid=run.api('/api/projects',dict(name=name,description='Offline skin-only two-second pilot; original voice and lip motion preserved.',defaultWidth=2560,defaultHeight=1440,defaultFps=24))['id']
        run.save(projectId=pid)
    wf=run.api('/api/workflows/scan',{},timeout=300)
    lookup=run.api('/api/workflows')
    workflow=next(w for w in lookup if w['name']=='realvisxl_skin_patch_768_api')
    for index in run.state['keyframes']:
        folder=FOLDER/'keys'/f'{index:03}'
        params=dict(workflowVersion=run.state['workflowVersion'],width=768,height=768,
                    inputSlots=dict(firstFrame=str((folder/'input.png').relative_to(DATA)),editMask=str((folder/'mask.png').relative_to(DATA))),
                    seed=2026102401,steps=32,cfg=3.5 if attempt==1 else 4.0,denoise=.24 if attempt==1 else .32)
        body=dict(projectId=run.state['projectId'],taskType='Image',resourceClass='GPU',workflowId=workflow['id'],
                  stage=f'Skin-Pilot-Key-{index:03}-Attempt-{attempt}',maxRetries=0,parameters=params)
        detail=once(run,f'key{index:03}Attempt{attempt}TaskId',body)
        path=result(detail,('.png','.jpg','.webp'))
        run.save(**{f'key{index:03}Attempt{attempt}Path':path})
    run.save('AwaitingPatchInspection',attempt=attempt)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['prepare','register','keys','check'],required=True)
    parser.add_argument('--attempt',type=int,default=1)
    args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    run=Run(API,FOLDER/'run.json')
    if args.stage=='check' or run.state.get('stage')=='ReadyForUserPreview':
        preserve(run);print('Preserved sources verified; no new task',flush=True);return
    if args.stage=='prepare':prepare(run)
    elif args.stage=='register':register(run)
    else:keys(run,args.attempt)


if __name__=='__main__':main()

"""Second, independent local validation. Old package and outputs remain read-only."""
from pathlib import Path
import sys, argparse, shutil, subprocess, json, importlib.util

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/visual_validation'))
_spec=importlib.util.spec_from_file_location('visual_validation_base',ROOT/'tools/visual_validation/run.py')
base=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(base)
FOLDER=ROOT.parent/'Data/VisualTargeted20261024'
base.FOLDER=FOLDER
read,write,sha,media,rel,DATA=base.read,base.write,base.sha,base.media,base.rel,base.DATA

class Run(base.Run):
    def preserve(self):
        super().preserve()
        for key,value in self.state.items():
            if key.endswith('Path') and isinstance(value,str) and self.state.get(key[:-4]+'Sha256'):
                if sha(media(value))!=self.state[key[:-4]+'Sha256']:raise RuntimeError('Frozen revision output changed: '+key)
        for candidate in self.state.get('blinkCandidates',[]):
            if sha(media(candidate['path']))!=candidate['sha256']:raise RuntimeError('Retained blink candidate changed')

def prepare(r):
    if r.state.get('prepared'):r.preserve();return
    old=read(DATA/'VisualValidation20261024/run.json')
    if not old.get('completed'):raise RuntimeError('Completed prior package required')
    fields=['actingPath','actingNewComparePath','qhdPath','h3ControlledPath','h3BaselinePath','keyframe5Path','driverPath']
    inputs={k:old[k] for k in fields}
    inputs.update(h3First='VisualValidation20261024/inputs/h3-first.png',h3Last='VisualValidation20261024/inputs/h3-last.png')
    frozen=[dict(path=v,sha256=sha(media(v))) for v in dict.fromkeys(list(inputs.values())+['VisualValidation20261024/run.json'])]
    inventory=[dict(path=str(p.relative_to(ROOT.parent/'Models')).replace('\\','/'),size=p.stat().st_size,mtimeNs=p.stat().st_mtime_ns) for p in (ROOT.parent/'Models').rglob('*') if p.is_file()]
    write(FOLDER/'model-inventory.json',dict(scope='size and mtime baseline, not all-model fresh SHA',files=inventory))
    for name in ['server/VisualActingService.cs','server/GenerationQueue.cs','server/TaskSubmissionPreflightService.cs']:
        dest=FOLDER/'backups'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=frozen,localInferenceOnly=True,maxTargetedRepairs=2)
    r.access()
    original=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');original.access()
    r.save(originalQueueStatus=original.api('/api/minimax/local/status')['queue'],pilotQueueStatus=r.api('/api/minimax/local/status')['queue'])
    original.api('/api/production/pause',{})
    name='画面定向修复小样_'+r.state['runId'][:8]
    r.save(projectCreationStarted=True)
    pid=r.api('/api/projects',dict(name=name,description='Local blink, H3 expression and source-detail preservation experiments; human review required.',defaultWidth=2560,defaultHeight=1440,defaultFps=24),key='project')['id']
    r.save(projectId=pid)
    r.api('/api/production/resume',{})

def h3(r):
    if r.state.get('h3RepairTaskIdInput'):body=r.state['h3RepairTaskIdInput']
    else:
        i=r.state['inputs']
        body=dict(projectId=r.state['projectId'],prompt=(
            'One continuous locked-off close-up, same woman and room throughout. The first four seconds show the exact same calm neutral CLOSED-LIP expression as the first picture. '
            'Her upper and lower lips stay gently touching in EVERY frame, including the middle of the shot. The mouth opening stays zero. '
            'Only during the final second, the corners of her STILL CLOSED lips lift a tiny amount to match the last picture. '
            'Keep her head position, face proportions, gaze, camera distance, crop, hair and background absolutely steady. Gentle breathing only. '
            'No talking, no teeth, no open mouth, no broad smile, no head turn, no camera movement. Audio: quiet room tone only, no speech or music.'),
            inputImagePath=i['h3First'],lastFramePath=i['h3Last'],firstFrameSha256=sha(media(i['h3First'])),lastFrameSha256=sha(media(i['h3Last'])),
            seed=2026102407,profile='firstlast480',steps=20)
    r.access();detail=r.once('h3RepairTaskId',body,endpoint='/api/minimax/local/video')
    path=base.result(detail,'.mp4');r.save('H3AwaitingInspection',h3RepairPath=path,h3RepairSha256=sha(media(path)))
    response=r.session.get('http://127.0.0.1:8188/history',timeout=30);response.raise_for_status()
    write(FOLDER/'h3-live-history.json',response.json())

def blink(r):
    i=r.state['inputs'];manifest=FOLDER/'blink-manifest-v1.json'
    value=dict(sourcePath=str(media(i['keyframe5Path'])),sourceSha256=sha(media(i['keyframe5Path'])),
        drivingPath=str(media(i['driverPath'])),drivingSha256=sha(media(i['driverPath'])),durationSeconds=2,drivingStartSeconds=0,
        animationRegion='all',drivingMultiplier=1,repairProfile='blink-residual-v1',eyeResidualGain=1.0,driverOrigin='Existing local generated task1293; not new human footage',
        licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
    if manifest.exists() and read(manifest)!=value:raise RuntimeError('Frozen blink manifest differs')
    if not manifest.exists():write(manifest,value)
    body=dict(projectId=r.state['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='Targeted-Blink-Residual-V1',
        parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile='blink-residual-v1',engineVersion=sha(ROOT/'tools/visual_targeted/blink.py')))
    r.access();detail=r.once('blinkTaskId',body);path=base.result(detail,'.mp4')
    receipt=next(x['assetPath'] for x in detail['results'] if x.get('available') and x.get('mimeType')=='application/json')
    r.save('BlinkAwaitingInspection',blinkPath=path,blinkSha256=sha(media(path)),blinkReceipt=receipt,
        blinkCandidates=[dict(taskId=r.state['blinkTaskId'],path=path,sha256=sha(media(path)))])

def normalize(r):
    body=dict(projectId=r.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Targeted-Blink-24FPS',
        parameters=dict(files=[r.state['blinkPath']],targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=2,originalAudioVolume=0,outputName='blink_repaired_24fps.mp4'))
    r.access();detail=r.once('blinkCompareTaskId',body);path=base.result(detail,'.mp4')
    r.save(blinkComparePath=path,blinkCompareSha256=sha(media(path)))

def detail(r):
    i=r.state['inputs'];manifest=FOLDER/'detail-manifest-v1.json'
    value=dict(profile='source-detail-residual-v1',strength=.65,sourcePath=str(media(i['actingNewComparePath'])),sourceSha256=sha(media(i['actingNewComparePath'])),
        restoredPath=str(media(i['qhdPath'])),restoredSha256=sha(media(i['qhdPath'])),maskEngineSha256=sha(ROOT/'tools/skin_pilot/pilot.py'))
    if manifest.exists() and read(manifest)!=value:raise RuntimeError('Frozen detail manifest differs')
    if not manifest.exists():write(manifest,value)
    body=dict(projectId=r.state['projectId'],taskType='VisualDetail',resourceClass='CPU',maxRetries=0,stage='Targeted-Source-Detail-V1',
        parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),engineVersion=sha(ROOT/'tools/visual_targeted/detail.py')))
    r.access();result=r.once('detailTaskId',body)
    paths={}
    for token,key in [('source_detail_recovered','detailPath'),('source_detail_baseline','detailBaselinePath')]:
        path=next(x['assetPath'] for x in result['results'] if x.get('available') and token in x.get('assetPath',''))
        paths[key]=path;paths[key[:-4]+'Sha256']=sha(media(path))
    paths['detailReceipt']=next(x['assetPath'] for x in result['results'] if x.get('available') and x.get('mimeType')=='application/json')
    r.save('AwaitingMediaReview',**paths)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','h3','blink','detail','normalize-blink','check'],required=True);args=p.parse_args()
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Completed package read-only');sys.exit(0)
    if args.stage=='prepare':prepare(r)
    elif args.stage=='h3':h3(r)
    elif args.stage=='blink':blink(r)
    elif args.stage=='detail':detail(r)
    elif args.stage=='normalize-blink':normalize(r)
    else:r.preserve();print('Frozen prior media verified; no submission')

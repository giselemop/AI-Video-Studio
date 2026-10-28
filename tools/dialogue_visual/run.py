"""Versioned ten-second dialogue, preserving exact audio and three-shot timing."""
from pathlib import Path
import sys,json,shutil,subprocess,argparse,importlib.util
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueVisual20261025'
spec=importlib.util.spec_from_file_location('dialogue_validation_base',ROOT/'tools/visual_validation/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.FOLDER=FOLDER
read,write,sha,media,rel=base.read,base.write,base.sha,base.media,base.rel
class Run(base.Run):
    def preserve(self):
        super().preserve()
        for k,v in self.state.items():
            if k.endswith('Path') and isinstance(v,str) and self.state.get(k[:-4]+'Sha256'):
                if sha(media(v))!=self.state[k[:-4]+'Sha256']:raise RuntimeError('Frozen dialogue version changed: '+k)

def prepare(r):
    if not r.state.get('prepared'):
        old=read(DATA/'FaceActing20261024/run.json');visual=read(DATA/'VisualValidation20261024/run.json');targeted=read(DATA/'VisualTargeted20261024/run.json')
        if old['stage']!='ReadyForUserPreview' or not targeted.get('completed'):raise RuntimeError('Completed prior versions required')
        inputs=dict(original=old['finalPath'],older=old['preserved'][0]['path'],femaleReference=visual['keyframe5Path'],maleReference='FaceActing20261024/reference-2.png',wideReference='FaceActing20261024/reference-3.png',
            driver1=old['shot1Attempt1Path'],driver2=old['shot2Attempt2Path'],driver3=old['shot3Attempt1Path'],subtitle='DialogueThreeShot20261023/audio/dialogue.srt')
        paths=list(inputs.values())+['FaceActing20261024/run.json','VisualTargeted20261024/run.json','VisualValidation20261024/run.json']
        records=[dict(path=p,sha256=sha(media(p))) for p in dict.fromkeys(paths)]
        inventory=[dict(path=str(p.relative_to(ROOT.parent/'Models')).replace('\\','/'),size=p.stat().st_size,mtimeNs=p.stat().st_mtime_ns) for p in (ROOT.parent/'Models').rglob('*') if p.is_file()]
        write(FOLDER/'model-inventory.json',dict(files=inventory,scope='Size/mtime baseline, not fresh complete hashes of all old weights'))
        r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=records,shots=old['shots'],cutFrames=[53,96],frameCount=240,fps=24,durationSeconds=10,
            localInferenceOnly=True,maxTargetedRepairs=2,femaleReferenceProvenance='Previously validated Klein K05 reused explicitly as reference, not newly generated in this run')
        for name in ['server/VisualActingService.cs','server/GenerationQueue.cs','server/TaskSubmissionPreflightService.cs']:
            p=FOLDER/'backups'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
    r.preserve();r.access()
    original=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');original.access()
    if 'originalQueueStatus' not in r.state:r.save(originalQueueStatus=original.api('/api/minimax/local/status')['queue'],pilotQueueStatus=r.api('/api/minimax/local/status')['queue'])
    original.api('/api/production/pause',{})
    if not r.state.get('projectId'):
        name='10秒对话画面升级_'+r.state['runId'][:8]
        matches=[p for p in r.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        else:
            if r.state.get('projectCreationStarted'):raise RuntimeError('Unresolved project creation; no duplicate')
            r.save(projectCreationStarted=True)
            pid=r.api('/api/projects',dict(name=name,description='Local three-shot dialogue from validated visual pipeline; preserve original audio/cuts; review only',defaultWidth=2560,defaultHeight=1440,defaultFps=24),key='project')['id']
        r.save(projectId=pid)
    r.api('/api/production/resume',{})

def keyframes(r):
    r.access();s=r.state
    for index,source,prompt in [(2,s['inputs']['maleReference'],
        'Edit this photograph of the exact same adult man. Preserve identity, face proportions, short dark hair, light stubble, olive cardigan, dark shirt, downward gaze, bowed head, camera angle, window lighting and room. Use a natural head-and-shoulders close-up with relaxed CLOSED lips and a neutral expression. Preserve realistic fine skin grain and hair detail, unretouched photograph. No text, no plastic skin, no new person.'),
        (3,s['inputs']['wideReference'],
        'Edit the supplied two-person photograph. Preserve exactly these TWO adult people, their separate identities, positions, head angles, hairstyles, clothes, hands, phone, sofa, room, camera and warm window lighting. The woman stays LEFT and the man stays RIGHT looking down at his phone. Both begin with relaxed CLOSED lips. Maintain the same wide two-shot composition. Refine natural fine skin texture and hair detail without changing facial structure. Photorealistic, unretouched, no text, no beauty filter, no extra people.')]:
        body=dict(projectId=s['projectId'],taskType='Image',resourceClass='GPU',workflowId=2135,inputImagePath=source,maxRetries=0,stage=f'Dialogue-Visual-Keyframe-{index}',
            parameters=dict(workflowVersion='flux2-klein4b-keyframe-local-1024-v2',width=1024,height=576,seed=2026102500+index,steps=4,cfg=1,prompt=prompt,inputSlots={'firstFrame':source}))
        result=r.once(f'keyframe{index}TaskId',body);path=base.result(result,'.png');r.save(**{f'keyframe{index}Path':path,f'keyframe{index}Sha256':sha(media(path))})
    r.save('AwaitingKeyframeInspection')
    response=r.session.get('http://127.0.0.1:8188/history',timeout=30);response.raise_for_status();write(FOLDER/'keyframe-live-history.json',response.json())

def act(r,attempt):
    r.access();s=r.state
    review=read(FOLDER/'keyframe-review.json')
    if review['status']!='SelectedForLocalPreview':raise RuntimeError('Inspect actual references first')
    for role,source,driver,direction,duration in [
        ('female',s['inputs']['femaleReference'],s['inputs']['driver1'],'large-small',57/25),
        ('male',s['keyframe2Path'],s['inputs']['driver2'],'large-small',46/25),
        ('wideFemale',s['wideSelectedPath'],s['inputs']['driver3'],'left-right',151/25),
        ('wideMale',s['wideSelectedPath'],s['inputs']['driver3'],'right-left',151/25)]:
        if s.get(role+'Path'):r.preserve();continue
        manifest=FOLDER/f'{role}-acting-v{attempt}.json'
        request=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),
            durationSeconds=duration,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,repairProfile='dialogue-blink-v1',eyeResidualGain=1,
            faceDirection=direction,driverOrigin='Existing self-generated same-dialogue native shot; not new human footage',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
        if manifest.exists() and read(manifest)!=request:raise RuntimeError('Frozen acting manifest differs')
        if not manifest.exists():write(manifest,request)
        body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage=f'Dialogue-Visual-{role}-V{attempt}',parameters=dict(
            manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile='dialogue-blink-v1',engineVersion=sha(ROOT/'tools/dialogue_visual/acting.py')))
        result=r.once(f'{role}A{attempt}TaskId',body);path=base.result(result,'.mp4')
        receipt=next(x['assetPath'] for x in result['results'] if x.get('available') and 'local_visual_acting_receipt' in x.get('assetPath',''))
        mask=next(x['assetPath'] for x in result['results'] if x.get('available') and 'dialogue_face_support' in x.get('assetPath',''))
        r.save(**{role+'Path':path,role+'Sha256':sha(media(path)),role+'ReceiptPath':receipt,role+'ReceiptSha256':sha(media(receipt)),role+'MaskPath':mask,role+'MaskSha256':sha(media(mask))})
    r.save('AwaitingNativeInspection')

def composite(r,field,manifest,values):
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen composition changed')
    if not manifest.exists():write(manifest,values)
    body=dict(projectId=r.state['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage=field,
        parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),engineVersion=sha(ROOT/'tools/dialogue_visual/compose.py')))
    result=r.once(field+'TaskId',body);path=base.result(result,'.mp4')
    receipt=next(x['assetPath'] for x in result['results'] if x.get('available') and 'dialogue_composition_receipt' in x.get('assetPath',''))
    r.save(**{field+'Path':path,field+'Sha256':sha(media(path)),field+'ReceiptPath':receipt,field+'ReceiptSha256':sha(media(receipt))})

def canvases(r):
    r.access();s=r.state
    files={}
    def bind(role,p):files[role]=dict(path=str(media(p)),sha256=sha(media(p)))
    bind('source',s['wideSelectedPath'])
    for label,role in [('left','wideFemale'),('right','wideMale')]:
        for suffix,target in [('',label),('Receipt',label+'Receipt'),('Mask',label+'Mask')]:bind(target,s[role+suffix+'Path'])
    composite(r,'wideMerge',FOLDER/'wide-merge-v1.json',dict(profile='dialogue-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=151,files=files))
    for index,source,frames in [(1,s['femalePath'],53),(2,s['malePath'],43),(3,s['wideMergePath'],144)]:
        body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage=f'Dialogue-Visual-Shot-{index}-24FPS',
            parameters=dict(files=[source],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=frames/24,originalAudioVolume=0,outputName=f'dialogue_visual_shot_{index}_720p.mp4'))
        result=r.once(f'canvas{index}TaskId',body);path=base.result(result,'.mp4');r.save(**{f'canvas{index}Path':path,f'canvas{index}Sha256':sha(media(path))})
    r.save('AwaitingCanvasInspection')

def restore(r,index):
    r.access();s=r.state
    if read(FOLDER/'native-review.json')['status']!='SelectedForQhd':raise RuntimeError('Inspect native takes before long restore')
    status=r.api('/api/video-restore/status')
    if not status['ready']:raise RuntimeError(status['message'])
    source=s[f'canvas{index}Path']
    body=dict(projectId=s['projectId'],taskType='VideoRestore',resourceClass='GPU',maxRetries=0,stage=f'Dialogue-Visual-Shot-{index}-QHD',
        parameters=dict(input=source,sourceSha256=sha(media(source)),engineVersion=status['engineVersion'],strength=.3,cutFrames=[],outputProfile='qhd1440',targetWidth=2560,targetHeight=1440))
    result=r.once(f'qhd{index}TaskId',body);path=base.result(result,'.mp4');r.save(**{f'qhd{index}Path':path,f'qhd{index}Sha256':sha(media(path))})

def detail(r,index):
    r.access();s=r.state;files={}
    for role,key in [('source',f'canvas{index}Path'),('restored',f'qhd{index}Path')]:
        p=s[key];files[role]=dict(path=str(media(p)),sha256=sha(media(p)))
    frames={1:53,2:43,3:144}[index]
    composite(r,f'detail{index}',FOLDER/f'detail-shot-{index}-v1.json',dict(profile='dialogue-compose-v1',phase='detail',width=2560,height=1440,fps=24,frames=frames,
        strength=.65,expectedFaces=2 if index==3 else 1,maskEngineSha256=sha(ROOT/'tools/skin_pilot/pilot.py'),files=files))

def assemble(r):
    r.access();s=r.state
    if not s.get('singlePassCaptionBuildReady'):
        r.save('AwaitingFinalAssemblyBuild');print('All shots retained; await tested single-pass caption build before final assembly');return
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Dialogue-Visual-10s-Subtitled-Picture',
        parameters=dict(files=[s[f'detail{i}Path'] for i in [1,2,3]],singlePass=True,targetWidth=2560,targetHeight=1440,targetFps=24,targetDurationSeconds=10,
            originalAudioVolume=0,subtitlePath=s['inputs']['subtitle'],outputName='dialogue_visual_10s_picture.mp4'))
    result=r.once('pictureTaskId',body);path=base.result(result,'.mp4');r.save(picturePath=path,pictureSha256=sha(media(path)))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Dialogue-Visual-Original-Audio-Packets',
        parameters=dict(files=[s['picturePath']],videoSha256=s['pictureSha256'],audioStreamCopyFrom=s['inputs']['original'],audioStreamCopySha256=sha(media(s['inputs']['original'])),outputName='dialogue_visual_same_voice_2k_10s.mp4'))
    result=r.once('finalTaskId',body);path=base.result(result,'.mp4');r.save('AwaitingFinalInspection',finalPath=path,finalSha256=sha(media(path)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','keyframes','act','canvases','restore','detail','assemble','check'],required=True);p.add_argument('--index',type=int,choices=[1,2,3],default=1);p.add_argument('--attempt',type=int,choices=[1,2],default=1);args=p.parse_args()
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Completed dialogue version is read-only');sys.exit(0)
    if args.stage=='prepare':prepare(r)
    elif args.stage=='keyframes':keyframes(r)
    elif args.stage=='act':act(r,args.attempt)
    elif args.stage=='canvases':canvases(r)
    elif args.stage=='restore':restore(r,args.index)
    elif args.stage=='detail':detail(r,args.index)
    elif args.stage=='assemble':assemble(r)
    else:r.preserve();print('Frozen prior dialogue verified, no task submitted')

"""Additive local audio-driven mouth/response pilot; all production via queue."""
from pathlib import Path
import sys,json,subprocess,shutil,importlib.util,argparse,copy,math
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueSync20261025'
spec=importlib.util.spec_from_file_location('sync_validation_base',ROOT/'tools/visual_validation/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.FOLDER=FOLDER
read,write,sha,media,rel=base.read,base.write,base.sha,base.media,base.rel
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
CLIPS=[dict(name='close',index=1,startFrame=5,frames=48,nativeFrames=51,source='femaleReference',roles=['female']),
       dict(name='wide',index=3,startFrame=150,frames=54,nativeFrames=57,source='wideReference',roles=['female','male'])]
class Run(base.Run):
    def preserve(self):
        super().preserve()
        for name in ['prepared-inputs.json','hybrid-inputs.json']:
            frozen=FOLDER/name
            if frozen.exists():
                for item in read(frozen)['files']:
                    if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Prepared excerpt input changed')
        for k,v in self.state.items():
            if k.endswith('Path') and isinstance(v,str) and self.state.get(k[:-4]+'Sha256'):
                if sha(media(v))!=self.state[k[:-4]+'Sha256']:raise RuntimeError('Frozen pilot asset changed: '+k)

def asset(r,key,detail,suffix='.mp4'):
    path=base.result(detail,suffix);r.save(**{key+'Path':path,key+'Sha256':sha(media(path))});return path

def prepare(r):
    r.access();old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
    q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Inspect existing jobs; never duplicate or interrupt them')
    if not r.state.get('prepared'):
        previous=read(DATA/'DialogueVisual20261025/run.json')
        if not previous.get('completed'):raise RuntimeError('Completed ten-second baseline required')
        inputs=dict(original=previous['finalPath'],femaleReference=previous['inputs']['femaleReference'],wideReference=previous['wideSelectedPath'],
                    femaleAudio='DialogueThreeShot20261023/audio/female-10s.wav',maleAudio='DialogueThreeShot20261023/audio/male-10s.wav',
                    subtitle=previous['inputs']['subtitle'])
        paths=list(inputs.values())+['DialogueVisual20261025/run.json']
        for key,value in previous.items():
            if key.endswith('Path') and isinstance(value,str) and previous.get(key[:-4]+'Sha256'):paths.append(value)
        records=[dict(path=p,sha256=sha(media(p))) for p in dict.fromkeys(paths)]
        inventory=[dict(path=str(p.relative_to(ROOT.parent/'Models')).replace('\\','/'),size=p.stat().st_size,mtimeNs=p.stat().st_mtime_ns)
                   for p in (ROOT.parent/'Models').rglob('*') if p.is_file()]
        write(FOLDER/'model-inventory.json',dict(scope='Existing files size/mtime; no model downloads',files=inventory))
        backup=FOLDER/'workflow-contracts-before.json';shutil.copy2(ROOT/'config/workflow-contracts.json',backup)
        health=old.api('/api/health');stats=r.session.get('http://127.0.0.1:8188/system_stats',timeout=15).json()
        write(FOLDER/'initial-environment.json',dict(health=health,comfy=stats,activeTasks=[],comfyIdle=True))
        (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short','--branch'],cwd=ROOT,text=True),encoding='utf-8')
        r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=records,clips=CLIPS,originalQueueStatus=old.api('/api/minimax/local/status')['queue'],
               pilotQueueStatus=r.api('/api/minimax/local/status')['queue'],localInferenceOnly=True,maxTargetedRepairs=2,
               scope='Two short excerpts; no replacement of ten-second baseline; audio guidance2 with existing Lightx2v')
    r.preserve();old.api('/api/production/pause',{});r.api('/api/production/resume',{})
    if not r.state.get('projectId'):
        name='口型与双人表情小样_'+r.state['runId'][:8];matches=[p for p in r.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        else:
            if r.state.get('projectStarted'):raise RuntimeError('Unresolved project creation')
            r.save(projectStarted=True);pid=r.api('/api/projects',dict(name=name,description='Local mouth synchronization and two-person response pilot; preserve project40; review only',defaultWidth=1280,defaultHeight=720,defaultFps=24),key='project')['id']
        r.save(projectId=pid)
    # CPU-only detection positions the left/right speaker split, never identifies people.
    import cv2
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection']);app.prepare(ctx_id=-1,det_size=(640,640))
    image=cv2.imread(str(media(r.state['inputs']['wideReference'])));faces=sorted(app.get(image),key=lambda f:f.bbox[0])
    if len(faces)!=2:raise RuntimeError('Two-person source roles cannot be localized')
    centres=[float((f.bbox[0]+f.bbox[2])/2/image.shape[1]) for f in faces];split=sum(centres)/2
    if not .1<split<.9 or faces[0].bbox[2]>=split*image.shape[1] or faces[1].bbox[0]<=split*image.shape[1]:raise RuntimeError('Speaker split crosses a face')
    write(FOLDER/'speaker-region-check.json',dict(status='Passed',source=r.state['inputs']['wideReference'],sourceSha256=sha(media(r.state['inputs']['wideReference'])),centres=centres,splitRatio=split,roles=['female-left','male-right'],scope='Spatial binding only; no identity score'))
    for clip in CLIPS:
        for role in ['female','male']:
            path=FOLDER/f"{clip['name']}-{role}-native.wav"
            if not path.exists():subprocess.run([FFMPEG,'-nostdin','-v','error','-ss',str(clip['startFrame']/24),'-i',str(media(r.state['inputs'][role+'Audio'])),'-t',str(clip['nativeFrames']/25),'-c:a','pcm_s24le',str(path)],check=True)
        # Original subtitles are retimed by exact excerpt offset, not rewritten.
        import re
        def stamp(t):
            ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000)
            return f'{h:02}:{m:02}:{sec:02},{ms:03}'
        def seconds(v):
            h,m,tail=v.split(':');sec,ms=tail.split(',');return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
        captions=[];start=clip['startFrame']/24;end=start+clip['frames']/24
        for block in media(r.state['inputs']['subtitle']).read_text(encoding='utf-8-sig').strip().split('\n\n'):
            lines=block.splitlines();a,b=lines[1].split(' --> ');a,b=seconds(a),seconds(b)
            if b>start and a<end:captions.append(f'{len(captions)+1}\n{stamp(max(a,start)-start)} --> {stamp(min(b,end)-start)}\n'+ '\n'.join(lines[2:]))
        caption=FOLDER/f"{clip['name']}.srt";text='\n\n'.join(captions)+'\n'
        if caption.exists() and caption.read_text(encoding='utf-8')!=text:raise RuntimeError('Frozen caption differs')
        caption.write_text(text,encoding='utf-8')
    r.save('Prepared',splitRatio=split)

def register(r):
    r.access();r.preserve();doc=read(ROOT/'config/workflow-contracts.json');before=sha(ROOT/'config/workflow-contracts.json');rows=[]
    for clip in CLIPS:
        name=clip['name'];graph=read(ROOT.parent/f"Workflows/face_acting_shot_{clip['index']}_v1_api.json")
        template=copy.deepcopy(next(c for c in doc['contracts'] if c['id']==f"face-acting-shot-{clip['index']}-v1"))
        graph['7']['inputs'].update(num_frames=clip['nativeFrames'],audio_cfg_scale=2.0,audio_scale=.95)
        graph['14']['inputs'].update(frame_window_size=57,motion_frame=9)
        graph['19']['inputs']['length']=clip['nativeFrames'];graph['15']['inputs'].update(steps=8,cfg=1.0,seed=2026102507+clip['index'])
        graph['18']['inputs']['filename_prefix']='dialogue_sync/'+name
        if name=='wide':
            graph['4']['inputs']['split_ratio']=r.state['splitRatio']
            graph['5']['inputs']['positive']='Photorealistic two-shot of exactly the woman LEFT and man RIGHT from the reference, same sofa, clothes and window light. The man gives his brief Mandarin reply according to ONLY his own audio, with small precise lips and relaxed jaw. A slight satisfied expression develops gradually then settles, no fixed grin. The woman listens silently throughout this excerpt, with gently touching lips, a subtle responsive look and quiet breathing. Both keep small coordinated cheek and eyebrow changes, softly held gaze and continuous gentle head motion. Restrained believable performance, no broad smile, static camera. Preserve their separate identities, phone, hands, room and positions.'
        else:
            graph['5']['inputs']['positive']='Photorealistic close-up of the exact same woman in the reference, same beige cardigan and warm window light. She speaks her Mandarin audio naturally, with precise small consonant closures, rounded vowels and a relaxed jaw. Subtle teasing warmth, small coherent cheek and brow changes. Lips settle gently after speaking. Keep the original face proportions and gaze to screen right, restrained continuous performance, no fixed smile, no exaggerated mouth opening, static camera.'
        graph['5']['inputs']['negative']+=', excessive jaw opening, fixed smile, listener talking, frozen eyebrows, twitching cheeks, sudden expression change'
        version='dialogue-sync-'+name+'-i2v-v2';path=ROOT.parent/('Workflows/'+version.replace('-','_')+'_api.json')
        template.update(id=version,version=version,fileName=path.name,notes='sha256=PLACEHOLDER | Existing weights; audio_cfg2, native aligned excerpt, pose-matched source and bounded natural response; review only')
        template['media'].update(outputFrames=[clip['nativeFrames']],exactFrameCount=True)
        payload=(json.dumps(graph,ensure_ascii=False,indent=2)+'\n').encode();import hashlib
        template['notes']=template['notes'].replace('PLACEHOLDER',hashlib.sha256(payload).hexdigest())
        if path.exists() and path.read_bytes()!=payload:raise RuntimeError('Existing graph differs; create new version')
        matches=[c for c in doc['contracts'] if c['id']==version or c['fileName']==path.name]
        if matches and matches!=[template]:raise RuntimeError('Existing contract differs')
        if not matches:doc['contracts'].append(template)
        if not path.exists():path.write_bytes(payload)
        rows.append(dict(name=name,version=version,fileName=path.name,sha256=sha(path),frames=clip['nativeFrames']))
    if sha(ROOT/'config/workflow-contracts.json')!=before:raise RuntimeError('Concurrent contract edit; preserve it')
    write(ROOT/'config/workflow-contracts.json',doc);r.api('/api/workflows/scan',{},timeout=600)
    workflows=r.api('/api/workflows')
    for row in rows:
        matches=[w for w in workflows if w.get('name')==Path(row['fileName']).stem]
        if len(matches)!=1:raise RuntimeError('Registered workflow not uniquely available')
        row['workflowId']=matches[0]['id']
    r.save('Registered',workflows=rows)

def baseline(r,clip):
    r.access();s=r.state;name=clip['name']
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Baseline-'+name,parameters=dict(files=[s['inputs']['original']],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,trimStartSeconds=clip['startFrame']/24,targetDurationSeconds=clip['frames']/24,originalAudioVolume=1,outputName=name+'_baseline.mp4'))
    return asset(r,name+'Baseline',r.once(name+'BaselineTaskId',body))

def generate(r,clip):
    r.access();s=r.state;name=clip['name'];wf=next(x for x in s['workflows'] if x['name']==name)
    slots=dict(firstFrame=s['inputs'][clip['source']])
    if name=='close':slots['speakerAudio']=rel(FOLDER/(name+'-female-native.wav'))
    else:slots.update(femaleAudio=rel(FOLDER/(name+'-female-native.wav')),maleAudio=rel(FOLDER/(name+'-male-native.wav')))
    body=dict(projectId=s['projectId'],taskType='ImageToVideo',resourceClass='GPU',workflowId=wf['workflowId'],inputImagePath=slots['firstFrame'],maxRetries=0,stage='Sync-Audio-Driver-'+name,
              parameters=dict(workflowVersion=wf['version'],width=832,height=480,fps=25,frames=clip['nativeFrames'],duration=clip['nativeFrames']/25,steps=8,cfg=1,seed=2026102507+clip['index'],inputSlots=slots))
    asset(r,name+'Driver',r.once(name+'DriverTaskId',body));r.save('AwaitingDriverInspection')

def free(r,clip):
    import psutil,time
    r.access();r.preserve();active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
    q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Never free Comfy models while jobs are active')
    peaks=[read(media(v)).get('peakReservedMiB',0) for k,v in r.state.items() if k.endswith('ReceiptPath') and isinstance(v,str) and ('Female' in k or 'Male' in k)]
    observed=max(peaks,default=0);required=max(4096,math.ceil(observed)+2048)
    def memory():
        values=[int(x.strip()) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free','--format=csv,noheader,nounits'],text=True).strip().split(',')]
        return dict(deviceUsedMiB=values[0],deviceFreeMiB=values[1],availableRamMiB=psutil.virtual_memory().available//1024**2)
    before=memory();response=r.session.post('http://127.0.0.1:8188/free',json=dict(unload_models=True,free_memory=True),timeout=30);response.raise_for_status()
    for _ in range(20):
        after=memory()
        if after['deviceFreeMiB']>=required and after['availableRamMiB']>=6144:break
        time.sleep(1)
    target=FOLDER/'idle-cache-release.json';index=2
    while target.exists():target=FOLDER/f'idle-cache-release-{index}.json';index+=1
    write(target,dict(status='Passed' if after['deviceFreeMiB']>=required and after['availableRamMiB']>=6144 else 'Blocked',before=before,after=after,requiredFreeDeviceMiB=required,observedPortraitPeakReservedMiB=observed,
        reserveRule='At least4GiB or measured portrait peak plus2GiB margin; portrait-stage gate only',queueIdleChecked=True,historyPreserved=True,modelsDeleted=0))
    if after['deviceFreeMiB']<required or after['availableRamMiB']<6144:raise RuntimeError('Idle memory release insufficient; inspect without duplicate GPU submission')
    print('Passed: idle Comfy free request complete; measured portrait memory headroom validated; no model files/history removed')

def act(r,clip):
    r.access();r.preserve();s=r.state;name=clip['name']
    if read(FOLDER/'driver-review.json')['status']!='SelectedForActing':raise RuntimeError('Inspect actual audio drivers first')
    for role in clip['roles']:
        key=name+role.title();source=s['inputs'][clip['source']];driver=s[name+'DriverPath']
        if s.get(key+'Path'):r.preserve();continue
        manifest=FOLDER/(key+'-acting.json')
        values=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),
            durationSeconds=clip['nativeFrames']/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,
            repairProfile='dialogue-blink-v1',eyeResidualGain=1,faceDirection='large-small' if name=='close' else 'left-right' if role=='female' else 'right-left',
            driverOrigin='Fresh local audio-conditioned InfiniteTalk pilot; original separated voice excerpt; not human performance footage',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
        if manifest.exists() and read(manifest)!=values:raise RuntimeError('Acting request differs')
        if not manifest.exists():write(manifest,values)
        body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='Sync-Acting-'+key,parameters=dict(
            manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile='dialogue-blink-v1',engineVersion=sha(ROOT/'tools/dialogue_visual/acting.py')))
        result=r.once(key+'TaskId',body);asset(r,key,result)
        for suffix,needle in [('Receipt','local_visual_acting_receipt'),('Mask','dialogue_face_support')]:
            path=next(x['assetPath'] for x in result['results'] if x.get('available') and needle in x.get('assetPath',''));r.save(**{key+suffix+'Path':path,key+suffix+'Sha256':sha(media(path))})
    r.save('ActingReady')

def composite(r,key,values):
    manifest=FOLDER/(key+'-composition.json')
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen short composition differs')
    if not manifest.exists():write(manifest,values)
    profile=values['profile'];script='hybrid_compose.py' if profile=='dialogue-hybrid-compose-v1' else 'compose.py'
    body=dict(projectId=r.state['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage='Sync-'+key,parameters=dict(
        compositionProfile=profile,manifest=rel(manifest),manifestSha256=sha(manifest),engineVersion=sha(ROOT/'tools/dialogue_sync'/script)))
    result=r.once(key+'TaskId',body);asset(r,key,result)
    receipt=next(x['assetPath'] for x in result['results'] if x.get('available') and 'dialogue_composition_receipt' in x.get('assetPath',''));r.save(**{key+'ReceiptPath':receipt,key+'ReceiptSha256':sha(media(receipt))})

def canvas(r,clip):
    r.access();r.preserve();s=r.state;name=clip['name']
    if s.get(name+'CanvasPath'):r.preserve();print('Selected canvas retained; no duplicate');return
    if name=='wide':
        files={}
        def bind(role,key):
            path=s[key];files[role]=dict(path=str(media(path)),sha256=sha(media(path)))
        path=s['inputs']['wideReference'];files['source']=dict(path=str(media(path)),sha256=sha(media(path)))
        for label,role in [('left','Female'),('right','Male')]:
            for suffix,target in [('',label),('Receipt',label+'Receipt'),('Mask',label+'Mask')]:bind(target,'wide'+role+suffix+'Path')
        composite(r,'wideMerge',dict(profile='dialogue-sync-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=57,files=files))
        source=s['wideMergePath']
    else:source=s['closeFemalePath']
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Canvas-'+name,parameters=dict(files=[source],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=clip['frames']/24,originalAudioVolume=0,outputName=name+'_canvas.mp4'))
    asset(r,name+'Canvas',r.once(name+'CanvasTaskId',body));r.save('AwaitingNativeInspection')

def restore(r,clip):
    r.access();s=r.state;name=clip['name']
    if read(FOLDER/'native-review.json')['status']!='SelectedForQhd':raise RuntimeError('Inspect actual new performance first')
    status=r.api('/api/video-restore/status')
    if not status['ready']:raise RuntimeError(status['message'])
    path=s[name+'CanvasPath'];body=dict(projectId=s['projectId'],taskType='VideoRestore',resourceClass='GPU',maxRetries=0,stage='Sync-QHD-'+name,parameters=dict(input=path,sourceSha256=sha(media(path)),engineVersion=status['engineVersion'],strength=.3,cutFrames=[],outputProfile='qhd1440',targetWidth=2560,targetHeight=1440))
    asset(r,name+'Qhd',r.once(name+'QhdTaskId',body))

def detail(r,clip):
    r.access();s=r.state;name=clip['name'];files={}
    for role,suffix in [('source','Canvas'),('restored','Qhd')]:
        path=s[name+suffix+'Path'];files[role]=dict(path=str(media(path)),sha256=sha(media(path)))
    profile='dialogue-hybrid-compose-v1' if name=='wide' and s.get('wideHybridSelected') else 'dialogue-sync-compose-v1'
    composite(r,name+'Detail',dict(profile=profile,phase='detail',width=2560,height=1440,fps=24,frames=clip['frames'],strength=.65,expectedFaces=len(clip['roles']),maskEngineSha256=sha(ROOT/'tools/skin_pilot/pilot.py'),files=files))

def assemble(r,clip):
    r.access();s=r.state;name=clip['name'];caption=FOLDER/(name+'.srt')
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Picture-'+name,parameters=dict(files=[s[name+'DetailPath']],singlePass=True,targetWidth=2560,targetHeight=1440,targetFps=24,targetDurationSeconds=clip['frames']/24,originalAudioVolume=0,subtitlePath=rel(caption),outputName=name+'_picture.mp4'))
    asset(r,name+'Picture',r.once(name+'PictureTaskId',body))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Original-Excerpt-Voice-'+name,parameters=dict(files=[s[name+'PicturePath']],videoSha256=s[name+'PictureSha256'],audioStreamCopyFrom=s[name+'BaselinePath'],audioStreamCopySha256=s[name+'BaselineSha256'],allowResolutionDifference=True,outputName=name+'_sync_same_voice.mp4'))
    asset(r,name+'Final',r.once(name+'FinalTaskId',body));r.save('AwaitingFinalInspection')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','register','baseline','generate','free','act','canvas','restore','detail','assemble','check'],required=True);p.add_argument('--clip',choices=['close','wide'],default='close');a=p.parse_args()
    FOLDER.mkdir(exist_ok=True);r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed') or a.stage=='check':r.preserve();print('Preserved; no new tasks');sys.exit(0)
    if a.stage=='prepare':prepare(r)
    elif a.stage=='register':register(r)
    else:globals()[a.stage](r,next(x for x in CLIPS if x['name']==a.clip))

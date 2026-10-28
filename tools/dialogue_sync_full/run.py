"""Full ten-second local revision from accepted mouth/pose pilot; real queue only."""
from pathlib import Path
import sys,json,subprocess,shutil,importlib.util,argparse,copy,math
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueSyncFull20261025'
spec=importlib.util.spec_from_file_location('sync_full_base',ROOT/'tools/visual_validation/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.FOLDER=FOLDER
read,write,sha,media,rel=base.read,base.write,base.sha,base.media,base.rel
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
SHOTS=[dict(index=1,start=0,frames=53,native=57,source='femaleReference',roles=['female']),dict(index=2,start=53,frames=43,native=46,source='maleReference',roles=['male']),dict(index=3,start=96,frames=144,native=151,source='wideReference',roles=['female','male'])]
class Run(base.Run):
    def preserve(self):
        super().preserve()
        for k,v in self.state.items():
            if k.endswith('Path') and isinstance(v,str) and self.state.get(k[:-4]+'Sha256') and sha(media(v))!=self.state[k[:-4]+'Sha256']:raise RuntimeError('Frozen full-version file changed: '+k)
        p=FOLDER/'prepared-inputs.json'
        if p.exists():
            for item in read(p)['files']:
                if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Frozen prepared input changed')
        recovery=self.state.get('driver3RecoveryTaskIdInput',{}).get('parameters')
        if recovery and (sha(media(recovery['files'][0]))!=recovery['videoSha256'] or sha(media(recovery['audioStreamCopyFrom']))!=recovery['audioStreamCopySha256']):raise RuntimeError('Original recovered Comfy input changed')

def asset(r,key,detail):
    path=base.result(detail,'.mp4');r.save(**{key+'Path':path,key+'Sha256':sha(media(path))});return path

def prepare(r):
    r.access();old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
    q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Inspect existing jobs; never interrupt or duplicate')
    if not r.state.get('prepared'):
        visual=read(DATA/'DialogueVisual20261025/run.json');pilot=read(DATA/'DialogueSync20261025/run.json')
        if not visual.get('completed') or not pilot.get('completed') or not pilot.get('wideHybridSelected'):raise RuntimeError('Completed accepted pilot required')
        inputs=dict(original=visual['finalPath'],femaleReference=visual['inputs']['femaleReference'],maleReference=visual['keyframe2Path'],wideReference=visual['wideSelectedPath'],pose=visual['inputs']['driver3'],subtitle=visual['inputs']['subtitle'],femaleAudio='DialogueThreeShot20261023/audio/female-10s.wav',maleAudio='DialogueThreeShot20261023/audio/male-10s.wav')
        paths=list(inputs.values())+['DialogueVisual20261025/run.json','DialogueSync20261025/run.json']
        for state in [visual,pilot]:
            paths += [v for k,v in state.items() if k.endswith('Path') and isinstance(v,str) and state.get(k[:-4]+'Sha256')]
        records=[dict(path=p,sha256=sha(media(p))) for p in dict.fromkeys(paths)]
        inventory=[dict(path=str(p.relative_to(ROOT.parent/'Models')).replace('\\','/'),size=p.stat().st_size,mtimeNs=p.stat().st_mtime_ns) for p in (ROOT.parent/'Models').rglob('*') if p.is_file()]
        write(FOLDER/'model-inventory.json',dict(files=inventory,scope='Existing model set/size/mtime; no new downloads'))
        write(FOLDER/'initial-environment.json',dict(health=old.api('/api/health'),comfy=r.session.get('http://127.0.0.1:8188/system_stats',timeout=15).json(),activeTasks=[],comfyIdle=True))
        (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short','--branch'],cwd=ROOT,text=True),encoding='utf-8')
        r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=records,shots=SHOTS,cutFrames=[53,96],frameCount=240,fps=24,durationSeconds=10,originalQueueStatus=old.api('/api/minimax/local/status')['queue'],pilotQueueStatus=r.api('/api/minimax/local/status')['queue'],localInferenceOnly=True,maxTargetedRepairs=2,method='Accepted audio CFG2/portrait blink protection; full wide uses fresh audio mouth and approved original1299 pose. Existing wide source1328 is the original full-shot initial reference, not the pilot mid-shot frame. Static body/background outside face supports.')
    r.preserve();old.api('/api/production/pause',{});r.api('/api/production/resume',{})
    if not r.state.get('projectId'):
        name='完整10秒口型与双人回应_'+r.state['runId'][:8];matches=[p for p in r.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        else:
            if r.state.get('projectStarted'):raise RuntimeError('Unresolved project creation; no duplicate')
            r.save(projectStarted=True);pid=r.api('/api/projects',dict(name=name,description='Full10s accepted dialogue sync method; preserve original audio/subtitles/cuts and prior versions; review only',defaultWidth=2560,defaultHeight=1440,defaultFps=24),key='project')['id']
        r.save(projectId=pid)
    files=[]
    for shot in SHOTS:
        for role in ['female','male']:
            p=FOLDER/f"shot-{shot['index']}-{role}.wav"
            if not p.exists():subprocess.run([FFMPEG,'-nostdin','-v','error','-n','-ss',str(shot['start']/24),'-i',str(media(r.state['inputs'][role+'Audio'])),'-af',f"atrim=duration={shot['frames']/24},apad=whole_dur={shot['native']/25},atrim=duration={shot['native']/25}",'-c:a','pcm_s24le',str(p)],check=True)
            files.append(dict(path=rel(p),sha256=sha(p)))
    # Freeze actual current full-shot speaker split; same reference as the accepted pilot's audio driver.
    pilot=read(DATA/'DialogueSync20261025/run.json')
    if sha(media(r.state['inputs']['wideReference']))!=sha(media(pilot['inputs']['wideReference'])):raise RuntimeError('Speaker reference changed')
    prepared=dict(status='Passed',files=files,operation='Exact per-shot original dry voice slice; pad silence only after original cut; no audio time shift or resynthesis')
    p=FOLDER/'prepared-inputs.json'
    if p.exists() and read(p)!=prepared:raise RuntimeError('Prepared input drift')
    write(p,prepared);r.save('Prepared',splitRatio=pilot['splitRatio'])

def register(r):
    r.preserve();doc=read(ROOT/'config/workflow-contracts.json');before=sha(ROOT/'config/workflow-contracts.json');rows=[]
    pilot=read(DATA/'DialogueSync20261025/run.json')
    for shot in SHOTS:
        i=shot['index'];graph=read(ROOT.parent/f'Workflows/face_acting_shot_{i}_v1_api.json')
        contract=copy.deepcopy(next(c for c in doc['contracts'] if c['id']==f'face-acting-shot-{i}-v1'))
        graph['7']['inputs'].update(num_frames=shot['native'],audio_cfg_scale=2.0,audio_scale=.95)
        graph['14']['inputs'].update(frame_window_size=57,motion_frame=9);graph['19']['inputs']['length']=shot['native']
        graph['15']['inputs'].update(steps=8,cfg=1,seed=2026102510+i);graph['18']['inputs']['filename_prefix']=f'dialogue_sync_full/shot{i}'
        if i in [1,3]:
            prior=next(x for x in pilot['workflows'] if x['name']==('close' if i==1 else 'wide'));approved=read(ROOT.parent/'Workflows'/prior['fileName']);graph['5']['inputs']=copy.deepcopy(approved['5']['inputs'])
        else:graph['5']['inputs']['positive']+=' Precise small consonant closures, rounded vowels, relaxed jaw, restrained coherent cheek and eyebrow motion; close lips gently after his own line.'
        if i==3:graph['4']['inputs']['split_ratio']=r.state['splitRatio']
        version=f'dialogue-sync-full-shot-{i}-i2v-v1';path=ROOT.parent/('Workflows/'+version.replace('-','_')+'_api.json')
        payload=(json.dumps(graph,ensure_ascii=False,indent=2)+'\n').encode();import hashlib
        contract.update(id=version,version=version,fileName=path.name,notes='sha256='+hashlib.sha256(payload).hexdigest()+' | Full accepted sync method; original per-shot dry voice; existing weights; audioCFG2; review only')
        contract['media'].update(outputFrames=[shot['native']],exactFrameCount=True)
        matches=[c for c in doc['contracts'] if c['id']==version or c['fileName']==path.name]
        if matches and matches!=[contract]:raise RuntimeError('Registered full contract differs')
        if path.exists() and path.read_bytes()!=payload:raise RuntimeError('Existing full graph differs')
        if not path.exists():path.write_bytes(payload)
        if not matches:doc['contracts'].append(contract)
        rows.append(dict(index=i,version=version,fileName=path.name,sha256=sha(path)))
    if sha(ROOT/'config/workflow-contracts.json')!=before:raise RuntimeError('Concurrent contract change')
    write(ROOT/'config/workflow-contracts.json',doc);r.save('ContractsRegistered',workflows=rows)

def scan(r):
    r.access();r.api('/api/workflows/scan',{},timeout=600);workflows=r.api('/api/workflows');rows=copy.deepcopy(r.state['workflows'])
    for row in rows:
        found=[w for w in workflows if w['name']==Path(row['fileName']).stem]
        if len(found)!=1:raise RuntimeError('Workflow registration not unique')
        row['workflowId']=found[0]['id']
    r.save('ReadyToGenerate',workflows=rows)

def generate(r,i):
    r.access();shot=SHOTS[i-1];s=r.state;wf=next(x for x in s['workflows'] if x['index']==i);source=s['inputs'][shot['source']]
    slots=dict(firstFrame=source)
    if i==3:slots.update(femaleAudio=rel(FOLDER/f'shot-{i}-female.wav'),maleAudio=rel(FOLDER/f'shot-{i}-male.wav'))
    else:slots['speakerAudio']=rel(FOLDER/f"shot-{i}-{'female' if i==1 else 'male'}.wav")
    body=dict(projectId=s['projectId'],taskType='ImageToVideo',resourceClass='GPU',workflowId=wf['workflowId'],inputImagePath=source,maxRetries=0,stage=f'SyncFull-Audio-Driver-{i}',parameters=dict(workflowVersion=wf['version'],width=832,height=480,fps=25,frames=shot['native'],duration=shot['native']/25,steps=8,cfg=1,seed=2026102510+i,inputSlots=slots))
    asset(r,f'driver{i}',r.once(f'driver{i}TaskId',body));r.save('AwaitingDriverInspection')

def free(r):
    r.access();r.preserve();q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if q['queue_running'] or q['queue_pending'] or r.api('/api/minimax/local/status')['queue']['activeTasks']:raise RuntimeError('Cannot free active tasks')
    import psutil
    r.session.post('http://127.0.0.1:8188/free',json=dict(unload_models=True,free_memory=True),timeout=30).raise_for_status()
    import time
    for _ in range(20):
        values=[int(x.strip()) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free','--format=csv,noheader,nounits'],text=True).strip().split(',')]
        if values[1]>=4096 and psutil.virtual_memory().available//1024**2>=6144:break
        time.sleep(1)
    if values[1]<4096 or psutil.virtual_memory().available//1024**2<6144:raise RuntimeError('Portrait stage memory headroom insufficient')
    print('Passed: idle cache released; model files/history retained')

def act(r,i):
    r.access();r.preserve();s=r.state;shot=SHOTS[i-1]
    if read(FOLDER/'driver-review.json')['status']!='SelectedForActing':raise RuntimeError('Inspect actual drivers first')
    for role in shot['roles']:
        key=f'actor{i}'+role.title();profile='dialogue-hybrid-full-v1' if i==3 else 'dialogue-blink-v1';engine=ROOT/'tools'/('dialogue_sync_full/hybrid.py' if i==3 else 'dialogue_visual/acting.py')
        source=s['inputs'][shot['source']];driver=s[f'driver{i}Path'];manifest=FOLDER/(key+'.json')
        values=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),durationSeconds=shot['native']/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,repairProfile=profile,eyeResidualGain=1,faceDirection='large-small' if i!=3 else 'left-right' if role=='female' else 'right-left',driverOrigin='Fresh local full-shot original-audio InfiniteTalk mouth; original approved1299 pose for wide; not human footage',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
        if i==3:values.update(posePath=str(media(s['inputs']['pose'])),poseSha256=sha(media(s['inputs']['pose'])))
        if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen actor input changed')
        if not manifest.exists():write(manifest,values)
        body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='SyncFull-'+key,parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile=profile,engineVersion=sha(engine)))
        result=r.once(key+'TaskId',body);asset(r,key,result)
        for suffix,needle in [('Receipt','local_visual_acting_receipt'),('Mask','dialogue_face_support')]:
            p=next(x['assetPath'] for x in result['results'] if x.get('available') and needle in x.get('assetPath',''));r.save(**{key+suffix+'Path':p,key+suffix+'Sha256':sha(media(p))})
    r.save('AwaitingActingInspection')

def composite(r,key,values):
    manifest=FOLDER/(key+'.json')
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen composition changed')
    if not manifest.exists():write(manifest,values)
    body=dict(projectId=r.state['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage='SyncFull-'+key,parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),compositionProfile='dialogue-hybrid-full-compose-v1',engineVersion=sha(ROOT/'tools/dialogue_sync_full/compose.py')))
    result=r.once(key+'TaskId',body);asset(r,key,result)
    p=next(x['assetPath'] for x in result['results'] if x.get('available') and 'dialogue_composition_receipt' in x.get('assetPath',''));r.save(**{key+'ReceiptPath':p,key+'ReceiptSha256':sha(media(p))})

def canvases(r):
    r.access();s=r.state;files={}
    for label,key in [('source',None),('left','actor3FemalePath'),('right','actor3MalePath'),('leftReceipt','actor3FemaleReceiptPath'),('rightReceipt','actor3MaleReceiptPath'),('leftMask','actor3FemaleMaskPath'),('rightMask','actor3MaleMaskPath')]:
        p=s[key] if key else s['inputs']['wideReference'];files[label]=dict(path=str(media(p)),sha256=sha(media(p)))
    composite(r,'wideMerge',dict(profile='dialogue-hybrid-full-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=151,files=files))
    for shot,key in zip(SHOTS,['actor1Female','actor2Male','wideMerge']):
        i=shot['index'];body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage=f'SyncFull-Canvas-{i}',parameters=dict(files=[s[key+'Path']],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=shot['frames']/24,originalAudioVolume=0,outputName=f'sync_full_shot_{i}_canvas.mp4'))
        asset(r,f'canvas{i}',r.once(f'canvas{i}TaskId',body))
    r.save('AwaitingCanvasInspection')

def restore(r,i):
    r.access();s=r.state
    if read(FOLDER/'native-review.json')['status']!='SelectedForQhd':raise RuntimeError('Inspect full-shot performances before QHD')
    status=r.api('/api/video-restore/status')
    if not status['ready']:raise RuntimeError(status['message'])
    p=s[f'canvas{i}Path'];body=dict(projectId=s['projectId'],taskType='VideoRestore',resourceClass='GPU',maxRetries=0,stage=f'SyncFull-QHD-{i}',parameters=dict(input=p,sourceSha256=sha(media(p)),engineVersion=status['engineVersion'],strength=.3,cutFrames=[],outputProfile='qhd1440',targetWidth=2560,targetHeight=1440))
    asset(r,f'qhd{i}',r.once(f'qhd{i}TaskId',body))

def detail(r,i):
    r.access();files={}
    for label,key in [('source',f'canvas{i}Path'),('restored',f'qhd{i}Path')]:
        p=r.state[key];files[label]=dict(path=str(media(p)),sha256=sha(media(p)))
    composite(r,f'detail{i}',dict(profile='dialogue-hybrid-full-compose-v1',phase='detail',width=2560,height=1440,fps=24,frames=SHOTS[i-1]['frames'],strength=.65,expectedFaces=2 if i==3 else 1,maskEngineSha256=sha(ROOT/'tools/skin_pilot/pilot.py'),files=files))

def assemble(r):
    r.access();s=r.state
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='SyncFull-10s-Original-Subtitles',parameters=dict(files=[s[f'detail{i}Path'] for i in [1,2,3]],singlePass=True,targetWidth=2560,targetHeight=1440,targetFps=24,targetDurationSeconds=10,originalAudioVolume=0,subtitlePath=s['inputs']['subtitle'],outputName='dialogue_sync_full_10s_picture.mp4'))
    asset(r,'picture',r.once('pictureTaskId',body))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='SyncFull-Original-AAC-Packets',parameters=dict(files=[s['picturePath']],videoSha256=s['pictureSha256'],audioStreamCopyFrom=s['inputs']['original'],audioStreamCopySha256=sha(media(s['inputs']['original'])),outputName='dialogue_sync_full_same_voice_2k_10s.mp4'))
    asset(r,'final',r.once('finalTaskId',body));r.save('AwaitingFinalInspection')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','register','scan','generate','free','act','canvases','restore','detail','assemble','check'],required=True);p.add_argument('--index',type=int,choices=[1,2,3],default=1);a=p.parse_args();r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed') or a.stage=='check':r.preserve();print('Preserved; no new tasks');sys.exit(0)
    if a.stage in ['generate','act','restore','detail']:globals()[a.stage](r,a.index)
    else:globals()[a.stage](r)

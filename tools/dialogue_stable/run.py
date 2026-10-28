"""Resumable stable768 trial and full output via real local production queues."""
from pathlib import Path
import importlib.util,json,sys,subprocess,argparse,copy
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueStable20261025'
spec=importlib.util.spec_from_file_location('stable_base',ROOT/'tools/visual_validation/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.FOLDER=FOLDER
read,write,sha,media,rel=base.read,base.write,base.sha,base.media,base.rel
class Run(base.Run):
    def preserve(self):
        super().preserve()
        for k,v in self.state.items():
            if k.endswith('Path') and isinstance(v,str) and self.state.get(k[:-4]+'Sha256') and sha(media(v))!=self.state[k[:-4]+'Sha256']:raise RuntimeError('Stable asset drift: '+k)
def asset(r,key,detail):
    p=base.result(detail,'.mp4');r.save(**{key+'Path':p,key+'Sha256':sha(media(p))})
def prepare(r):
    r.access();old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    active=[x['id'] for x in r.api('/api/tasks?limit=500') if x['status'] in ['Running','Pending','Queued']]
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Existing work present; inspect before submitting')
    if not r.state.get('prepared'):
        prior=read(DATA/'DialogueSyncFull20261025/run.json');visual=read(DATA/'DialogueVisual20261025/run.json')
        if not prior.get('completed'):raise RuntimeError('Completed previous full version required')
        inputs=copy.deepcopy(prior['inputs']);inputs['before']=prior['finalPath']
        for i in [1,2,3]:inputs['driver'+str(i)]=prior['driver'+str(i)+'Path'];inputs['pose'+str(i)]=visual['inputs']['driver'+str(i)]
        paths=list(inputs.values())+[x['path'] for x in prior['preserved']]
        paths += [v for k,v in prior.items() if k.endswith('Path') and isinstance(v,str) and prior.get(k[:-4]+'Sha256')]
        records=[dict(path=p,sha256=sha(media(p))) for p in dict.fromkeys(paths)]
        inventory=[dict(path=str(p.relative_to(ROOT.parent/'Models')).replace('\\','/'),size=p.stat().st_size,mtimeNs=p.stat().st_mtime_ns) for p in (ROOT.parent/'Models').rglob('*') if p.is_file()]
        write(FOLDER/'model-inventory.json',dict(files=inventory));write(FOLDER/'initial-environment.json',dict(health=old.api('/api/health'),comfyIdle=True,activeTasks=[]))
        (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short','--branch'],cwd=ROOT,text=True),encoding='utf-8')
        r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=records,originalQueueStatus=old.api('/api/minimax/local/status')['queue'],pilotQueueStatus=r.api('/api/minimax/local/status')['queue'],width=1366,height=768,fps=24,frames=240,cutFrames=[53,96],newDiffusionJobs=0,localOnly=True,maxTargetedRepairs=2)
    r.preserve();old.api('/api/production/pause',{});r.api('/api/production/resume',{})
    if not r.state.get('projectId'):
        name='稳定768p十秒验证_'+r.state['runId'][:8];matches=[p for p in r.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        else:
            if r.state.get('projectStarted'):raise RuntimeError('Project outcome unresolved')
            r.save(projectStarted=True);pid=r.api('/api/projects',dict(name=name,description='Stable eye schedule and coherent approved poses; preserve original whole audio/subtitles/cuts; local preview only',defaultWidth=1366,defaultHeight=768,defaultFps=24),key='project')['id']
        r.save('Prepared',projectId=pid)
def free(r):
    r.access();q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if q['queue_running'] or q['queue_pending'] or r.api('/api/minimax/local/status')['queue']['activeTasks']:raise RuntimeError('Active work; cannot release cache')
    r.session.post('http://127.0.0.1:8188/free',json=dict(unload_models=True,free_memory=True),timeout=30).raise_for_status()
def act(r,role,key=None):
    r.access();r.preserve();s=r.state;i=1 if role=='female-close' else 2 if role=='male-close' else 3;n={1:57,2:46,3:151}[i]
    source=s['inputs'][{1:'femaleReference',2:'maleReference',3:'wideReference'}[i]];driver=s['inputs'][f'driver{i}'];pose=s['inputs'][f'pose{i}']
    key=key or 'v2_'+role.replace('-','_');manifest=FOLDER/(key+'.json');profile='dialogue-stable-v2' if key.startswith('v2_') else 'dialogue-stable-v1';engine='deterministic.py' if key.startswith('v2_') else 'acting.py'
    values=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),posePath=str(media(pose)),poseSha256=sha(media(pose)),durationSeconds=n/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,repairProfile=profile,stableRole=role,eyeResidualGain=1,faceDirection='large-small' if i!=3 else 'left-right' if role=='female-wide' else 'right-left',driverOrigin='Existing selected project42 audio driver, approved original pose; reused explicitly; no new diffusion job',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Actor manifest changed')
    if not manifest.exists():write(manifest,values)
    body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='Stable768-'+key,parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile=profile,engineVersion=sha(ROOT/'tools/dialogue_stable'/engine)))
    detail=r.once(key+'TaskId',body);asset(r,key,detail)
    for suffix,needle in [('Receipt','local_visual_acting_receipt'),('Mask','dialogue_face_support')]:
        p=next(x['assetPath'] for x in detail['results'] if x.get('available') and needle in x.get('assetPath',''));r.save(**{key+suffix+'Path':p,key+suffix+'Sha256':sha(media(p))})
    r.save('AwaitingActorInspection')
def canvases(r):
    r.access();s=r.state;files={}
    for label,key in [('source',None),('left','v2_female_widePath'),('right','v2_male_widePath'),('leftReceipt','v2_female_wideReceiptPath'),('rightReceipt','v2_male_wideReceiptPath'),('leftMask','v2_female_wideMaskPath'),('rightMask','v2_male_wideMaskPath')]:
        p=s[key] if key else s['inputs']['wideReference'];files[label]=dict(path=str(media(p)),sha256=sha(media(p)))
    manifest=FOLDER/'merge.json';values=dict(profile='dialogue-stable-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=151,files=files)
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Merge changed')
    if not manifest.exists():write(manifest,values)
    body=dict(projectId=s['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage='Stable768-merge',parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),compositionProfile='dialogue-stable-compose-v1',engineVersion=sha(ROOT/'tools/dialogue_stable/compose.py')))
    asset(r,'wideMerge',r.once('wideMergeTaskId',body))
    for i,key,n in [(1,'v2_female_close',53),(2,'v2_male_close',43),(3,'wideMerge',144)]:
        body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage=f'Stable768-canvas-{i}',parameters=dict(files=[s[key+'Path']],singlePass=True,targetWidth=1366,targetHeight=768,targetFps=24,targetDurationSeconds=n/24,originalAudioVolume=0,outputName=f'stable768_shot{i}.mp4'))
        asset(r,f'canvas{i}',r.once(f'canvas{i}TaskId',body))
    r.save('Awaiting768Inspection')
def assemble(r):
    r.access();s=r.state
    if read(FOLDER/'native-review.json')['status']!='Passed':raise RuntimeError('Actual 768 shot inspection required')
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Stable768-picture',parameters=dict(files=[s[f'canvas{i}Path'] for i in [1,2,3]],singlePass=True,targetWidth=1366,targetHeight=768,targetFps=24,targetDurationSeconds=10,originalAudioVolume=0,subtitlePath=s['inputs']['subtitle'],outputName='dialogue_stable768_10s_picture.mp4'))
    asset(r,'picture',r.once('pictureTaskId',body))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Stable768-original-audio',parameters=dict(files=[s['picturePath']],videoSha256=s['pictureSha256'],audioStreamCopyFrom=s['inputs']['original'],audioStreamCopySha256=sha(media(s['inputs']['original'])),allowResolutionDifference=True,outputName='dialogue_stable768_same_voice_10s.mp4'))
    asset(r,'final',r.once('finalTaskId',body));r.save('AwaitingFinalInspection')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','free','act','canvases','assemble','check']);p.add_argument('--role',choices=['female-close','male-close','female-wide','male-wide']);p.add_argument('--key');a=p.parse_args();r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed') or a.stage=='check':r.preserve();print('Preserved; no new tasks');sys.exit(0)
    if a.stage=='act':act(r,a.role,a.key)
    else:globals()[a.stage](r)

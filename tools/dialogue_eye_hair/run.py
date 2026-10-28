"""New review-only CPU revision; never changes the completed project43 run."""
from pathlib import Path
import importlib.util,json,sys,copy,subprocess,argparse,shutil,os
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueEyeHair20261025'
spec=importlib.util.spec_from_file_location('eye_hair_run_base',ROOT/'tools/dialogue_stable/run.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.base.FOLDER=FOLDER
Run=b.Run;read,write,sha,media,rel=b.read,b.write,b.sha,b.media,b.rel
def asset(r,key,detail):
    b.asset(r,key,detail)
    for needle,suffix in [('dialogue_composition_receipt','Receipt')]:
        p=next((x['assetPath'] for x in detail['results'] if x.get('available') and needle in x.get('assetPath','')),None)
        if p:r.save(**{key+suffix+'Path':p,key+suffix+'Sha256':sha(media(p))})
def prepare(r):
    r.access();old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access();q=r.session.get('http://127.0.0.1:8188/queue').json()
    if q['queue_running'] or q['queue_pending'] or any(t['status'] in ['Running','Pending','Queued'] for t in r.api('/api/tasks?limit=500')):raise RuntimeError('Active work; preserve it')
    if not r.state.get('prepared'):
        s=read(DATA/'DialogueStable20261025/run.json')
        if not s.get('completed'):raise RuntimeError('Existing completed version required')
        inputs=dict(before=s['finalPath'],source=s['inputs']['wideReference'],female=s['v2_female_widePath'],male=s['v2_male_widePath'],femaleReceipt=s['v2_female_wideReceiptPath'],maleReceipt=s['v2_male_wideReceiptPath'],femaleMask=s['v2_female_wideMaskPath'],maleMask=s['v2_male_wideMaskPath'],canvas1=s['canvas1Path'],canvas2=s['canvas2Path'],subtitle=s['inputs']['subtitle'])
        paths=list(inputs.values())+[x['path'] for x in s['preserved']]+[v for k,v in s.items() if k.endswith('Path') and isinstance(v,str) and s.get(k[:-4]+'Sha256')]
        records=[dict(path=p,sha256=sha(media(p))) for p in dict.fromkeys(paths)]
        shutil.copy2(DATA/'DialogueStable20261025/model-inventory.json',FOLDER/'model-inventory.json')
        user_reported_frame = os.environ.get('AI_VIDEO_STUDIO_USER_REPORTED_FRAME')
        if not user_reported_frame:
            raise RuntimeError('Set AI_VIDEO_STUDIO_USER_REPORTED_FRAME to the reviewed local screenshot path')
        screenshot_source = Path(user_reported_frame).expanduser()
        if not screenshot_source.is_file():
            raise RuntimeError('AI_VIDEO_STUDIO_USER_REPORTED_FRAME must point to an existing screenshot file')
        shutil.copy2(screenshot_source,FOLDER/'user-reported-frame.png')
        write(FOLDER/'user-feedback.json',dict(status='Failed',scope='Project43 female side-profile eye/hair visual content at7.9-8.1s; prior technical checks remainPassed',sourcePath=inputs['before'],sourceSha256=sha(media(inputs['before'])),userScreenshot=rel(FOLDER/'user-reported-frame.png'),screenshotSha256=sha(FOLDER/'user-reported-frame.png'),method='New local source-anchor fallback, cancel this side-profile forced blink, retain speaking mouth only; male unchanged before encoding'))
        (FOLDER/'git-status-before.txt').write_text(subprocess.check_output(['git','status','--short','--branch'],cwd=ROOT,text=True),encoding='utf-8')
        r.save('InputsFrozen',prepared=True,inputs=inputs,preserved=records,originalQueueStatus=old.api('/api/minimax/local/status')['queue'],pilotQueueStatus=r.api('/api/minimax/local/status')['queue'],newGpuTasks=0,newModels=0,localOnly=True,maxTargetedRepairs=2,cutFrames=[53,96])
    r.preserve();old.api('/api/production/pause',{});r.api('/api/production/resume',{})
    if not r.state.get('projectId'):
        name='女方侧脸眼睛与头发修复_'+r.state['runId'][:8];matches=[p for p in r.api('/api/projects') if p['name']==name]
        if matches:pid=matches[0]['id']
        else:
            if r.state.get('projectStarted'):raise RuntimeError('Project creation outcome unresolved')
            r.save(projectStarted=True);pid=r.api('/api/projects',dict(name=name,description='User-reported side profile eye and hair defect; local source-anchored mouth-only CPU fallback, keep original audio/subtitles/cuts and previous version',defaultWidth=1366,defaultHeight=768,defaultFps=24),key='project')['id']
        r.save('Prepared',projectId=pid)
def sample(r):
    r.access();r.preserve();s=r.state;files={}
    for label,key in [('source','source'),('left','female'),('right','male'),('leftReceipt','femaleReceipt'),('rightReceipt','maleReceipt'),('leftMask','femaleMask'),('rightMask','maleMask')]:
        p=s['inputs'][key];files[label]=dict(path=str(media(p)),sha256=sha(media(p)))
    values=dict(profile='dialogue-eye-hair-guard-v1',phase='merge',width=1024,height=576,fps=25,frames=151,files=files,femalePolicy='source-eyes-hair-mouth-only',mouthEllipse=[360,205,26,23],speakingSeconds=[.158,2.237],fadeSeconds=[.08,.16])
    manifest=FOLDER/'guard-merge.json'
    if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen composition changed')
    if not manifest.exists():write(manifest,values)
    body=dict(projectId=s['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage='EyeHair-Guard-Wide-Sample',parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),compositionProfile='dialogue-eye-hair-guard-v1',engineVersion=sha(ROOT/'tools/dialogue_eye_hair/compose.py')))
    asset(r,'wideMerge',r.once('wideMergeTaskId',body))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='EyeHair-768-Wide-Sample',parameters=dict(files=[s['wideMergePath']],singlePass=True,targetWidth=1366,targetHeight=768,targetFps=24,targetDurationSeconds=6,originalAudioVolume=0,outputName='eye_hair_guard_768_wide_sample.mp4'))
    asset(r,'wideCanvas',r.once('wideCanvasTaskId',body));r.save('AwaitingSampleInspection')
def assemble(r):
    r.access();s=r.state
    if read(FOLDER/'sample-review.json')['status']!='Passed':raise RuntimeError('Actual sample eye/hair/mouth inspection required')
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='EyeHair-Original-Subtitles',parameters=dict(files=[s['inputs']['canvas1'],s['inputs']['canvas2'],s['wideCanvasPath']],singlePass=True,targetWidth=1366,targetHeight=768,targetFps=24,targetDurationSeconds=10,originalAudioVolume=0,subtitlePath=s['inputs']['subtitle'],outputName='dialogue_eye_hair_guard_768_10s_picture.mp4'))
    asset(r,'picture',r.once('pictureTaskId',body))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='EyeHair-Original-Whole-Audio',parameters=dict(files=[s['picturePath']],videoSha256=s['pictureSha256'],audioStreamCopyFrom=s['inputs']['before'],audioStreamCopySha256=sha(media(s['inputs']['before'])),outputName='dialogue_eye_hair_guard_768_same_voice_10s.mp4'))
    asset(r,'final',r.once('finalTaskId',body));r.save('AwaitingFinalInspection')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','sample','assemble','check']);a=p.parse_args();r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed') or a.stage=='check':r.preserve();print('Preserved; no new tasks');sys.exit(0)
    globals()[a.stage](r)

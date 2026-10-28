"""Resumable, person-free environmental cutaway and review edit.

Models and post-processing run through the existing business queue. The
original completed story, soundtrack, reference and pending reviews are kept.
"""
import argparse,copy,datetime,json,msvcrt,re,sys,uuid
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).parent/'character_scene'))
from common import ROOT,DATA,sha,write,mysql

OUT=DATA/'CharacterSceneCutaway20261028'
OLD=DATA/'CharacterPlotContinuation20261028/run.json'
FIRST=DATA/'CharacterPlotPreview20261027/run.json'
IMAGE_PROMPT=('Use Image1 ONLY as the location reference for the warm wooden window frame, afternoon daylight and green trees outside. '
    'Create a genuinely WIDE establishing photograph of the same quiet cozy interior from several meters back: a large warm wooden-framed window and the surrounding walls, '
    'an empty simple wooden table and one empty chair. Distant lush green trees are visible through the glass. '
    'The entire room is completely unoccupied. Remove the woman and all people from the image, including reflections, portraits, silhouettes and body parts. '
    'Single coherent realistic live-action photograph, natural afternoon light, camera fixed at eye level, horizontal 16:9; no text, no collage, no logo.')
VIDEO_PROMPT=('A wide establishing view of the quiet sunlit room shown in the first frame. Keep the wooden window, empty chair, walls and camera stable. '
    'Outside the window, green leaves move softly in a gentle breeze and daylight subtly shimmers; very small natural motion. '
    'The room stays completely empty: no people, faces, reflections, animals or moving furniture. '
    'One continuous locked-camera photorealistic shot, no text, no cuts, no speaking; the final edit replaces the native audio.')

class Cutaway:
 def __init__(self):
    self.path=OUT/'run.json';self.base='http://127.0.0.1:18080';self.s=requests.Session()
    auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];self.s.headers['X-CSRF-Token']=auth['csrfToken']
    self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
 def api(self,path,body=None,headers=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,headers=headers,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP '+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def save(self):write(self.path,self.state)
 def key(self,label):return 'scene-cut:'+self.state['runId']+':'+label
 def preserve(self):
    for x in self.state['protectedFiles']:
        if sha(Path(x['path']))!=x['sha256']:raise RuntimeError('Protected source changed: '+x['path'])
 def idle(self):
    h=self.api('/api/health');q=self.api('/api/minimax/local/status')['queue'];c=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert h['database']['online'] and h['comfy']['online'] and h['ffmpeg']['available'] and h['comfy']['gpu']['freeMiB']>=1024
    assert not q['paused'] and q['gpuConcurrency']==1 and q['activeTasks']==0 and not c['queue_running'] and not c['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');")=='0'
 def prepare(self):
    if self.state:self.preserve();print('Existing cutaway checkpoint retained; no new task.');return
    self.idle();old=json.loads(OLD.read_text(encoding='utf-8'));first=json.loads(FIRST.read_text(encoding='utf-8'))
    assert old['completed'] and old['finalVideo']['taskId']==1565 and first['Keyframe']['id']==1554 and first['Keyframe']['inspection']['payload']['decision']=='Passed'
    orig=DATA/old['finalVideo']['assetPath'];scene=DATA/first['Keyframe']['assetPath'];assert sha(orig)==old['finalVideo']['sha256'] and sha(scene)==first['Keyframe']['sha256']
    protected=[dict(path=str(p),sha256=sha(p)) for p in [OLD,FIRST,orig,scene,DATA/'CharacterScene20261027/run.json']]
    self.state=dict(runId=str(uuid.uuid4()),projectId=old['projectId'],episodeId=old['episodeId'],sourceVideoTaskId=1565,sourceVideoPath=old['finalVideo']['assetPath'],sourceVideoSha256=old['finalVideo']['sha256'],locationFrameTaskId=1554,locationFramePath=first['Keyframe']['assetPath'],locationFrameSha256=first['Keyframe']['sha256'],protectedFiles=protected,cutStartFrame=210,cutEndFrame=246,stage='Prepared',contentReview='NeedReview',publication='Blocked',completed=False,images=[],video=None)
    self.save();print('New environment-cutaway checkpoint created; prior story and hold preserved.')
 def submit(self,entry,body,label):
    key=self.key(label);assert re.fullmatch(r'[A-Za-z0-9:-]+',key);body['idempotencyKey']=key
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen task request changed')
    entry['body']=body;self.save();found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['id']=int(found);self.save();print('Recovered existing task '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Submission outcome uncertain; inspect task database before retrying')
    pre=self.api('/api/tasks/preflight',body);write(OUT/(label+'-preflight.json'),pre)
    if not pre['passed']:raise RuntimeError('Preflight rejected: '+str(pre['issues']))
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/tasks',body);entry.update(id=result['id'],status='Pending');self.save();print(label+' queued '+str(entry['id']))
 def image(self,reason=None,adjustment=None):
    if self.state.get('completed'):raise RuntimeError('Completed run is read-only')
    self.preserve();self.idle();history=self.state['images']
    if history and not history[-1].get('id'):
        entry=history[-1];attempt=entry['attempt'];reason=entry['reason'];adjustment=entry['adjustment']
    else:
        attempt=len(history)
        if attempt and history[-1].get('inspection',{}).get('decision')!='Failed':raise RuntimeError('Only a specifically failed candidate can be repaired')
        if attempt>2:raise RuntimeError('Two targeted image repairs exhausted')
        if attempt and (not reason or not adjustment):raise RuntimeError('Record failure and prompt change')
        entry=dict(attempt=attempt,reason=reason,adjustment=adjustment);history.append(entry);self.save()
    prompt=IMAGE_PROMPT+(' Targeted correction: '+adjustment if adjustment else '')
    body=dict(projectId=self.state['projectId'],taskType='Keyframe',workflowId=2441,inputImagePath=self.state['locationFramePath'],resourceClass='GPU',stage='Environment-Cutaway-Keyframe-Preview',maxRetries=0,
      parameters=dict(workflowVersion='character-pack-klein4b-single-1536-v1',inputSlots=dict(firstFrame=self.state['locationFramePath']),positive=prompt,seed=2026102807+attempt*100,width=1536,height=864,steps=4,cfg=1))
    self.submit(entry,body,'image-'+str(attempt));self.state['stage']='ImageQueued';self.save()
 def inspect_image(self,decision,note):
    self.preserve();e=self.state['images'][-1]
    if decision not in ['Passed','Failed'] or not note or e.get('status')!='Succeeded' or sha(DATA/e['assetPath'])!=e['sha256']:raise RuntimeError('Inspect actual unchanged image and record a reason')
    e['inspection']=dict(decision=decision,scope='PreviewInspection',note=note,sha256=e['sha256'],humanApproved=False);self.state['stage']='ImageInspected'+decision;self.save();print('Environment frame '+decision+'; final review remains pending.')
 def video(self):
    self.preserve();self.idle();frame=self.state['images'][-1]
    if frame.get('inspection',{}).get('decision')!='Passed' or sha(DATA/frame['assetPath'])!=frame['sha256']:raise RuntimeError('Inspect the actual environmental frame before video')
    check=json.loads((OUT/'image-checks.json').read_text(encoding='utf-8'))
    if check['status']!='Passed' or check['taskId']!=frame['id']:raise RuntimeError('Actual environment frame needs verified provenance')
    entry=self.state.get('video') or {};self.state['video']=entry
    if entry.get('id'):print('Existing video retained '+str(entry['id']));return
    body=dict(projectId=self.state['projectId'],taskType='ImageToVideo',workflowId=1105,inputImagePath=frame['assetPath'],dependencyTaskId=frame['id'],resourceClass='GPU',stage='MiniMax-Local-Experiment',maxRetries=0,
      parameters=dict(provider='MiniMaxLocal',profile='baseline480',textToVideo=False,prompt=VIDEO_PROMPT,seed=2026102808,width=864,height=480,frames=124,fps=24,steps=20,duration=124/24,preserveAudio=True,extractNativeAudio=True,qualityReferenceImagePath=frame['assetPath'],contentReview='NeedReview'))
    self.submit(entry,body,'wide-video');self.state['stage']='VideoQueued';self.save()
 def inspect_video(self,decision,note):
    self.preserve();e=self.state['video'];report=json.loads((OUT/'video-checks.json').read_text(encoding='utf-8'))
    if decision not in ['Passed','Failed'] or not note or e.get('status')!='Succeeded' or report['status']!='Passed' or sha(DATA/e['assetPath'])!=e['sha256']:raise RuntimeError('Inspect the actual technically verified video')
    e['inspection']=dict(decision=decision,scope='PreviewInspection',note=note,sha256=e['sha256'],humanApproved=False);self.state['stage']='VideoInspected'+decision;self.save();print('Environment video '+decision+'; final review remains pending.')
 def edit(self,name):
    if self.state.get('completed'):raise RuntimeError('Completed edit is read-only')
    self.preserve();self.idle();video=self.state.get('video') or {}
    if video.get('inspection',{}).get('decision')!='Passed' or sha(DATA/video['assetPath'])!=video['sha256']:raise RuntimeError('Inspect the real environment clip before editing')
    tasks=self.state.setdefault('editTasks',{});entry=tasks.setdefault(name,{})
    if entry.get('id'):print('Existing '+name+' task retained '+str(entry['id']));return
    base=self.state['sourceVideoPath'];baseSha=self.state['sourceVideoSha256'];wide=video['assetPath'];wideSha=video['sha256'];start=self.state['cutStartFrame'];end=self.state['cutEndFrame'];fps=24
    common=dict(projectId=self.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Scene-Cutaway-Review-Edit')
    if name in ['head','cut','tail']:
        source=wide if name=='cut' else base;sourceSha=wideSha if name=='cut' else baseSha
        duration={'head':start/fps,'cut':(end-start)/fps,'tail':(360-end)/fps}[name];offset=end/fps if name=='tail' else 0
        body=dict(common,dependencyTaskId=video['id'] if name=='cut' else self.state['sourceVideoTaskId'],parameters=dict(files=[source],singlePass=True,targetWidth=864,targetHeight=480,targetFps=24,trimStartSeconds=offset,targetDurationSeconds=duration,originalAudioVolume=0,sourceChecks=[dict(path=source,sha256=sourceSha)],outputName='window_cutaway_'+name+'.mp4'))
    elif name=='picture':
        parts=[tasks.get(k,{}) for k in ['head','cut','tail']]
        if any(x.get('status')!='Succeeded' or sha(DATA/x['assetPath'])!=x['sha256'] for x in parts):raise RuntimeError('Three actual edited picture parts are required')
        body=dict(common,dependencyTaskId=parts[-1]['id'],parameters=dict(files=[x['assetPath'] for x in parts],singlePass=True,targetWidth=864,targetHeight=480,targetFps=24,targetDurationSeconds=15,originalAudioVolume=0,sourceChecks=[dict(path=x['assetPath'],sha256=x['sha256']) for x in parts],outputName='window_cutaway_picture.mp4'))
    elif name=='final':
        pic=tasks.get('picture',{})
        if pic.get('status')!='Succeeded' or sha(DATA/pic['assetPath'])!=pic['sha256']:raise RuntimeError('Edited picture must be complete before preserving soundtrack')
        body=dict(common,dependencyTaskId=pic['id'],parameters=dict(files=[pic['assetPath']],videoSha256=pic['sha256'],audioStreamCopyFrom=base,audioStreamCopySha256=baseSha,targetFps=24,outputName='window_cutaway_15s_same_audio.mp4'))
    else:raise RuntimeError('Unknown edit task')
    self.submit(entry,body,'edit-'+name);self.state['stage']='Edit-'+name+'-Queued';self.save()
 def tick(self):
    entries=[*self.state['images']]+([self.state['video']] if self.state.get('video') else [])+list(self.state.get('editTasks',{}).values())
    for e in entries:
        if not e.get('id'):continue
        detail=self.api('/api/tasks/'+str(e['id']));e['status']=detail['task']['status']
        if e['status']=='Succeeded':
            extension='.png' if e in self.state['images'] else '.mp4';asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith(extension));e.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
        elif e['status'] in ['Failed','Cancelled']:e['failure']=detail['task'].get('errorMessage')
    self.save();print(json.dumps([dict(id=e.get('id'),status=e.get('status'),sha256=e.get('sha256')) for e in entries],ensure_ascii=False))
 def inspect_final(self,note):
    self.preserve();entry=self.state['editTasks']['final']
    report=json.loads((OUT/'final-checks.json').read_text(encoding='utf-8'))
    if not note or entry.get('status')!='Succeeded' or report['status']!='Passed' or report['taskId']!=entry['id'] or sha(DATA/entry['assetPath'])!=entry['sha256']:
        raise RuntimeError('Inspect the real technically verified final edit before recording a preview note')
    self.state['finalInspection']=note;self.state['stage']='FinalInspected';self.save()
    print('Final preview inspection recorded; content remains pending user review.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','image','inspect-image','video','inspect-video','edit','tick','inspect-final']);parser.add_argument('--decision',choices=['Passed','Failed']);parser.add_argument('--note');parser.add_argument('--prompt');parser.add_argument('--part',choices=['head','cut','tail','picture','final']);args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);p=Cutaway()
        if args.command=='image':p.image(args.note,args.prompt)
        elif args.command=='inspect-image':p.inspect_image(args.decision,args.note)
        elif args.command=='inspect-video':p.inspect_video(args.decision,args.note)
        elif args.command=='inspect-final':p.inspect_final(args.note)
        elif args.command=='edit':
            if not args.part:parser.error('--part is required')
            p.edit(args.part)
        else:getattr(p,args.command)()

if __name__=='__main__':main()

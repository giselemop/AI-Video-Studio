"""Resumable local continuation of the completed window story.

All model generation and video assembly use the existing Studio queue. The
source clip, reviewed frames, original checkpoints and other work are retained.
"""
import argparse, copy, datetime, json, msvcrt, re, subprocess, sys, uuid
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).parent/'character_scene'))
from common import ROOT, DATA, sha, write, mysql

OUT=DATA/'CharacterPlotContinuation20261028'
OLD=DATA/'CharacterPlotPreview20261027/run.json'
TEXTS=[
 '林安等了很久，终于听见熟悉的脚步。',
 '她没有多问，只是轻轻点了点头。',
 '窗边的等待，终于有了回应。'
]
STARTS=[0.4,5.5,10.8]
SHOT_SPECS=[
 dict(number=2,title='轻轻点头',action=('Begin exactly as the previous final frame, with the same woman and her warm closed-mouth smile. '
      'She gently gives ONE small natural nod, then raises her head and briefly glances toward picture left, as if acknowledging a friend offscreen. '
      'Return her gaze near the camera, still calmly smiling. Only one woman, no visible other person, no speech or mouth movement, no hands entering frame. '
      'Same face, age, shoulder-length black hair, cream knitted top, window and afternoon lighting; locked camera, no cuts.'),
      start='Continue the immediately preceding frame exactly: same single woman, head and smile, same clothes, window and camera.'),
 dict(number=3,title='窗边回应',action=('Begin exactly as the previous final frame, same woman and same relaxed expression. '
      'She takes a quiet breath, makes a tiny thoughtful glance down, then raises her gaze to the camera and settles into a gentle closed-mouth smile. '
      'Hold the final expression. Only one woman, no visible other person, no speech or mouth movement, no hands entering frame. '
      'Same face, age, black shoulder-length hair, cream knitted top, window and afternoon lighting; locked camera, no cuts.'),
      start='Continue the immediately preceding frame exactly: same single woman, head and expression, same clothes, window and camera.')
]


class Continuation:
 def __init__(self):
    self.path=OUT/'run.json';self.base='http://127.0.0.1:18080';self.session=requests.Session()
    auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired']
    self.session.headers['X-CSRF-Token']=auth['csrfToken']
    self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
 def api(self,path,body=None,headers=None):
    r=self.session.request('POST' if body is not None else 'GET',self.base+path,json=body,headers=headers,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP '+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def save(self):write(self.path,self.state)
 def key(self,label):return 'plot-cont:'+self.state['runId']+':'+label
 def preserve(self):
    for item in self.state['protectedFiles']:
        if sha(Path(item['path']))!=item['sha256']:raise RuntimeError('Protected file changed: '+item['path'])
 def idle(self):
    h=self.api('/api/health');q=self.api('/api/minimax/local/status')['queue'];c=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert h['database']['online'] and h['comfy']['online'] and h['ffmpeg']['available'] and h['comfy']['gpu']['freeMiB']>=6144
    assert not q['paused'] and q['gpuConcurrency']==1 and q['activeTasks']==0 and not c['queue_running'] and not c['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');")=='0'
 def prepare(self):
    if self.state:
        self.preserve();print('Existing continuation checkpoint retained; no task submitted.');return
    self.idle();old=json.loads(OLD.read_text(encoding='utf-8'));assert old['completed'] and old['Video']['id']==1555 and old['Preview']['id']==1556
    assert old['Video']['inspection']['payload']['decision']=='Passed'
    raw=DATA/old['Video']['assetPath'];preview=DATA/old['Preview']['assetPath'];tail=OUT/'source-1555-tail-123.png'
    assert sha(raw)==old['Video']['sha256'] and sha(preview)==old['Preview']['sha256'] and tail.is_file()
    inherited=old['protectedFiles'];protected=[dict(path=str(OLD),sha256=sha(OLD)),dict(path=str(raw),sha256=sha(raw)),dict(path=str(preview),sha256=sha(preview)),dict(path=str(tail),sha256=sha(tail))]+inherited
    self.state=dict(runId=str(uuid.uuid4()),stage='Prepared',projectId=old['projectId'],episodeId=old['episodeId'],episodeCastId=old['episodeCastId'],sourceVideoTaskId=1555,sourceReviewId=old['Video']['inspection']['id'],sourcePlanId=old['planId'],sourceVideoPath=old['Video']['assetPath'],sourceVideoSha256=old['Video']['sha256'],sourceTailPath=tail.relative_to(DATA).as_posix(),sourceTailSha256=sha(tail),sourceTailFrameIndex=123,protectedFiles=protected,story='窗边等候：熟悉的脚步、点头回应与安静的陪伴。',audioStrategy='PostDubbing',voiceId='qwen3:Vivian',narration=[dict(index=i+1,text=text,startSeconds=STARTS[i]) for i,text in enumerate(TEXTS)],shots=[],technicalStatus='InProgress',contentReview='NeedReview',publication='Blocked',completed=False)
    self.save();print('Fresh continuation checkpoint created; source video and previous holds preserved.')
 def tts(self,index):
    if self.state.get('completed'):raise RuntimeError('Completed continuation is read-only')
    self.preserve();self.idle();entry=self.state['narration'][index-1]
    if entry.get('taskId'):print('Existing narration task retained '+str(entry['taskId']));return
    body=dict(projectId=self.state['projectId'],voiceId=self.state['voiceId'],text=entry['text'],instruction='成年女性普通话旁白，温暖轻柔，像在讲一个安静的短故事，语速自然，语句完整，不夸张。',speed=1,pitch=0,outputName='window_story_narration_'+str(index)+'.wav')
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen narration request changed')
    entry['body']=body;key=self.key('narration-'+str(index));assert re.fullmatch(r'[A-Za-z0-9:-]+',key);entry['idempotencyKey']=key;self.save()
    found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['taskId']=int(found);entry['status']='Recovered';self.save();print('Recovered narration task '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Narration submission outcome uncertain; inspect task database before retrying')
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save()
    result=self.api('/api/audio/tts',body,headers={'Idempotency-Key':key});entry.update(taskId=result['taskId'],status='Pending');self.state['stage']='NarrationQueued';self.save();print('Qwen narration task queued '+str(result['taskId']))
 def shots(self):
    if self.state.get('completed'):raise RuntimeError('Completed continuation is read-only')
    self.preserve();old=json.loads(OLD.read_text(encoding='utf-8'))
    for spec in SHOT_SPECS:
        entry=next((x for x in self.state['shots'] if x['number']==spec['number']),None)
        if entry is None:
            entry=dict(number=spec['number'],title=spec['title']);self.state['shots'].append(entry);self.save()
        if not entry.get('shotId'):
            rows=self.api('/api/episodes/'+str(self.state['episodeId'])+'/shots')
            occupied=next((x for x in rows if x['shotNumber']==spec['number']),None)
            if occupied and occupied['title']!=spec['title']:raise RuntimeError('Shot number occupied by another work; preserve it')
            if occupied:entry['shotId']=occupied['id']
            else:
                if entry.get('creationIntent'):raise RuntimeError('Shot creation outcome uncertain; inspect the database before another request')
                entry['creationIntent']=True;self.save()
                entry['shotId']=self.api('/api/shots',dict(projectId=self.state['projectId'],episodeId=self.state['episodeId'],shotNumber=spec['number'],title=spec['title'],width=864,height=480,frames=124,fps=24,durationSeconds=124/24))['id']
            self.save()
        if not entry.get('planBody'):
            body=copy.deepcopy(old['planBody']);body['action']=spec['action'];body['actors'][0]['action']=spec['start'];body['idempotencyKey']=self.key('shot-plan-'+str(spec['number']))
            entry['planBody']=body;self.save()
        if not entry.get('planId'):
            record=self.api('/api/character-story/shots/'+str(entry['shotId']),entry['planBody'])
            entry.update(planId=record['id'],planSha256=record['sha256']);self.save()
    self.state['stage']='ShotsPlanned';self.save();print('Two new sequential Shot plans frozen with the same actor, scene and camera.')
 def music(self):
    if self.state.get('completed'):raise RuntimeError('Completed continuation is read-only')
    self.preserve();self.idle();entry=self.state.setdefault('music',{})
    if entry.get('taskId'):print('Existing music task retained '+str(entry['taskId']));return
    key=self.key('music');body=dict(projectId=self.state['projectId'],taskType='MusicSynthesis',resourceClass='CPU',maxRetries=0,stage='Original-Music-Preview',idempotencyKey=key,parameters=dict(composition='window-warm-piano-v1',durationSeconds=15.5))
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen music request changed')
    entry['body']=body;self.save();found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['taskId']=int(found);self.save();print('Recovered original music task '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Music submission outcome uncertain; inspect the queue before retrying')
    check=self.api('/api/tasks/preflight',body)
    if not check['passed']:raise RuntimeError('Music preflight rejected: '+str(check['issues']))
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/tasks',body);entry.update(taskId=result['id'],status='Pending');self.save();print('Original instrumental queued '+str(result['id']))
 def video(self,number):
    if self.state.get('completed'):raise RuntimeError('Completed continuation is read-only')
    self.preserve();self.idle();entry=next(x for x in self.state['shots'] if x['number']==number)
    if entry.get('videoTaskId'):print('Existing video task retained '+str(entry['videoTaskId']));return
    if number==2:
        sourceId=self.state['sourceVideoTaskId'];reviewId=self.state['sourceReviewId'];framePath=self.state['sourceTailPath'];frameSha=self.state['sourceTailSha256']
    else:
        prev=next(x for x in self.state['shots'] if x['number']==number-1)
        if prev.get('inspection',{}).get('payload',{}).get('decision')!='Passed' or not prev.get('tailInspection',{}).get('passed'):raise RuntimeError('Inspect the actual previous video and final frame before continuation')
        sourceId=prev['videoTaskId'];reviewId=prev['inspection']['id'];framePath=prev['tailPath'];frameSha=prev['tailSha256']
    if sha(DATA/framePath)!=frameSha:raise RuntimeError('Inspected tail frame changed')
    key=self.key('shot'+str(number)+'-video');body=dict(planId=entry['planId'],profile='baseline480',seed=2026102800+number,continuationSourceTaskId=sourceId,continuationReviewId=reviewId,continuationFramePath=framePath,continuationFrameSha256=frameSha,idempotencyKey=key)
    if entry.get('videoBody') and entry['videoBody']!=body:raise RuntimeError('Frozen video request changed')
    entry['videoBody']=body;self.save();found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['videoTaskId']=int(found);self.save();print('Recovered video task '+found);return
    if entry.get('videoSubmissionIntentAt'):raise RuntimeError('Video submission outcome uncertain; inspect task database before retrying')
    resolved=self.api('/api/character-story/resolve/Video',body);write(OUT/('shot'+str(number)+'-resolved.json'),resolved)
    entry['videoSubmissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/character-story/generate/Video',body);entry.update(videoTaskId=result['id'],status='Pending');self.state['stage']='Shot'+str(number)+'Queued';self.save();print('Checked-tail continuation queued '+str(result['id']))
 def inspect(self,number,decision,note):
    if decision not in ['Passed','Failed'] or not note:raise RuntimeError('Supply actual inspection result and details')
    self.preserve();entry=next(x for x in self.state['shots'] if x['number']==number)
    if entry.get('status')!='Succeeded' or sha(DATA/entry['assetPath'])!=entry['sha256']:raise RuntimeError('Inspect unchanged completed video first')
    report=json.loads((DATA/entry.get('technicalCheckPath',('CharacterPlotContinuation20261028/shot-'+str(number)+'/technical-checks.json'))).read_text(encoding='utf-8'))
    if report['status']!='Passed' or report['videoTaskId']!=entry['videoTaskId']:raise RuntimeError('Inspect the correct technically verified video')
    request=dict(taskId=entry['videoTaskId'],decision=decision,scope='PreviewInspection',humanConfirmed=False,note=note,idempotencyKey=self.key('inspection-'+str(entry['videoTaskId'])))
    entry['inspection']=self.api('/api/character-story/inspect',request)
    entry['tailInspection']=dict(passed=decision=='Passed',framePath=entry['tailPath'],frameSha256=entry['tailSha256'],note=note,scope='PreviewInspection')
    self.state['stage']='Shot'+str(number)+'Inspected'+decision;self.save();print('Shot '+str(number)+' PreviewInspection '+decision+'; final human review remains pending.')
 def repair(self,number,note,adjustment):
    if not note or not adjustment:raise RuntimeError('Provide specific failure and changed prompt')
    self.preserve();entry=next(x for x in self.state['shots'] if x['number']==number);history=entry.setdefault('videoHistory',[]);pending=entry.get('repairPending')
    if pending is None:
        if entry.get('status')!='Failed' and entry.get('inspection',{}).get('payload',{}).get('decision')!='Failed':raise RuntimeError('Only a recorded failed clip can be repaired')
        attempt=len(history)+1
        if attempt>2:raise RuntimeError('Two targeted repairs exhausted')
        oldId=entry['videoTaskId'];body=dict(entry['videoBody'],seed=entry['videoBody']['seed']+100,repairOfTaskId=oldId,changeReason=note,promptAdjustment=adjustment,idempotencyKey=self.key('shot'+str(number)+'-repair-'+str(attempt)))
        pending=dict(body=body,attempt=attempt,oldId=oldId);entry['repairPending']=pending;self.save()
    body=pending['body'];key=body['idempotencyKey'];found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:pending['taskId']=int(found)
    elif pending.get('submissionIntentAt'):raise RuntimeError('Repair submission outcome uncertain; inspect before retrying')
    else:
        self.idle();resolved=self.api('/api/character-story/resolve/Video',body);write(OUT/('shot'+str(number)+'-repair'+str(pending['attempt'])+'-resolved.json'),resolved)
        pending['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();pending['taskId']=self.api('/api/character-story/generate/Video',body)['id']
    saved={k:entry[k] for k in ['videoTaskId','status','assetPath','sha256','videoBody','inspection','tailPath','tailSha256','tailInspection','technicalCheckPath'] if k in entry}
    if not any(x['videoTaskId']==saved['videoTaskId'] for x in history):history.append(saved)
    for k in ['assetPath','sha256','inspection','tailPath','tailSha256','tailInspection','technicalCheckPath','comfyPromptId','failure']:entry.pop(k,None)
    entry.update(videoTaskId=pending['taskId'],videoBody=body,status='Pending');entry.pop('repairPending',None);self.save();print('Shot '+str(number)+' targeted repair queued '+str(entry['videoTaskId']))
 def captions(self):
    self.preserve();lines=[];tracks=[]
    def stamp(seconds):
        ms=round(seconds*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    for e in self.state['narration']:
        if e.get('status')!='Succeeded' or sha(DATA/e['assetPath'])!=e['sha256']:raise RuntimeError('Narration missing or changed')
        probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-show_entries','format=duration','-of','json',str(DATA/e['assetPath'])],encoding='utf-8'))
        duration=float(probe['format']['duration']);start=e['startSeconds'];end=start+duration
        if end>14.9 or duration<=0:raise RuntimeError('Narration does not fit the 15-second edit')
        e['durationSeconds']=duration;lines.append(f"{e['index']}\n{stamp(start)} --> {stamp(end)}\n{e['text']}\n")
        tracks.append(dict(path=e['assetPath'],volume=1,startSeconds=start,tempo=1))
    music=self.state['music']
    if music.get('status')!='Succeeded' or sha(DATA/music['assetPath'])!=music['sha256']:raise RuntimeError('Music missing or changed')
    tracks.append(dict(path=music['assetPath'],volume=.12,startSeconds=0,tempo=1,fadeOutStartSeconds=13.8,fadeOutDurationSeconds=1.2))
    path=OUT/'window-narration.srt';content=('\n'.join(lines)).encode('utf-8')
    if path.exists() and path.read_bytes()!=content:raise RuntimeError('Existing subtitles differ; preserve them')
    if not path.exists():path.write_bytes(content)
    self.state['captions']=dict(assetPath=path.relative_to(DATA).as_posix(),sha256=sha(path));self.state['audioTracks']=tracks;self.save();print('Caption timing and separate narration/music tracks frozen for a 15-second edit.')
 def preview(self):
    self.preserve();self.idle();entry=self.state.setdefault('silentPreview',{})
    if entry.get('taskId'):print('Existing checked clip preview retained '+str(entry['taskId']));return
    for shot in self.state['shots']:
        if shot.get('inspection',{}).get('payload',{}).get('decision')!='Passed' or sha(DATA/shot['assetPath'])!=shot['sha256']:raise RuntimeError('Each actual shot must pass preview inspection before assembly')
    ids=[self.state['sourceVideoTaskId']]+[x['videoTaskId'] for x in self.state['shots']]
    body=dict(episodeId=self.state['episodeId'],taskIds=ids,audioPath=None,idempotencyKey=self.key('silent-preview'))
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen preview request changed')
    entry['body']=body;self.save();found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+body['idempotencyKey']+"' LIMIT 1;")
    if found:entry['taskId']=int(found);self.save();print('Recovered checked preview '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Preview submission uncertain; inspect before retrying')
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/character-story/preview',body);entry.update(taskId=result['id'],status='Pending');self.state['stage']='SilentPreviewQueued';self.save();print('Checked, silent multi-shot preview queued '+str(result['id']))
 def mix(self):
    self.preserve();self.idle();entry=self.state.setdefault('finalVideo',{});source=self.state['silentPreview']
    if entry.get('taskId'):print('Existing final delivery retained '+str(entry['taskId']));return
    if source.get('status')!='Succeeded' or sha(DATA/source['assetPath'])!=source['sha256']:raise RuntimeError('Checked silent preview missing or changed')
    tracks=self.state['audioTracks'];captions=self.state['captions'];sources=[dict(path=source['assetPath'],sha256=source['sha256'])]
    for track in tracks:
        known=next((e for e in [*self.state['narration'],self.state['music']] if e.get('assetPath')==track['path']),None)
        if not known or sha(DATA/track['path'])!=known['sha256']:raise RuntimeError('Audio source changed')
        sources.append(dict(path=track['path'],sha256=known['sha256']))
    if sha(DATA/captions['assetPath'])!=captions['sha256']:raise RuntimeError('Caption source changed')
    sources.append(dict(path=captions['assetPath'],sha256=captions['sha256']))
    body=dict(projectId=self.state['projectId'],taskType='Concat',resourceClass='CPU',dependencyTaskId=source['taskId'],maxRetries=0,stage='Story-Narrated-Review-Preview',idempotencyKey=self.key('final-mix'),parameters=dict(files=[source['assetPath']],targetWidth=864,targetHeight=480,targetFps=24,targetDurationSeconds=15,originalAudioVolume=0,audioTracks=tracks,subtitlePath=captions['assetPath'],sourceChecks=sources,outputName='window_waiting_15s_narrated.mp4'))
    if entry.get('body') and entry['body']!=body:raise RuntimeError('Frozen final mix request changed')
    entry['body']=body;self.save();key=body['idempotencyKey'];found=mysql("SELECT id FROM generation_tasks WHERE idempotency_key='"+key+"' LIMIT 1;")
    if found:entry['taskId']=int(found);self.save();print('Recovered final mix '+found);return
    if entry.get('submissionIntentAt'):raise RuntimeError('Final mix submission uncertain; inspect before retrying')
    check=self.api('/api/tasks/preflight',body);write(OUT/'final-preflight.json',check)
    if not check['passed']:raise RuntimeError('Final mix preflight rejected: '+str(check['issues']))
    entry['submissionIntentAt']=datetime.datetime.now().astimezone().isoformat();self.save();result=self.api('/api/tasks',body);entry.update(taskId=result['id'],status='Pending');self.state['stage']='FinalMixQueued';self.save();print('15-second narration, music and subtitle mix queued '+str(result['id']))
 def review_final(self,note):
    if not note:raise RuntimeError('Actual final media inspection note required')
    self.preserve();final=self.state['finalVideo'];report=json.loads((OUT/'final-technical-checks.json').read_text(encoding='utf-8'))
    if final.get('status')!='Succeeded' or report['status']!='Passed' or report['finalTaskId']!=final['taskId'] or sha(DATA/final['assetPath'])!=final['sha256']:raise RuntimeError('Review the actual verified final video')
    self.state.update(finalInspection=note,finalInspectionScope='PreviewInspection',stage='FinalPreviewInspected',contentReview='NeedReview',publication='Blocked');self.save();print('Final visual preview inspection recorded; listening and human approval remain pending.')
 def tick(self):
    for entry in self.state['narration']:
        if not entry.get('taskId'):continue
        detail=self.api('/api/tasks/'+str(entry['taskId']));entry['status']=detail['task']['status']
        if entry['status']=='Succeeded':
            asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith('.wav'))
            entry.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
        elif entry['status'] in ['Failed','Cancelled']:entry['failure']=detail['task'].get('errorMessage')
    entry=self.state.get('music',{})
    if entry.get('taskId'):
        detail=self.api('/api/tasks/'+str(entry['taskId']));entry['status']=detail['task']['status']
        if entry['status']=='Succeeded':
            asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith('.wav'));entry.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
        elif entry['status'] in ['Failed','Cancelled']:entry['failure']=detail['task'].get('errorMessage')
    for shot in self.state['shots']:
        if not shot.get('videoTaskId'):continue
        detail=self.api('/api/tasks/'+str(shot['videoTaskId']));shot['status']=detail['task']['status']
        if shot['status']=='Succeeded':
            asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith('.mp4'));shot.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
            receipt=DATA/('CharacterStoryTrace/task_'+str(shot['videoTaskId']))/'submission.json'
            if receipt.exists():shot['comfyPromptId']=json.loads(receipt.read_text(encoding='utf-8'))['promptId']
        elif shot['status'] in ['Failed','Cancelled']:shot['failure']=detail['task'].get('errorMessage')
    for key in ['silentPreview','finalVideo']:
        item=self.state.get(key,{})
        if not item.get('taskId'):continue
        detail=self.api('/api/tasks/'+str(item['taskId']));item['status']=detail['task']['status']
        if item['status']=='Succeeded':
            asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith('.mp4'));item.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
        elif item['status'] in ['Failed','Cancelled']:item['failure']=detail['task'].get('errorMessage')
    self.save();print(json.dumps(dict(narration=[dict(index=e['index'],taskId=e.get('taskId'),status=e.get('status')) for e in self.state['narration']],music={k:entry.get(k) for k in ['taskId','status']},shots=[{k:x.get(k) for k in ['number','videoTaskId','status']} for x in self.state['shots']],silentPreview=self.state.get('silentPreview',{}).get('status'),finalVideo=self.state.get('finalVideo',{}).get('status')),ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','tts','shots','music','video','inspect','repair','captions','preview','mix','review-final','tick']);parser.add_argument('--index',type=int,choices=[1,2,3]);parser.add_argument('--decision',choices=['Passed','Failed']);parser.add_argument('--note');parser.add_argument('--prompt');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        run=Continuation()
        if args.command=='prepare':run.prepare()
        elif args.command=='tts':
            if not args.index:parser.error('--index is required')
            run.tts(args.index)
        elif args.command=='shots':run.shots()
        elif args.command=='music':run.music()
        elif args.command=='video':
            if args.index not in [2,3]:parser.error('--index must be 2 or 3')
            run.video(args.index)
        elif args.command in ['inspect','repair']:
            if args.index not in [2,3]:parser.error('--index must be 2 or 3')
            if args.command=='inspect':run.inspect(args.index,args.decision,args.note)
            else:run.repair(args.index,args.note,args.prompt)
        elif args.command=='captions':run.captions()
        elif args.command=='preview':run.preview()
        elif args.command=='mix':run.mix()
        elif args.command=='review-final':run.review_final(args.note)
        else:run.tick()


if __name__=='__main__':main()

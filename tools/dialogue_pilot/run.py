"""Resumable local pilot; all inference and final export use the business queue."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[2]
AI=ROOT.parent
DATA=AI/'Data'
FOLDER=DATA/'DialoguePilot20261023'
FOLDER.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'tools/minimax'))
from run_local_acceptance import Acceptance,TaskFailure
from download_assets import download_lock

LINES=[
 dict(role='female',text='哟，约会回来了？',voice='qwen3:Vivian',emotion='年轻成年女性，轻轻挑眉，带笑打趣熟悉的朋友。轻松口语普通话，重音在“约会”，结尾自然上扬，亲近但不夸张，不要朗诵，不加其他词。'),
 dict(role='male',text='哼，要你管。',voice='qwen3:Dylan',emotion='年轻成年男性，佯装不服，嘴角含笑，轻轻哼一声后回答，语速从容，熟人间的玩笑，不是真生气，不要喊，不要朗诵，不加其他词。'),
 dict(role='female',text='好啦，不逗你了。',voice='qwen3:Vivian',emotion='同一位年轻成年女性，笑意收住后温柔让步，轻声自然地说，语气亲近，普通话，不要夸张大笑，不要朗诵，不加其他词。'),
 dict(role='male',text='这还差不多。',voice='qwen3:Dylan',emotion='同一位年轻成年男性，玩笑得逞后的轻松满意，忍住笑，声音柔和，自然口语，不要喊，不要朗诵，不加其他词。'),
]

def sha(path):
    path=Path(path).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():raise RuntimeError('Media must stay inside the controlled Data directory')
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

class Pilot(Acceptance):
    def poll(self,task_id,limit=10800):
        start=time.monotonic()
        while time.monotonic()-start<limit:
            detail=self.api(f'/api/tasks/{task_id}')
            status=detail['task']['status']
            import psutil
            sample=dict(epoch=time.time(),taskId=task_id,status=status,progress=detail['task'].get('progress'),availableRamMiB=psutil.virtual_memory().available//1024**2)
            try:
                vals=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],encoding='utf-8',timeout=10)
                sample['gpu']=list(map(lambda v:int(v.strip()),vals.strip().split(',')))
            except (OSError,subprocess.SubprocessError):pass
            with (FOLDER/'resources.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(sample)+'\n')
            if status=='Succeeded':return detail
            if status in ['Failed','Cancelled']:raise TaskFailure(task_id,status,str(detail['task'].get('errorMessage'))[:2000])
            time.sleep(5)
        raise RuntimeError('Task unresolved; inspect recorded ID before any new submission')

def once(run,field,endpoint,body):
    if run.state.get(field+'Input') and run.state[field+'Input']!=body:raise RuntimeError('Frozen input changed: '+field)
    if not run.state.get(field):
        if run.state.get(field+'SubmissionStarted'):raise RuntimeError('Submission unresolved: '+field)
        if endpoint=='/api/tasks':
            pre=run.api('/api/tasks/preflight',body,timeout=600)
            (FOLDER/(field+'-preflight.json')).write_text(json.dumps(pre,ensure_ascii=False,indent=2),encoding='utf-8')
            if not pre['passed']:raise RuntimeError(str(pre['issues']))
        run.save(field,**{field+'Input':body,field+'SubmissionStarted':True})
        r=run.api(endpoint,body,key=field,timeout=600)
        run.save(**{field:r.get('id') or r.get('taskId')})
        print(field,run.state[field],flush=True)
    detail=run.poll(run.state[field])
    (FOLDER/(field+'-result.json')).write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
    return detail

def prepare(run):
    run.access()
    if not run.state.get('projectId'):
        name='午后双人对白_口型样片_'+run.state['runId'][:8]
        matches=[x for x in run.api('/api/projects') if x['name']==name]
        if matches:project=matches[0]['id']
        elif run.state.get('projectSubmissionStarted'):raise RuntimeError('Project submission unresolved')
        else:
            run.save('Preparing',projectSubmissionStarted=True)
            project=run.api('/api/projects',dict(name=name,description='Pure-local Qwen dialogue -> per-speaker audio/masks -> InfiniteTalk pilot. Human content review required.',defaultWidth=1280,defaultHeight=720,defaultFps=25))['id']
        run.save(projectId=project)
    (FOLDER/'dialogue-plan.json').write_text(json.dumps(dict(roles=dict(female='LEFT, beige knitted cardigan, long dark hair',male='RIGHT, olive cardigan, short black hair'),lines=LINES,sourceCharacterReference='project32 candidate1216; character reference only, new audio-driven video inference required',pipeline='Qwen3-TTS -> isolated speaker tracks -> InfiniteTalk Multi -> QA -> local detail restore/mix/export'),ensure_ascii=False,indent=2),encoding='utf-8')

def tts(run):
    for i,line in enumerate(LINES,1):
        detail=once(run,f'line{i}TaskId','/api/audio/tts',dict(projectId=run.state['projectId'],voiceId=line['voice'],text=line['text'],instruction=line['emotion'],speed=1,pitch=0,outputName=f'pilot_{i:02}_{line["role"]}.wav'))
        item=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').endswith('.wav'))
        path=item['assetPath'];audio,sr=sf.read(DATA/path)
        run.save(**{f'line{i}Path':path,f'line{i}Sha256':sha(DATA/path),f'line{i}Duration':len(audio)/sr})
    sr=24000;duration=9.64;length=round(sr*duration)
    roles={role:np.zeros(length,dtype=np.float32) for role in ['female','male']}
    cursor=.4;timeline=[]
    for i,line in enumerate(LINES,1):
        audio,rate=sf.read(DATA/run.state[f'line{i}Path'],dtype='float32')
        if rate!=sr or audio.ndim!=1:raise RuntimeError('Unexpected Qwen format')
        start=round(cursor*sr);end=start+len(audio)
        if end>length-round(.25*sr):raise RuntimeError('Dialogue too long; do not speed up or truncate it')
        roles[line['role']][start:end]=audio
        timeline.append(dict(index=i,**line,startSeconds=start/sr,endSeconds=end/sr,durationSeconds=len(audio)/sr,taskId=run.state[f'line{i}TaskId']))
        cursor=end/sr+.42
    for role,audio in roles.items():sf.write(FOLDER/f'{role}-9.64s.wav',audio,sr,subtype='PCM_16')
    mix=roles['female']+roles['male']
    sf.write(FOLDER/'dialogue-9.64s.wav',mix,sr,subtype='PCM_16')
    (FOLDER/'dialogue-timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
    run.save('DialogueReady',durationSeconds=duration,timeline=timeline)
    print(json.dumps(timeline,ensure_ascii=False),flush=True)

def video(run,frames):
    if run.state.get('stage')=='ReadyForUserPreview':
        print('Existing final pilot preserved; no inference submitted',flush=True);return
    if frames==125 and run.state.get('video125PublishedTaskId'):
        if sha(DATA/run.state['video125Path'])!=run.state['video125Sha256']:raise RuntimeError('Reviewed test clip changed')
        print('Existing exact 5-second test preserved; no inference submitted',flush=True);return
    if run.state.get(f'video{frames}Path'):
        if sha(DATA/run.state[f'video{frames}Path'])!=run.state[f'video{frames}Sha256']:raise RuntimeError('Existing video changed')
        print('Existing audio-driven video preserved; no inference submitted',flush=True);return
    if frames==241:
        review=json.loads((FOLDER/'inspection-125/review.json').read_text(encoding='utf-8'))
        if review.get('decision')!='SelectedForContinuation' or review.get('sourceSha256')!=run.state.get('video125Sha256'):raise RuntimeError('Inspect the actual short test before the complete pilot')
    version=f'infinitetalk-dialogue-{frames}-v2'
    run.api('/api/workflows/scan',{},timeout=180)
    workflow=next(x for x in run.api('/api/workflows') if x['name']==f'infinitetalk_dialogue_{frames}_exact_api')
    body=dict(projectId=run.state['projectId'],taskType='ImageToVideo',resourceClass='GPU',workflowId=workflow['id'],inputImagePath='DialoguePilot20261023/pilot-reference.png',stage='Dialogue-Pilot-InfiniteTalk',maxRetries=0,
        parameters=dict(workflowVersion=version,width=832,height=480,fps=25,frames=frames,duration=frames/25,steps=6,cfg=1,seed=2026102305,
            inputSlots=dict(firstFrame='DialoguePilot20261023/pilot-reference.png',femaleAudio='DialoguePilot20261023/female-9.64s.wav',maleAudio='DialoguePilot20261023/male-9.64s.wav')))
    detail=once(run,f'video{frames}TaskId','/api/tasks',body)
    item=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').endswith('.mp4'))
    path=item['assetPath']
    run.save('AwaitingVideoInspection',**{f'video{frames}Path':path,f'video{frames}Sha256':sha(DATA/path)})
    print(str(DATA/path),flush=True)

def exported_path(detail):
    return next(x['assetPath'] for x in detail['results'] if x.get('available') and x.get('assetPath','').endswith('.mp4'))

def finish(run,restore=False):
    review=FOLDER/'inspection-241/review.json'
    if not review.exists():raise RuntimeError('Inspect the actual complete audio-driven video before export')
    decision=json.loads(review.read_text(encoding='utf-8'))
    if sha(DATA/run.state['video241Path'])!=run.state['video241Sha256']:raise RuntimeError('Source video changed')
    if decision.get('sourceSha256')!=run.state['video241Sha256'] or decision.get('decision')!='SelectedForFinishing':raise RuntimeError('A traceable content review is required')
    # 9.50 s / 228 frames at 24FPS permits the already-installed conservative detail-restoration engine.
    # Only 0.14 s of the silent reaction tail is trimmed; all four complete utterances end at 8.78 s.
    if run.state['timeline'][-1]['endSeconds']>9.25:raise RuntimeError('Dialogue does not fit the delivery window')
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='Dialogue-Pilot-Detail-Canvas',maxRetries=0,
       parameters=dict(files=[run.state['video241Path']],targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=9.5,originalAudioVolume=0,outputName='dialogue_pilot_clean_720p.mp4'))
    detail=once(run,'canvasTaskId','/api/tasks',body);canvas=exported_path(detail)
    run.save(canvasPath=canvas,canvasSha256=sha(DATA/canvas))
    if not restore:return
    status=run.api('/api/video-restore/status')
    if not status['ready']:raise RuntimeError(status['message'])
    body=dict(projectId=run.state['projectId'],taskType='VideoRestore',resourceClass='GPU',stage='Dialogue-Pilot-Conservative-Detail',maxRetries=0,
       parameters=dict(input=canvas,sourceSha256=sha(DATA/canvas),engineVersion=status['engineVersion'],strength=.45,cutFrames=[]))
    detail=once(run,'restoreTaskId','/api/tasks',body);path=exported_path(detail)
    run.save('AwaitingRestorationInspection',restorePath=path,restoreSha256=sha(DATA/path))
    print(str(DATA/path),flush=True)

def assemble(run):
    review=FOLDER/'restoration-review.json'
    if not review.exists():raise RuntimeError('Inspect restored faces and mouths before final mix')
    selected=json.loads(review.read_text(encoding='utf-8'))
    path=selected['selectedPath'];expected=selected['selectedSha256']
    if sha(DATA/path)!=expected:raise RuntimeError('Selected finishing media changed')
    mix=json.loads((FOLDER/'mix-preparation.json').read_text(encoding='utf-8'))
    if sha(FOLDER/'dialogue-room-9.5s.wav')!=mix['mixSha256'] or sha(FOLDER/'dialogue.srt')!=mix['subtitleSha256']:raise RuntimeError('Audio/subtitle preparation changed')
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='Dialogue-Pilot-Final-Mix',maxRetries=0,
        parameters=dict(files=[path],targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=9.5,originalAudioVolume=0,audioTracks=[dict(path='DialoguePilot20261023/dialogue-room-9.5s.wav',volume=1,startSeconds=0,tempo=1)],subtitlePath='DialoguePilot20261023/dialogue.srt',outputName='two_person_dialogue_local_9.5s.mp4'))
    detail=once(run,'finalTaskId','/api/tasks',body);path=exported_path(detail)
    run.save('AwaitingDeliveryVerification',finalPath=path,finalSha256=sha(DATA/path))
    print(str(DATA/path),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','tts','test','video','canvas','restore','assemble','check'],required=True);args=parser.parse_args()
    run=Pilot('http://127.0.0.1:18080',FOLDER/'run.json')
    if args.stage=='check' or run.state.get('stage')=='ReadyForUserPreview':
        run.access()
        for key in ['final','video125','video241','restore']:
            if run.state.get(key+'Path') and sha(DATA/run.state[key+'Path'])!=run.state[key+'Sha256']:raise RuntimeError('Recorded media changed: '+key)
        print('Read-only verification; no task submitted. Stage='+run.state['stage'],flush=True)
        return
    with download_lock(FOLDER,filename='.pilot-run.lock',conflict='Another pilot runner is already active; inspect its recorded tasks'):
        run=Pilot('http://127.0.0.1:18080',FOLDER/'run.json')
        prepare(run)
        if args.stage=='tts':tts(run)
        if args.stage in ['test','video']:video(run,125 if args.stage=='test' else 241)
        if args.stage in ['canvas','restore']:finish(run,args.stage=='restore')
        if args.stage=='assemble':assemble(run)

if __name__=='__main__':main()

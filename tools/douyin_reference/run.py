"""Fresh local two-person story. All inference/export goes through VideoStudio's queue."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'DouyinReference20261023'
REPORT = FOLDER / 'run.json'
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from run_local_acceptance import Acceptance, TaskFailure
from download_assets import download_lock
from run_quality import artifact

FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'
FFPROBE = r'C:\install\FFmpeg\bin\ffprobe.exe'
REFERENCE_SHA = 'c1f0500e78d9b55ded016551e417c0b28a5c54367ffc8137b7a4bc5ce898da50'
FRAME_PROMPT = (
    'Realistic live action movie photograph, medium wide two-person shot at eye level. '
    'Exactly two fictional East Asian adults in a warm sunlit modern living room. '
    'On the LEFT, one 28-year-old man with short neat black hair, wearing a plain brown long sleeve shirt '
    'and beige trousers, stands beside a cream fabric sofa and smiles toward the woman. '
    'On the RIGHT, one 27-year-old woman with long wavy dark hair, wearing an olive green knitted cardigan '
    'over a plain cream crew neck T-shirt and a black knee length skirt, sits upright on the cream sofa. '
    'She holds a small smartphone and looks toward the man. Both adult faces are clearly visible. '
    'A low round wooden coffee table in front of them holds one clear glass of water and a yellow snack bag. '
    'Simple white walls, pale wood floor, wooden door on the far left, a large bright window on the right. '
    'Natural afternoon sunlight, coherent furniture, realistic skin and clothing, understated expressions, '
    '35mm lens, unretouched documentary photography, balanced horizontal framing, both people distinct.')
NEGATIVE = ('child, teenager, multiple men, multiple women, crowd, twins, duplicate people, '
    'extra limbs, fused bodies, malformed hands, cartoon, illustration, CGI, doll, plastic skin, '
    'airbrushed face, beauty filter, text, subtitles, watermark, logo, collage, bare chest')
SHOTS = [
    dict(number=1, title='回家打趣', action=(
        'The man beside the sofa takes one small step toward the woman and sits on the LEFT end of the sofa. '
        'The woman on the RIGHT lowers her phone to the sofa cushion beside her, turns toward him with a playful smile. '
        'They exchange a short casual greeting, looking at each other. Keep both faces visible.'),
        dialogue='The woman says in Mandarin: "哟，约会回来了？" The man replies: "哼，要你管。"'),
    dict(number=2, title='零食撒落', action=(
        'Both adults remain on the same cream sofa. The woman playfully gestures toward the man\'s cheek while teasing him. '
        'The man gives an exaggerated surprised smile. He reaches toward the yellow snack bag on the coffee table '
        'and accidentally tips a few chips onto the sofa cushion. The glass stays upright on the table.'),
        dialogue='The woman says in Mandarin: "几天没见，感觉你脸圆了些。" The man replies: "你才圆呢！"'),
    dict(number=3, title='沙发嬉闹', action=(
        'The man turns toward the woman and briefly tickles her forearm with his fingertips. '
        'She laughs, leans a little sideways against the sofa cushion and gently blocks his hand with her palm. '
        'Both remain fully clothed and seated, with their feet on the floor, separate natural bodies. '
        'This is light friendly play. Keep their faces and hands visible, no wrestling, no climbing on each other.'),
        dialogue='The man says in Mandarin: "还敢说我胖？" The woman laughs: "啊哈哈，不说了！"'),
    dict(number=4, title='抱枕反击', action=(
        'The woman picks up the small cream cushion beside her and gently places it between their arms, '
        'ending the tickling. Both laugh. The man withdraws his hand. The woman taps his forearm once with the cushion. '
        'They return to upright seated positions, looking at each other, calm playful expressions.'),
        dialogue='The woman says in Mandarin: "犯规！叫姐姐！" The man replies: "就不叫。"'),
    dict(number=5, title='起身追逐', action=(
        'The man stands up from the LEFT end of the sofa and moves three small quick steps toward the wooden doorway on the LEFT. '
        'He looks back at the woman with a mischievous grin. The woman puts the cushion on the sofa, stands up and '
        'takes two steps after him. Camera gently pans left, both adults stay clearly separate, no running into furniture.'),
        dialogue='The man says in Mandarin: "来呀，来抓我呀！" The woman replies: "别跑！"'),
    dict(number=6, title='门口收尾', action=(
        'The man reaches the wooden doorway on the LEFT, steps through it and leaves the frame. '
        'The woman follows two small steps, then stops just inside the living room near the doorway. '
        'She puts one hand on her waist and smiles with mock annoyance, then relaxes. '
        'Hold the sunlit room and her final expression for the last second, one continuous shot.'),
        dialogue='The woman says in Mandarin with playful mock annoyance: "气死我了！"')
]
LINES = [
    (1.0, 'female', '哟，约会回来了？'), (3.1, 'male', '哼，要你管。'),
    (5.65, 'female', '几天没见，感觉你脸圆了些。'), (9.5, 'male', '你才圆呢！'),
    (11.9, 'male', '还敢说我胖？'), (14.0, 'female', '啊哈哈，不说了！'),
    (17.0, 'female', '犯规！叫姐姐！'), (19.65, 'male', '就不叫。'),
    (22.0, 'male', '来呀，来抓我呀！'), (25.0, 'female', '别跑！'),
    (28.1, 'female', '气死我了！')
]


def sha(path):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError('Media must stay inside Data')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE, '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(path)], encoding='utf-8'))


class StoryRun(Acceptance):
    def poll(self, task_id, limit=7500):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            detail = self.api(f'/api/tasks/{task_id}')
            status = detail['task']['status']
            sample = dict(epoch=time.time(), taskId=task_id, status=status, progress=detail['task'].get('progress'))
            try:
                import psutil
                gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu',
                    '--format=csv,noheader,nounits'], encoding='utf-8', timeout=10)
                used, free, util = [int(v.strip()) for v in gpu.strip().split(',')]
                sample.update(usedVramMiB=used, freeVramMiB=free, utilizationPercent=util,
                    systemAvailableMiB=round(psutil.virtual_memory().available/1024**2))
            except (OSError, subprocess.SubprocessError):
                sample['resourceSampleUnavailable'] = True
            with (FOLDER/'resources.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(sample)+'\n')
            if status == 'Succeeded':
                return detail
            if status in ['Failed', 'Cancelled']:
                raise TaskFailure(task_id, status, f'Task {task_id} {status}: '+str(detail['task'].get('errorMessage') or '')[:2000])
            time.sleep(5)
        raise RuntimeError(f'Task {task_id} unresolved; inspect before resubmitting')


def once(run, field, stage, endpoint, body):
    if run.state.get(field+'Input') and run.state[field+'Input'] != body:
        raise RuntimeError('Frozen submitted input changed: '+field)
    if not run.state.get(field):
        if run.state.get(field+'SubmissionStarted'):
            raise RuntimeError('Submission outcome unresolved: '+field)
        if endpoint == '/api/tasks':
            preflight = run.api('/api/tasks/preflight', body)
            (FOLDER/(field+'-preflight.json')).write_text(json.dumps(preflight,ensure_ascii=False,indent=2),encoding='utf-8')
            if not preflight['passed']:
                raise RuntimeError(str(preflight['issues']))
        run.save(stage, **{field+'SubmissionStarted':True, field+'Input':body})
        result = run.api(endpoint, body, key=field, timeout=600)
        task_id = result.get('id') or result.get('taskId')
        if not task_id:
            raise RuntimeError('No task ID returned')
        run.save(**{field:task_id})
        print(f'{field}={task_id}', flush=True)
    detail = run.poll(run.state[field])
    (FOLDER/(field+'-result.json')).write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
    return detail


def prepare(run):
    run.access()
    reference = FOLDER/'reference-7699361421842789233.mp4'
    if sha(reference) != REFERENCE_SHA:
        raise RuntimeError('Original reference changed')
    plan = dict(title='午后小日常：男女双人本地复刻', referenceUrl='https://www.douyin.com/video/7699361421842789233',
        referenceSha256=REFERENCE_SHA, referenceVideo=dict(width=1280,height=720,fps=30,durationSeconds=30.7),
        referenceAcquisition='Browser pageAssets export of the exact visible video; no cookies or private APIs',
        referencePlot='Two adult women return home, tease about dating and weight, spill chips, tickle and laugh on the sofa, chase to the doorway.',
        adaptation='Two new fictional adults, one man and one woman; same sunlit living-room setting and narrative beats. Friendly forearm tickling and cushion play.',
        sourceCanvas=[1376,768], sourceFps=24, framesPerShot=124, shotCount=6, outputWidth=1280, outputHeight=720,
        durationSeconds=31, profile='quality768', steps=20, shotPlan=SHOTS, dialogueLines=LINES,
        lipsyncStatus='Not verified; H3 speech-conditioned visual prompts plus independently generated Qwen dialogue, not an installed MultiTalk pipeline')
    for key, value in plan.items():
        # JSON round-trips tuples as arrays.
        value = json.loads(json.dumps(value,ensure_ascii=False))
        if run.state.get('projectId') and key in run.state and run.state[key] != value:
            raise RuntimeError('Frozen plan changed: '+key)
        run.state[key] = value
    run.save(error=None)
    if not run.state.get('projectId'):
        name = '午后小日常_男女双人本地_'+run.state['runId'][:8]
        matches = [p for p in run.api('/api/projects') if p['name'] == name]
        if matches:
            project_id = matches[0]['id']
        elif run.state.get('projectSubmissionStarted'):
            raise RuntimeError('Project submission unresolved')
        else:
            run.save('CreatingProject',projectSubmissionStarted=True)
            project_id = run.api('/api/projects',dict(name=name,description='Fresh local two-adult living-room story based on inspected Douyin reference. Human review required.',
                defaultWidth=1280,defaultHeight=720,defaultFps=24))['id']
        run.save(projectId=project_id)
    (FOLDER/'story-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')


def frame(run, attempt):
    if any(run.state.get(f'shot{number}TaskId') for number in range(1,7)):
        raise RuntimeError('Video inputs are already frozen; do not regenerate or reselect the opening frame')
    if attempt not in (1,2,3):
        raise RuntimeError('A targeted changed prompt must be documented before another frame attempt')
    workflow_name='realvisxl_openpose_reference_api' if attempt==2 else 'realvisxl_reference_api'
    workflow = next(w['id'] for w in run.api('/api/workflows') if w['name']==workflow_name)
    parameters=dict(workflowVersion='realvisxl-reference-1536-v1',positive=FRAME_PROMPT,negative=NEGATIVE,
        width=1536,height=864,seed=2026102301,steps=35,cfg=5.5,sampler_name='dpmpp_sde',scheduler='karras',denoise=1)
    if attempt==2:
        rejection=json.loads((FOLDER/'reference-1-rejection.json').read_text(encoding='utf-8'))
        if rejection.get('decision')!='Failed' or rejection.get('taskId')!=run.state['firstFrameTaskId']:
            raise RuntimeError('Inspect the initial frame before targeted repair')
        guide=FOLDER/'two-person-pose.png'
        if not guide.exists(): raise RuntimeError('Prepare the two-person pose guide first')
        parameters.update(workflowVersion='realvisxl-openpose-reference-1536-v1',seed=2026102302,
            inputSlots=dict(pose=guide.relative_to(DATA).as_posix()),positive=(
                'Wide full-body live-action photograph. Exactly two East Asian adults in a sunny living room. '
                'On the LEFT one adult MAN stands upright, short black hair, plain BROWN shirt, BEIGE trousers. '
                'On the RIGHT one adult WOMAN sits on a cream sofa, long dark wavy hair, OLIVE GREEN cardigan, '
                'CREAM T-shirt, BLACK knee length skirt. Their hands are empty and relaxed. '
                'Both separate adult faces and full bodies visible. A round wooden coffee table in front holds '
                'a clear water glass and one yellow potato chip bag. Wooden doorway on the left, white wall, pale wood floor, '
                'large bright window on the right, warm afternoon natural light, realistic skin and fabric, documentary movie still.'),
            negative=NEGATIVE+', close-up, cropped body, paperwork, documents, reading, hugging')
    if attempt==3:
        rejection=json.loads((FOLDER/'reference-2-rejection.json').read_text(encoding='utf-8'))
        if rejection.get('decision')!='Failed': raise RuntimeError('Inspect the pose result first')
        parameters.update(seed=2026102303,positive=(
            'Wide live-action movie photograph of a sunlit modern living room. '
            'Exactly one adult Chinese man and one adult Chinese woman sit apart on a cream fabric sofa, talking. '
            'The man wears a plain brown sweatshirt and beige trousers. '
            'The woman wears an olive green cardigan, a cream T-shirt and a black skirt. '
            'Both faces, hands and knees clearly visible. A round wood coffee table in front has a yellow bag of potato chips '
            'and a clear water glass. A wood door on the left. Bright window on the right. '
            'White walls, pale wood floor. Natural skin and clothing, warm soft sunlight, realistic documentary film still.'),
            negative=NEGATIVE+', paperwork, documents, reading, bathrobe, dressing gown, kimono, standing, formal suit, close-up')
    field='firstFrameTaskId' if attempt==1 else f'firstFrame{attempt}TaskId'
    detail = once(run,field,'GeneratingTwoPersonReference','/api/tasks',dict(projectId=run.state['projectId'],
        taskType='Image',resourceClass='GPU',workflowId=workflow,stage='TwoPerson-LivingRoom-Reference',maxRetries=0,
        parameters=parameters))
    path = artifact(detail,('.png',))
    run.save('AwaitingReferenceInspection',firstFramePath=path,firstFrameSha256=sha(DATA/path),
        **{f'candidate{attempt}Path':path,f'candidate{attempt}Sha256':sha(DATA/path)})
    print(json.dumps(dict(path=str(DATA/path))),flush=True)


def tts(run):
    for index, (_,role,text) in enumerate(LINES,1):
        field = f'dialogue{index}TaskId'
        voice = 'qwen3:Vivian' if role=='female' else 'qwen3:Dylan'
        instruction = ('年轻成年女性，轻松自然的普通话，和熟悉的朋友互相打趣，有笑意，语速自然稍快，不要朗诵。'
            if role=='female' else '年轻成年男性，轻松自然的普通话，和熟悉的朋友互相打趣，有笑意，语速自然稍快，不要朗诵。')
        detail = once(run,field,'GeneratingQwenDialogue','/api/audio/tts',dict(projectId=run.state['projectId'],
            voiceId=voice,text=text,instruction=instruction,speed=1,pitch=0,outputName=f'dialogue_{index:02}_{role}.wav'))
        path = artifact(detail,('.wav',))
        duration = float(probe(DATA/path)['format']['duration'])
        run.save(**{f'dialogue{index}Path':path,f'dialogue{index}Sha256':sha(DATA/path),f'dialogue{index}DurationSeconds':duration})
    run.save('DialogueReady')


def make_contact(run, number, path):
    folder = FOLDER/f'shot-{number:02}'
    folder.mkdir(exist_ok=True)
    contact = Image.new('RGB',(1376,768),'#111')
    for i,index in enumerate([0,40,80,123]):
        target = folder/f'frame-{index:03}.png'
        if not target.exists():
            subprocess.run([FFMPEG,'-v','error','-i',str(DATA/path),'-vf',f'select=eq(n\\,{index})',
                '-frames:v','1','-n',str(target)],check=True)
        image = Image.open(target).convert('RGB'); image.thumbnail((688,384))
        contact.paste(image,((i%2)*688,(i//2)*384))
    ImageDraw.Draw(contact).text((6,6),f'Shot {number}: frames 0 / 40 / 80 / 123',fill='white')
    contact.save(folder/'contact.jpg',quality=92)


def video(run,number):
    if number==1:
        review_path = FOLDER/'reference-review.json'
        reference = run.state['firstFramePath']
    else:
        review_path = FOLDER/f'shot-{number-1:02}/review.json'
        reference = str((FOLDER/f'shot-{number-1:02}/frame-123.png').relative_to(DATA)).replace('\\','/')
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if review.get('decision') != 'SelectedForContinuation':
        raise RuntimeError('Inspect the actual reference before continuation')
    if sha(DATA/reference) != review['referenceSha256']:
        raise RuntimeError('Inspected reference hash differs')
    shot = SHOTS[number-1]
    staging=json.loads((FOLDER/'staging.json').read_text(encoding='utf-8'))
    if staging.get('referenceSha256')!=run.state['firstFrameSha256']:
        raise RuntimeError('Staging is not based on the inspected actual frame')
    action=staging.get('actions',{}).get(str(number),shot['action'])
    anchors=staging.get('anchorsByShot',{}).get(str(number),staging['anchors'])
    prompt = ('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
        'integrated_multimodal_description: [Shot 1] Realistic live-action domestic comedy. '
        +anchors+' '
        'Begin at the exact positions visible in the reference. '+action+' '+shot['dialogue']+
        ' Natural subtle facial expressions and visible conversational mouth movement. '
        'One continuous steady eye-level shot, realistic anatomy, consistent faces, no extra people, no cuts, no on-screen text.\n\n'
        'overall_soundscape: Quiet living room, natural Mandarin conversation, light laughter, soft fabric and footsteps. '
        +shot['dialogue']+'\n\nnon_diegetic_music: None.')
    field=f'shot{number}TaskId'
    if not run.state.get(field):
        run.api('/api/minimax/local/verify',{},timeout=600)
    detail=once(run,field,f'GeneratingShot{number}','/api/minimax/local/video',dict(projectId=run.state['projectId'],
        profile='quality768',textToVideo=False,inputImagePath=reference,prompt=prompt,seed=2026102340+number,steps=20))
    path=artifact(detail,('.mp4',)); metadata=probe(DATA/path)
    v=next(s for s in metadata['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames'])) != (1376,768,'24/1',124):
        raise RuntimeError('Actual new shot specification differs')
    graph=json.loads(metadata['format']['tags']['prompt'])
    if graph['6']['inputs']['prompt']!=prompt or graph['5'].get('is_changed')!=[sha(DATA/reference)] or graph['10']['inputs']['steps']!=20:
        raise RuntimeError('Actual graph differs from frozen reference/prompt/sampler')
    folder=FOLDER/f'shot-{number:02}'; folder.mkdir(exist_ok=True)
    (folder/'execution-graph.json').write_text(json.dumps(graph,indent=2),encoding='utf-8')
    make_contact(run,number,path)
    run.save(f'AwaitingShot{number}Inspection',**{f'shot{number}VideoPath':path,f'shot{number}VideoSha256':sha(DATA/path),
        f'shot{number}InputFrameSha256':sha(DATA/reference),f'shot{number}TaskMetrics':detail['task']})
    print(json.dumps(dict(contact=str(folder/'contact.jpg'))),flush=True)


def timestamp(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def assemble(run):
    files=[]; sources=[]; tracks=[]; captions=[]
    for number in range(1,7):
        review=json.loads((FOLDER/f'shot-{number:02}/review.json').read_text(encoding='utf-8'))
        if review.get('decision')!='SelectedForContinuation': raise RuntimeError('Inspect all shots before export')
        path=run.state[f'shot{number}VideoPath']
        if sha(DATA/path)!=run.state[f'shot{number}VideoSha256']: raise RuntimeError('Source changed')
        files.append(path); sources.append(dict(path=path,sha256=sha(DATA/path),taskId=run.state[f'shot{number}TaskId']))
    for index,(start,role,text) in enumerate(LINES,1):
        path=run.state[f'dialogue{index}Path']; duration=run.state[f'dialogue{index}DurationSeconds']
        if sha(DATA/path)!=run.state[f'dialogue{index}Sha256']: raise RuntimeError('Dialogue changed')
        window=(LINES[index][0] if index<len(LINES) else 30.8)-start-.1
        tempo=max(1,round(duration/window+.001,3))
        if tempo>1.5: raise RuntimeError(f'Dialogue {index} does not naturally fit: duration={duration},window={window}')
        tracks.append(dict(path=path,volume=1,startSeconds=start,tempo=tempo))
        captions.append(f'{index}\n{timestamp(start)} --> {timestamp(start+duration/tempo)}\n{text}\n')
    subtitle=FOLDER/'dialogue.srt'; content='\n'.join(captions).encode('utf-8')
    if subtitle.exists() and subtitle.read_bytes()!=content: raise RuntimeError('Frozen subtitles changed')
    subtitle.write_bytes(content)
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='TwoPerson-LivingRoom-Preview',maxRetries=0,
        parameters=dict(files=files,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=31,
            originalAudioVolume=0,audioTracks=tracks,subtitlePath=subtitle.relative_to(DATA).as_posix(),outputName='afternoon_two_person_local_31s.mp4'))
    run.save(assemblySources=sources,dialogueTracks=tracks,subtitleSha256=sha(subtitle))
    detail=once(run,'assemblyTaskId','AssemblingPreview','/api/tasks',body)
    path=artifact(detail,('.mp4',)); metadata=probe(DATA/path)
    v=next(s for s in metadata['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1280,720,'24/1',744):
        raise RuntimeError('Final specification mismatch')
    if not any(s['codec_type']=='audio' for s in metadata['streams']): raise RuntimeError('Audio missing')
    subprocess.run([FFMPEG,'-v','error','-i',str(DATA/path),'-f','null','-'],check=True)
    (FOLDER/'final-probe.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    run.save('AwaitingPlaybackInspection',finalVideoPath=path,finalVideoSha256=sha(DATA/path),technicalStatus='Passed',
        contentStatus='NeedReview',publicationStatus='Blocked',error=None)
    print(json.dumps(dict(videoPath=str(DATA/path))),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','frame','tts','video','assemble','check'],required=True)
    parser.add_argument('--shot',type=int,choices=range(1,7),default=1)
    parser.add_argument('--attempt',type=int,default=1)
    args=parser.parse_args(); FOLDER.mkdir(parents=True,exist_ok=True)
    with download_lock(FOLDER,'.two-person-story.lock','Another story runner is active'):
        run=StoryRun('http://127.0.0.1:18080',REPORT)
        try:
            run.access()
            if run.state.get('stage')=='ReadyForUserPreview':
                if run.api(f'/api/tasks/{run.state["assemblyTaskId"]}')['task']['status']!='Succeeded' or sha(DATA/run.state['finalVideoPath'])!=run.state['finalVideoSha256']:
                    raise RuntimeError('Existing completed delivery differs')
                print(json.dumps(dict(stage='ReadyForUserPreview',newTaskSubmitted=False)),flush=True); return
            if args.stage=='prepare': prepare(run)
            elif args.stage=='frame': frame(run,args.attempt)
            elif args.stage=='tts': tts(run)
            elif args.stage=='video': video(run,args.shot)
            elif args.stage=='assemble': assemble(run)
            else: print(json.dumps(dict(stage=run.state['stage'],newTaskSubmitted=False)),flush=True)
        except Exception as error:
            status='Failed' if isinstance(error,TaskFailure) and error.status=='Failed' else 'Blocked'
            run.save(status,technicalStatus=status,error=str(error)[:2000])
            raise


if __name__=='__main__': main()

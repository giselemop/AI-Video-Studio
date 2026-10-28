"""One resumable, local-only full-body story preview, preserving all earlier work."""
import argparse
import datetime
import json
import io
import msvcrt
import re
import subprocess
import sys
import uuid
from pathlib import Path
import requests
from PIL import Image, ImageChops
sys.path.insert(0, str(Path(__file__).parent / 'character_scene'))
from common import ROOT, DATA, sha, write, mysql

OUT = DATA / 'CharacterFullBodyScene20261028'
FIRST = DATA / 'CharacterPlotPreview20261027/run.json'
OLD = DATA / 'CharacterPlotContinuation20261028/run.json'
CUT = DATA / 'CharacterSceneCutaway20261028/run.json'
HOLD = DATA / 'CharacterScene20261027/run.json'

IMAGE_PROMPT = (
    'Image1 is a single still from a real story; preserve the SAME woman and the SAME room. '
    'Move the camera several meters back to a single wide full-length shot. Exactly ONE adult East Asian woman, '
    'same apparent age, facial features, straight shoulder-length black hair and the exact ivory crew-neck '
    'knitted sweater shown in Image1. She sits calmly on a simple chair near the large wooden-framed window, '
    'facing the camera, her arms natural and both hands resting on her lap; both legs and feet rest on the floor. '
    'Show her complete body from the top of her hair to both entire shoes, with empty margin above and below. '
    'She wears straight-leg charcoal trousers and plain white low-top sneakers, without accessories. '
    'Behind her is the same warm wooden window and green trees outside, natural afternoon daylight. '
    'One continuous realistic horizontal 16:9 photograph with natural proportions and complete hands and feet, '
    'one face only, no second person, no extra heads, no reflections of people, no collage, no inset, no text.'
)
VIDEO_PROMPT = (
    'One continuous locked-camera wide full-body view of the same adult woman in the exact first frame. '
    'She remains quietly seated by the wooden window, both hands resting naturally, both feet on the floor, '
    'with very gentle breathing and an occasional natural blink. Keep her same face, age, black shoulder-length hair, '
    'ivory knit sweater, charcoal trousers and white shoes, and keep the window, chair and room stable. '
    'Exactly one woman, no extra people, no duplicate faces or limbs, no walking, no speech, no zoom, no camera cut.'
)

class Run:
 def __init__(self):
    self.path = OUT / 'run.json'
    self.base = 'http://127.0.0.1:18080'
    self.s = requests.Session()
    a = self.api('/api/auth/status')
    if a['accessMode'] != 'LocalOnly' or a['loginRequired']:
        raise RuntimeError('Local authenticated runtime is required')
    self.s.headers['X-CSRF-Token'] = a['csrfToken']
    self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
 def api(self, path, body=None):
    r = self.s.request('POST' if body is not None else 'GET', self.base + path, json=body, timeout=180)
    if not r.ok:
        raise RuntimeError(path + ' HTTP ' + str(r.status_code) + ' ' + r.text[:1000])
    return r.json()
 def save(self): write(self.path, self.state)
 def preserve(self):
    for item in self.state['protectedFiles']:
        if sha(Path(item['path'])) != item['sha256']:
            raise RuntimeError('Protected source changed: ' + item['path'])
 def require_reference(self):
    refs = mysql("SELECT id,JSON_UNQUOTE(JSON_EXTRACT(metadata_json,'$.humanReviewStatus')) FROM character_references WHERE id IN (36,43,44) ORDER BY id;")
    if refs.splitlines() != ['36\tApproved', '43\tRejected', '44\tRejected']:
        raise RuntimeError('Reference review state changed; inspect before continuing')
    versions = self.api('/api/character-library')['versions']
    version = next((v for v in versions if v['id'] == 3), None)
    if not version or version['sha256'] != self.state['sourceVersionSha256']:
        raise RuntimeError('Pinned source character version changed')
 def idle(self):
    h = self.api('/api/health')
    q = self.api('/api/minimax/local/status')['queue']
    c = requests.get('http://127.0.0.1:8188/queue', timeout=30).json()
    if not (h['database']['online'] and h['comfy']['online'] and h['ffmpeg']['available']
            and h['comfy']['gpu']['freeMiB'] >= 1024 and not q['paused']
            and q['gpuConcurrency'] == 1 and q['activeTasks'] == 0
            and not c['queue_running'] and not c['queue_pending']
            and mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');") == '0'):
        raise RuntimeError('Queue, GPU, services or resources are not ready')
 def prepare(self):
    if self.state:
        self.preserve()
        if 'sourceVersionSha256' not in self.state:
            first = json.loads(FIRST.read_text(encoding='utf-8'))
            if first['Keyframe']['sha256'] != self.state['sourceFrameSha256']:
                raise RuntimeError('Cannot recover the pinned character version')
            self.state['sourceVersionSha256'] = first['actorVersionSha256']
            self.save()
        print('Existing checkpoint retained; no task submitted.')
        return
    self.idle()
    first = json.loads(FIRST.read_text(encoding='utf-8'))
    prior = json.loads(CUT.read_text(encoding='utf-8'))
    old = json.loads(OLD.read_text(encoding='utf-8'))
    hold = json.loads(HOLD.read_text(encoding='utf-8'))
    if not (first['completed'] and first['Keyframe']['id'] == 1554 and first['sourceReference']['id'] == 36
            and prior['completed'] and prior['finalVideoTaskId'] == 1572 and old['completed']
            and hold['generationHold']['active']):
        raise RuntimeError('Prior sources or hold do not match the reviewed checkpoints')
    refs = mysql("SELECT id,JSON_UNQUOTE(JSON_EXTRACT(metadata_json,'$.humanReviewStatus')) FROM character_references WHERE id IN (36,43,44) ORDER BY id;")
    if refs.splitlines() != ['36\tApproved', '43\tRejected', '44\tRejected']:
        raise RuntimeError('Reference review state changed; inspect before creating a preview')
    source = first['Keyframe']
    identity = first['sourceReference']
    base = prior['editTasks']['final']
    if (sha(DATA/source['assetPath']) != source['sha256']
            or sha(DATA/identity['assetPath']) != identity['assetSha256']
            or sha(DATA/base['assetPath']) != base['sha256']):
        raise RuntimeError('Prior asset hash mismatch')
    tracks = old['finalVideo']['body']['parameters']['audioTracks']
    assert len(tracks) == 4 and tracks[2]['startSeconds'] == 10.8
    protected = [FIRST, OLD, CUT, HOLD, DATA/source['assetPath'], DATA/identity['assetPath'],
                 DATA/base['assetPath'], DATA/old['finalVideo']['assetPath'],
                 DATA/'CharacterPlotContinuation20261028/window-narration.srt']
    protected += [DATA/t['path'] for t in tracks]
    self.state = dict(runId=str(uuid.uuid4()), stage='Prepared', completed=False, projectId=54,
        episodeId=37, shotId=257, actorVersionId=3, sourceVersionSha256=first['actorVersionSha256'], sourceIdentityReferenceId=36,
        sourceIdentityPath=identity['assetPath'], sourceIdentitySha256=identity['assetSha256'],
        sourceFrameTaskId=1554, sourceFramePath=source['assetPath'], sourceFrameSha256=source['sha256'],
        baseTaskId=1572, basePath=base['assetPath'], baseSha256=base['sha256'],
        musicAndNarration=tracks, insertionFrame=210, insertionFrames=36, fps=24, finalFrames=396,
        lowerClothingNote='原剧情未显示裤鞋；参考人物设定文字新生成深灰裤子和白鞋，尚未经用户审核。',
        referenceNote='以剧情关键帧为唯一模型图像输入，已审核近照36用于血缘与人工对比；不使用被拒43/44。',
        protectedFiles=[dict(path=str(x),sha256=sha(x)) for x in protected],
        images=[], videos=[], editTasks={}, contentReview='NeedReview', publication='Blocked')
    self.save()
    print('Prepared separate provisional full-body preview; earlier holds and media preserved.')
 def submit(self, entry, body, label):
    key = 'fullbody:' + self.state['runId'] + ':' + label
    if not re.fullmatch(r'[A-Za-z0-9:-]+', key): raise RuntimeError('Invalid idempotency key')
    body['idempotencyKey'] = key
    if entry.get('body') and entry['body'] != body: raise RuntimeError('Frozen request changed')
    entry['body'] = body
    self.save()
    found = mysql("SELECT id FROM generation_tasks WHERE idempotency_key='" + key + "' LIMIT 1;")
    if found:
        entry['id'] = int(found)
        self.save()
        print('Recovered existing task ' + found)
        return
    if entry.get('submissionIntentAt'):
        raise RuntimeError('Submission outcome uncertain; inspect the database rather than resubmitting')
    pre = self.api('/api/tasks/preflight', body)
    write(OUT / (label + '-preflight.json'), pre)
    if not pre['passed']: raise RuntimeError('Preflight rejected: ' + str(pre['issues']))
    entry['submissionIntentAt'] = datetime.datetime.now().astimezone().isoformat()
    self.save()
    result = self.api('/api/tasks', body)
    entry.update(id=result['id'], status='Pending')
    self.save()
    print(label + ' queued ' + str(entry['id']))
 def next_entry(self, items, reason, adjustment):
    if items and not items[-1].get('id'):
        return items[-1]
    n = len(items)
    if n and items[-1].get('inspection', {}).get('decision') != 'Failed':
        raise RuntimeError('Only an inspected failed result can be repaired')
    if n > 2: raise RuntimeError('Two targeted repairs exhausted')
    if n and (not reason or not adjustment): raise RuntimeError('Record the failure and targeted correction')
    item = dict(attempt=n, reason=reason, adjustment=adjustment)
    items.append(item)
    self.save()
    return item
 def cut_reference(self):
    if self.state.get('cutReference'):
        ref = self.state['cutReference']
        if sha(DATA/ref['assetPath']) != ref['sha256']:
            raise RuntimeError('The saved actual cut reference changed')
        return ref
    ref_path = DATA/'CharacterSceneCutaway20261028/final/final-frames/frame-04.png'
    if not ref_path.exists(): raise RuntimeError('The earlier decoded cut frame is missing')
    ffmpeg = ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe'
    decoded = subprocess.run([str(ffmpeg),'-v','error','-i',str(DATA/self.state['basePath']),
        '-vf',r'select=eq(n\,209)','-frames:v','1','-f','image2pipe','-c:v','png','-'],
        capture_output=True,timeout=120,check=True).stdout
    with Image.open(io.BytesIO(decoded)) as actual, Image.open(ref_path) as prior:
        if actual.size != prior.size or ImageChops.difference(actual.convert('RGB'),prior.convert('RGB')).getbbox():
            raise RuntimeError('Stored frame does not match frame 209 of the actual prior video')
    ref = dict(assetPath=ref_path.relative_to(DATA).as_posix(),sha256=sha(ref_path),
               sourceVideoTaskId=self.state['baseTaskId'],sourceVideoSha256=self.state['baseSha256'],frame=209)
    self.state['cutReference']=ref
    self.state['protectedFiles'].append(dict(path=str(ref_path),sha256=ref['sha256']))
    self.save()
    return ref
 def image(self, reason, adjustment, source_choice):
    if self.state['completed']: raise RuntimeError('Completed run is read-only')
    self.preserve(); self.require_reference(); self.idle()
    e = self.next_entry(self.state['images'], reason, adjustment)
    e.setdefault('sourceChoice', source_choice)
    if e['attempt'] == 0 and e['sourceChoice'] != 'story':
        raise RuntimeError('The initial candidate uses the original story frame')
    ref = self.cut_reference() if e['sourceChoice'] == 'precut' else dict(
        assetPath=self.state['sourceFramePath'],sha256=self.state['sourceFrameSha256'],
        sourceVideoTaskId=self.state['sourceFrameTaskId'])
    e['sourcePath'],e['sourceSha256']=ref['assetPath'],ref['sha256']
    self.save()
    prompt = IMAGE_PROMPT + (' Targeted correction: ' + e['adjustment'] if e['adjustment'] else '')
    body = dict(projectId=54, taskType='Keyframe', workflowId=2441,
        inputImagePath=ref['assetPath'], dependencyTaskId=ref['sourceVideoTaskId'], resourceClass='GPU',
        stage='Fullbody-Scene-Experimental-Candidate', maxRetries=0,
        parameters=dict(workflowVersion='character-pack-klein4b-single-1536-v1',
          inputSlots=dict(firstFrame=ref['assetPath']), positive=prompt,
          seed=2026102811+e['attempt']*100, width=1536, height=864, steps=4, cfg=1))
    self.submit(e, body, 'image-'+str(e['attempt']))
    self.state['stage']='ImageQueued'; self.save()
 def inspect(self, kind, decision, note):
    self.preserve()
    e = self.state['images' if kind == 'image' else 'videos'][-1]
    if decision not in ['Passed','Failed'] or not note or e.get('status') != 'Succeeded' or sha(DATA/e['assetPath']) != e['sha256']:
        raise RuntimeError('Inspect the actual unchanged output and document the result')
    e['inspection'] = dict(decision=decision, scope='PreviewInspection', note=note,
                           sha256=e['sha256'], humanApproved=False)
    self.state['stage'] = kind.capitalize()+'Inspected'+decision
    self.save()
    print('Preview inspection recorded; user review remains pending.')
 def inspect_range(self, note):
    self.preserve();self.require_reference()
    e=self.state['videos'][-1]
    report=json.loads((OUT/'video-checks.json').read_text(encoding='utf-8'))
    files=[OUT/('video-'+str(e['id']))/'first-48-frames'/('frame-%02d.png'%(i+1)) for i in range(36)]
    if (not note or e.get('status')!='Succeeded' or e.get('inspection',{}).get('decision')!='Failed'
            or report['status']!='Passed' or report['taskId']!=e['id']
            or sha(DATA/e['assetPath'])!=e['sha256'] or not all(x.exists() for x in files)):
        raise RuntimeError('The first 36 real decoded frames and failed full-video review are required')
    review=dict(decision='Passed',scope='PreviewInspectionOfRange',startFrame=0,endFrame=36,
                videoTaskId=e['id'],videoSha256=e['sha256'],note=note,humanApproved=False,
                frameHashes=[sha(x) for x in files],contentReview='NeedReview',publication='Blocked')
    write(OUT/'range-inspection.json',review)
    e['rangeInspection']=review
    self.state['insertionFrames']=36;self.state['finalFrames']=396
    self.state['stage']='VideoRangeInspected';self.save()
    print('Only the first 36 frames passed preview inspection; the complete video remains Failed.')
 def video(self, reason, adjustment):
    if self.state['completed']: raise RuntimeError('Completed run is read-only')
    self.preserve(); self.require_reference(); self.idle()
    image = self.state['images'][-1]
    report = json.loads((OUT/'image-checks.json').read_text(encoding='utf-8'))
    if (image.get('inspection',{}).get('decision') != 'Passed'
            or report['status'] != 'Passed' or report['taskId'] != image['id']
            or sha(DATA/image['assetPath']) != image['sha256']):
        raise RuntimeError('A visually inspected and provenance-verified candidate is required')
    e = self.next_entry(self.state['videos'], reason, adjustment)
    prompt = VIDEO_PROMPT + (' Targeted correction: ' + e['adjustment'] if e['adjustment'] else '')
    body = dict(projectId=54, taskType='ImageToVideo', workflowId=1105,
        inputImagePath=image['assetPath'], dependencyTaskId=image['id'], resourceClass='GPU',
        stage='MiniMax-Local-Fullbody-Experimental-Preview', maxRetries=0,
        parameters=dict(provider='MiniMaxLocal', profile='baseline480', textToVideo=False,
            prompt=prompt, seed=2026102812+e['attempt']*100, width=864, height=480,
            frames=124, fps=24, steps=20, duration=124/24, preserveAudio=True,
            extractNativeAudio=True, qualityReferenceImagePath=image['assetPath'], contentReview='NeedReview'))
    self.submit(e, body, 'video-'+str(e['attempt']))
    self.state['stage']='VideoQueued'; self.save()
 def edit(self, name):
    if self.state['completed']: raise RuntimeError('Completed run is read-only')
    self.preserve(); self.require_reference(); self.idle()
    video = self.state['videos'][-1]
    report = json.loads((OUT/'video-checks.json').read_text(encoding='utf-8'))
    valid_range=video.get('rangeInspection',{})
    if (video.get('inspection',{}).get('decision') != 'Failed'
            or valid_range.get('decision') != 'Passed' or valid_range.get('startFrame') != 0
            or valid_range.get('endFrame') != 36 or valid_range.get('videoSha256') != video['sha256']
            or report['status'] != 'Passed'
            or report['taskId'] != video['id'] or sha(DATA/video['assetPath']) != video['sha256']):
        raise RuntimeError('The actual selected 36-frame range must be separately inspected')
    tasks = self.state['editTasks']; e = tasks.setdefault(name,{})
    if e.get('id'):
        print('Existing '+name+' task retained '+str(e['id'])); return
    base, baseSha = self.state['basePath'], self.state['baseSha256']
    common = dict(projectId=54, taskType='Concat', resourceClass='CPU', maxRetries=0,
                  stage='Fullbody-Scene-Review-Edit')
    if name in ['head','insert','tail']:
        path = video['assetPath'] if name == 'insert' else base
        digest = video['sha256'] if name == 'insert' else baseSha
        duration = {'head':8.75,'insert':1.5,'tail':6.25}[name]
        offset = 8.75 if name == 'tail' else 0
        body = dict(common, dependencyTaskId=video['id'] if name == 'insert' else self.state['baseTaskId'],
            parameters=dict(files=[path], singlePass=True, targetWidth=864, targetHeight=480,
                targetFps=24, trimStartSeconds=offset, targetDurationSeconds=duration,
                originalAudioVolume=0, sourceChecks=[dict(path=path,sha256=digest)],
                outputName='fullbody_story_'+name+'.mp4'))
    elif name == 'picture':
        parts = [tasks.get(k,{}) for k in ['head','insert','tail']]
        if any(x.get('status') != 'Succeeded' or sha(DATA/x['assetPath']) != x['sha256'] for x in parts):
            raise RuntimeError('All actual source segments must succeed')
        body = dict(common,dependencyTaskId=parts[-1]['id'], parameters=dict(
            files=[x['assetPath'] for x in parts], singlePass=True, targetWidth=864,
            targetHeight=480, targetFps=24, targetDurationSeconds=16.5, originalAudioVolume=0,
            sourceChecks=[dict(path=x['assetPath'],sha256=x['sha256']) for x in parts],
            outputName='fullbody_story_picture_16_5s.mp4'))
    elif name == 'final':
        pic=tasks.get('picture',{})
        if pic.get('status')!='Succeeded' or sha(DATA/pic['assetPath'])!=pic['sha256']:
            raise RuntimeError('Assembled picture required before mixing')
        tracks=json.loads(json.dumps(self.state['musicAndNarration']))
        tracks[2]['startSeconds'] = 12.3
        tracks[3]['tempo'] = 0.94
        tracks[3]['fadeOutStartSeconds'] = 15.3
        tracks[3]['fadeOutDurationSeconds'] = 1.2
        checks=[dict(path=pic['assetPath'],sha256=pic['sha256'])]
        checks += [dict(path=t['path'],sha256=sha(DATA/t['path'])) for t in tracks]
        body=dict(common,dependencyTaskId=pic['id'],parameters=dict(files=[pic['assetPath']],
            targetWidth=864,targetHeight=480,targetFps=24,targetDurationSeconds=16.5,
            originalAudioVolume=0,audioTracks=tracks,sourceChecks=checks,
            outputName='fullbody_story_16_5s_narrated.mp4'))
    else: raise RuntimeError('Unknown edit stage')
    self.submit(e,body,'edit-'+name)
    self.state['stage']='Edit-'+name+'-Queued'; self.save()
 def tick(self):
    entries=self.state['images']+self.state['videos']+list(self.state['editTasks'].values())
    for e in entries:
        if not e.get('id'): continue
        detail=self.api('/api/tasks/'+str(e['id']))
        e['status']=detail['task']['status']
        if e['status']=='Succeeded':
            ext='.png' if e in self.state['images'] else '.mp4'
            asset=next(x for x in detail['results'] if x.get('available') and x.get('assetPath','').lower().endswith(ext))
            e.update(assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
        elif e['status'] in ['Failed','Cancelled']:
            e['failure']=detail['task'].get('errorMessage')
    self.save()
    print(json.dumps([dict(id=e.get('id'),status=e.get('status'),sha256=e.get('sha256')) for e in entries],ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','image','inspect-image','video','inspect-video','inspect-range','edit','tick'])
    parser.add_argument('--decision',choices=['Passed','Failed'])
    parser.add_argument('--note')
    parser.add_argument('--prompt')
    parser.add_argument('--source',choices=['story','precut'],default='story')
    parser.add_argument('--part',choices=['head','insert','tail','picture','final'])
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        p=Run()
        if args.command=='image':
            p.image(args.note,args.prompt,args.source)
        elif args.command=='video':
            p.video(args.note,args.prompt)
        elif args.command in ['inspect-image','inspect-video']:
            p.inspect(args.command.split('-')[1],args.decision,args.note)
        elif args.command=='inspect-range':
            p.inspect_range(args.note)
        elif args.command=='edit':
            if not args.part: parser.error('--part is required')
            p.edit(args.part)
        else:
            getattr(p,args.command)()

if __name__=='__main__': main()

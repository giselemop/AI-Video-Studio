"""Fresh two-shot H3 video plus the existing Qwen audio, using the real studio queue."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact

DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'Qwen3Video20261022'
REPORT = FOLDER / 'run.json'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'
FFPROBE = r'C:\install\FFmpeg\bin\ffprobe.exe'
SOURCE = DATA / 'Qwen3Tts20261022/run.json'
TEMPO = 1.32


def sha(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(DATA.resolve()) or not resolved.is_file():
        raise RuntimeError('Source must be a regular file inside central Data')
    return hashlib.sha256(resolved.read_bytes()).hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], encoding='utf-8'))


def once(run, field, stage, endpoint, body, timeout):
    if not run.state.get(field):
        if run.state.get(field + 'SubmissionStarted'):
            raise RuntimeError('Submission outcome unresolved; query existing tasks before retrying: ' + field)
        preflight = run.api('/api/tasks/preflight', body) if endpoint == '/api/tasks' else None
        if preflight is not None:
            (FOLDER / (field + '-preflight.json')).write_text(json.dumps(preflight, indent=2), encoding='utf-8')
            if not preflight['passed']:
                raise RuntimeError('Actual submission preflight rejected ' + field)
        run.save(stage, **{field + 'SubmissionStarted': True})
        result = run.api(endpoint, body, key=field, timeout=600)
        run.save(**{field: result.get('id') or result.get('taskId')})
        if not run.state[field]: raise RuntimeError('Submission has no task ID')
        print(field + '=' + str(run.state[field]), flush=True)
    return run.poll(run.state[field], limit=timeout)


def completed(run):
    if run.state.get('stage') != 'ReadyForUserPreview': return False
    run.access()
    if run.api(f"/api/tasks/{run.state['assemblyTaskId']}")['task']['status'] != 'Succeeded':
        raise RuntimeError('Recorded completed assembly is not successful')
    if sha(DATA / run.state['finalVideoPath']) != run.state['finalVideoSha256']:
        raise RuntimeError('Recorded preview changed; preserved')
    print(json.dumps({'stage': 'ReadyForUserPreview', 'assemblyTaskId': run.state['assemblyTaskId'], 'newTaskSubmitted': False}), flush=True)
    return True


def prepare(run, profile):
    run.access()
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    audio = source['audio']['assetPath']
    expected = '0fbc4f5a5d2640af58080ce8984d8bfcc940aecc308f5795f730ef422d565d7e'
    if source['taskId'] != 1196 or sha(DATA / audio) != expected:
        raise RuntimeError('The requested Qwen audio source changed')
    if run.state.get('profile') and run.state['profile'] != profile:
        raise RuntimeError('Generation profile is frozen; do not switch implicitly')
    if not run.state.get('projectId'):
        name = 'Qwen3配音新视频10秒_' + run.state['runId'][:8]
        matches = [p for p in run.api('/api/projects') if p['name'] == name]
        if matches: project = matches[0]['id']
        elif run.state.get('projectSubmissionStarted'): raise RuntimeError('Project response unresolved')
        else:
            run.save('CreatingProject', projectSubmissionStarted=True)
            project = run.api('/api/projects', {'name': name, 'description': 'Two freshly generated campus shots with the existing Qwen3 Vivian narration. Private review only.',
                'defaultWidth': 1920 if profile == 'native1080' else 1376, 'defaultHeight': 1080 if profile == 'native1080' else 768, 'defaultFps': 24})['id']
        run.save(projectId=project)
    run.save(profile=profile, sourceAudioTaskId=1196, sourceAudioPath=audio, sourceAudioSha256=expected,
        narrationText=source['text'], audioTempo=TEMPO, audioStartSeconds=.12, originalAudioVolume=0,
        targetSeconds=10, targetFrames=240, fps=24,
        targetWidth=1920 if profile == 'native1080' else 1376, targetHeight=1080 if profile == 'native1080' else 768,
        generationCanvas=[1920, 1088] if profile == 'native1080' else [1376, 768],
        routeReason='Retain the previously selected native1080 route unless the user explicitly chooses quality768; both videos are newly generated.',
        error=None)


def video(run, number):
    frame, fingerprint = '', None
    if number == 2:
        review = json.loads((FOLDER / 'shot-01/review.json').read_text(encoding='utf-8'))
        if review.get('status') != 'SelectedForContinuation': raise RuntimeError('Inspect the fresh first shot before continuing')
        frame, fingerprint = review['lastFramePath'], review['lastFrameSha256']
        if frame != 'Qwen3Video20261022/shot-01/frame-123.png' or review.get('sourceVideoSha256') != run.state['shot1VideoSha256']:
            raise RuntimeError('Continuation must bind the actual ending of this fresh first shot')
        if sha(DATA / frame) != fingerprint: raise RuntimeError('New shot ending reference changed')
    scene = ('A cinematic live-action medium wide eye-level view of a quiet university courtyard in warm afternoon sunlight. '
        'There is one wooden bench under a leafy tree beside a red brick library. One fictional adult East Asian woman, age 22, '
        'black ponytail, plain navy blue hoodie, black trousers and cream canvas backpack. '
        'One closed red hardcover notebook lies visibly on the right end of the bench. No other people are close to her. ')
    if number == 1:
        action = ('The woman walks slowly toward the bench, notices the red notebook and stops beside it. '
            'She looks down at the notebook. Gentle leaves and dappled shadows move in the breeze. '
            'The camera slowly pushes forward, one uninterrupted shot. Keep the notebook resting on the bench throughout this shot. ')
        prefix = ''
    else:
        scene = ('The same adult East Asian woman with black ponytail, navy hoodie and cream backpack remains beside the same '
            'wooden bench in the same sunny university courtyard. Preserve the reference identity, clothing and spatial arrangement. ')
        action = ('She gently picks up the single closed red notebook from the bench with her right hand, straightens and holds it '
            'against her torso. The notebook leaves the bench and stays in her hand. She looks up along the path and lifts her free '
            'left hand in a small friendly gesture to catch a distant classmate attention. Stable medium-wide framing, one continuous shot. ')
        prefix = 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
    prompt = (prefix + 'integrated_multimodal_description: [Shot 1] ' + scene + action +
        'Natural human anatomy, coherent realistic surroundings and warm restrained colors. No on-screen text. '
        'The narration is off screen; no speaking or lip synchronization is required.\n\noverall_soundscape: '
        'Quiet campus wind and faint birds only. No speech, no music.\n\nnon_diegetic_music: None.')
    frozen = {f'shot{number}Prompt': prompt, f'shot{number}Seed': 2026102200 + number,
        f'shot{number}InputFrame': frame, f'shot{number}InputSha256': fingerprint}
    if run.state.get(f'shot{number}TaskId') and any(run.state.get(k) != v for k, v in frozen.items()):
        raise RuntimeError('Submitted shot inputs changed')
    run.save(**frozen)
    if not run.state.get(f'shot{number}TaskId'):
        queue = run.api('/api/minimax/local/status')['queue']
        if queue.get('activeTasks') or queue.get('paused'): raise RuntimeError('Queue is active or paused')
        run.api('/api/minimax/local/verify', {}, timeout=600)
    detail = once(run, f'shot{number}TaskId', f'GeneratingShot{number}', '/api/minimax/local/video', {
        'projectId': run.state['projectId'], 'profile': run.state['profile'], 'textToVideo': number == 1,
        'inputImagePath': frame, 'prompt': prompt, 'seed': run.state[f'shot{number}Seed']}, 22500)
    path = artifact(detail, ('.mp4',))
    metadata = probe(DATA / path)
    stream = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    if (stream['width'], stream['height'], stream['avg_frame_rate'], int(stream['nb_frames'])) != (run.state['targetWidth'], run.state['targetHeight'], '24/1', 124):
        raise RuntimeError('Actual newly generated source does not match its frozen dimensions/frame count')
    graph = json.loads(metadata['format']['tags']['prompt'])
    condition = graph['6']['inputs']
    if [condition['width'], condition['height']] != run.state['generationCanvas'] or condition['length'] != 124 or condition['prompt'] != prompt:
        raise RuntimeError('Actual graph generation geometry or prompt differs')
    if graph['10']['inputs']['steps'] != 20 or graph['7']['inputs']['noise_seed'] != run.state[f'shot{number}Seed']:
        raise RuntimeError('Actual graph sampler differs')
    if number == 1 and any(n['class_type'] == 'LoadImage' for n in graph.values()): raise RuntimeError('Fresh text opening used a hidden reference')
    if number == 2 and graph['5'].get('is_changed') != [fingerprint]: raise RuntimeError('Continuation reference hash differs')
    folder = FOLDER / f'shot-{number:02}'; folder.mkdir(exist_ok=True)
    (folder / 'probe.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (folder / 'execution-graph.json').write_text(json.dumps(graph, indent=2), encoding='utf-8')
    run.save(f'AwaitingShot{number}Inspection', **{f'shot{number}VideoPath': path, f'shot{number}VideoSha256': sha(DATA / path),
        f'shot{number}TaskMetrics': detail['task']})
    contact = Image.new('RGB', (960, 540), '#111111')
    for i, index in enumerate([0, 40, 80, 123]):
        image_path = folder / f'frame-{index:03}.png'
        if not image_path.exists(): subprocess.run([FFMPEG, '-v', 'error', '-i', str(DATA / path), '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', '-n', str(image_path)], check=True)
        image = Image.open(image_path).convert('RGB'); image.thumbnail((480, 270))
        contact.paste(image, ((i % 2) * 480, (i // 2) * 270))
    ImageDraw.Draw(contact).text((8, 8), f'New shot {number}: frames 0 / 40 / 80 / 123', fill='white')
    contact.save(folder / 'contact.png')
    print(json.dumps({'stage': run.state['stage'], 'shot': number, 'taskId': run.state[f'shot{number}TaskId'], 'contact': str(folder / 'contact.png')}), flush=True)


def assemble(run):
    sources = []
    for number in [1, 2]:
        review = json.loads((FOLDER / f'shot-{number:02}/review.json').read_text(encoding='utf-8'))
        if review.get('status') != 'SelectedForContinuation': raise RuntimeError('Inspect both newly generated shots before assembly')
        path = run.state[f'shot{number}VideoPath']
        if sha(DATA / path) != run.state[f'shot{number}VideoSha256']: raise RuntimeError('A fresh source changed')
        sources.append({'taskId': run.state[f'shot{number}TaskId'], 'path': path, 'sha256': sha(DATA / path)})
    if sha(DATA / run.state['sourceAudioPath']) != run.state['sourceAudioSha256']: raise RuntimeError('Original Qwen audio changed')
    duration = float(probe(DATA / run.state['sourceAudioPath'])['format']['duration'])
    if duration / TEMPO + .12 > 9.95: raise RuntimeError('The complete narration cannot fit without cutting')
    body = {'projectId': run.state['projectId'], 'taskType': 'Concat', 'resourceClass': 'CPU', 'stage': 'Qwen3-NewVideo-10s-Preview', 'maxRetries': 0,
        'parameters': {'files': [s['path'] for s in sources], 'targetWidth': run.state['targetWidth'], 'targetHeight': run.state['targetHeight'],
            'targetFps': 24, 'targetDurationSeconds': 10, 'originalAudioVolume': 0,
            'audioTracks': [{'path': run.state['sourceAudioPath'], 'volume': 1, 'startSeconds': .12, 'tempo': TEMPO}], 'outputName': 'qwen3_fresh_campus_10s.mp4'}}
    run.save(assemblySources=sources, assemblyInput=body)
    detail = once(run, 'assemblyTaskId', 'AssemblingPreview', '/api/tasks', body, 3600)
    path = artifact(detail, ('.mp4',)); metadata = probe(DATA / path)
    v = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    if (v['width'], v['height'], v['avg_frame_rate'], int(v['nb_frames'])) != (run.state['targetWidth'], run.state['targetHeight'], '24/1', 240): raise RuntimeError('Final 10-second video frame specification differs')
    if abs(float(v['duration']) - 10) > .02 or not any(s['codec_type'] == 'audio' for s in metadata['streams']): raise RuntimeError('Final duration/audio verification failed')
    subprocess.run([FFMPEG, '-v', 'error', '-i', str(DATA / path), '-f', 'null', '-'], check=True)
    (FOLDER / 'final-probe.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    run.save('AwaitingPlaybackInspection', technicalStatus='Passed', finalVideoPath=path, finalVideoSha256=sha(DATA / path),
        previewUrl='http://127.0.0.1:18080/qwen3-video-preview.html?' + urlencode({'video': path}), contentStatus='NeedReview', publicationStatus='Blocked')
    print(json.dumps({'stage': run.state['stage'], 'videoPath': path, 'previewUrl': run.state['previewUrl']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prepare', 'video', 'assemble', 'check'], required=True)
    parser.add_argument('--shot', type=int, choices=[1, 2], default=1)
    parser.add_argument('--profile', choices=['native1080', 'quality768'], default='native1080')
    args = parser.parse_args(); FOLDER.mkdir(parents=True, exist_ok=True)
    with download_lock(FOLDER, '.qwen3-video.lock', 'Another Qwen video runner is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            if completed(run): return
            prepare(run, args.profile)
            if args.stage == 'video': video(run, args.shot)
            elif args.stage == 'assemble': assemble(run)
            elif args.stage == 'prepare': run.save('Prepared')
            else: print(json.dumps({'stage': run.state['stage'], 'newTaskSubmitted': False}))
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1600]); print(str(error)[:1000], flush=True); raise


if __name__ == '__main__': main()

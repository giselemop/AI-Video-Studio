"""Resumable, queue-only execution for the local three-shot dialogue revision."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT.parent
DATA = AI / 'Data'
FOLDER = DATA / 'DialogueThreeShot20261023'
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from run_local_acceptance import Acceptance, TaskFailure
from download_assets import download_lock


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError('Controlled Data media path required')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Run(Acceptance):
    def poll(self, task_id, limit=7200):
        import psutil
        started = time.monotonic()
        printed = 0
        while time.monotonic() - started < limit:
            detail = self.api(f'/api/tasks/{task_id}')
            task = detail['task']
            sample = dict(epoch=time.time(), taskId=task_id, status=task['status'],
                          progress=task.get('progress'), availableRamMiB=psutil.virtual_memory().available // 1024**2)
            try:
                values = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], encoding='utf-8', timeout=10)
                sample['gpu'] = [int(x.strip()) for x in values.strip().split(',')]
            except (OSError, subprocess.SubprocessError):
                pass
            with (FOLDER / 'resources.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(sample) + '\n')
            if time.monotonic() - printed > 60:
                print(json.dumps(sample), flush=True)
                printed = time.monotonic()
            if task['status'] == 'Succeeded':
                return detail
            if task['status'] in ('Failed', 'Cancelled'):
                raise TaskFailure(task_id, task['status'], str(task.get('errorMessage'))[:2000])
            time.sleep(5)
        raise RuntimeError('Task remains unresolved; preserve ID and inspect before resuming')


def once(run, field, body):
    if run.state.get(field + 'Input') and run.state[field + 'Input'] != body:
        raise RuntimeError('Frozen task input changed: ' + field)
    if not run.state.get(field):
        if run.state.get(field + 'SubmissionStarted'):
            raise RuntimeError('Uncertain submission outcome: ' + field)
        result = run.api('/api/tasks/preflight', body, timeout=600)
        write(FOLDER / (field + '-preflight.json'), result)
        if not result['passed']:
            raise RuntimeError(str(result['issues']))
        run.save(**{field + 'Input': body, field + 'SubmissionStarted': True})
        result = run.api('/api/tasks', body, key=field, timeout=600)
        run.save(**{field: result.get('id') or result.get('taskId')})
        print(field, run.state[field], flush=True)
    result = run.poll(run.state[field])
    write(FOLDER / (field + '-result.json'), result)
    path = next(x['assetPath'] for x in result['results'] if x.get('available') and x.get('assetPath', '').endswith('.mp4'))
    return path


def prepare(run):
    run.access()
    if not run.state.get('projectId'):
        name = '午后对白_三镜头优化_' + run.state['runId'][:8]
        existing = [x for x in run.api('/api/projects') if x['name'] == name]
        if existing:
            project = existing[0]['id']
        elif run.state.get('projectSubmissionStarted'):
            raise RuntimeError('Project submission unresolved')
        else:
            run.save('Preparing', projectSubmissionStarted=True)
            project = run.api('/api/projects', dict(name=name, description='Pure-local revised acting, original characters and four texts, three shots, exact10s. Human content review required.', defaultWidth=1280, defaultHeight=720, defaultFps=24))['id']
        run.save(projectId=project)
    previous = 'Artifacts/project-33/video/task-1246/v0001/v0001_two_person_dialogue_local_9.5s_8931528782f6.mp4'
    old = DATA / 'DialoguePilot20261023/run.json'
    preserved = FOLDER / 'preserved-before.json'
    if not preserved.exists():
        write(preserved, [{'path': previous, 'sha256': sha(DATA / previous)}, {'path': str(old.relative_to(DATA)), 'sha256': sha(old)}])
    run.save(previousPath=previous, previousSha256=sha(DATA / previous))
    print('projectId', run.state['projectId'], flush=True)


def sync_audio(run):
    audio = json.loads((FOLDER / 'audio/run.json').read_text(encoding='utf-8'))
    shots = json.loads((FOLDER / 'audio/shot-definitions.json').read_text(encoding='utf-8'))
    timeline = json.loads((FOLDER / 'audio/timeline.json').read_text(encoding='utf-8'))
    if run.state.get('shot1Attempt1TaskId') and run.state.get('timeline') != timeline:
        raise RuntimeError('Dialogue timing is frozen after the first video submission')
    paths = [FOLDER / 'audio/timeline.json', FOLDER / 'audio/shot-definitions.json',
             FOLDER / 'audio/dialogue-room-10s.wav', FOLDER / 'audio/dialogue.srt']
    paths += [FOLDER / f'reference-{i}.png' for i in (1, 2, 3)]
    paths += [FOLDER / f'audio/shot-{i}-{role}-native.wav' for i in (1, 2, 3) for role in ('female', 'male')]
    frozen = {str(p.relative_to(DATA)): sha(p) for p in paths}
    snapshot = FOLDER / 'frozen-inputs.json'
    if snapshot.exists() and json.loads(snapshot.read_text(encoding='utf-8')) != frozen:
        raise RuntimeError('Frozen reference/audio/timeline changed; preserve this run and version the revision')
    if not snapshot.exists(): write(snapshot, frozen)
    if run.state.get('assemblyPath'):
        return audio, run.state['shots']
    run.save(timeline=timeline, shots=shots)
    return audio, shots


def video(run, index, attempt):
    if attempt not in (1, 2, 3):
        raise RuntimeError('Initial generation plus at most two targeted repairs')
    _, shots = sync_audio(run)
    if run.state.get(f'shot{index}Path') and attempt <= run.state.get(f'shot{index}SelectedAttempt', 0):
        if sha(DATA / run.state[f'shot{index}Path']) != run.state[f'shot{index}Sha256']:
            raise RuntimeError('Selected shot changed')
        print('Existing selected shot preserved; no task submitted', flush=True)
        return
    shot = shots[index - 1]
    run.api('/api/workflows/scan', {}, timeout=180)
    name = f'dialogue_three_shot_{index}_v1_api'
    workflow = next(x for x in run.api('/api/workflows') if x['name'] == name)
    plan = json.loads((FOLDER / 'workflow-plan.json').read_text(encoding='utf-8'))[index - 1]
    if attempt > 1 and not (FOLDER / f'shot-{index}-repair-{attempt}.json').exists():
        raise RuntimeError('Targeted repair reason/parameter record required')
    slots = dict(firstFrame=f'DialogueThreeShot20261023/reference-{index}.png')
    repair = json.loads((FOLDER / f'shot-{index}-repair-{attempt}.json').read_text(encoding='utf-8')) if attempt > 1 else {}
    if repair.get('referencePath'):
        if sha(DATA / repair['referencePath']) != repair.get('referenceSha256'):
            raise RuntimeError('Targeted reference changed')
        slots['firstFrame'] = repair['referencePath']
    if index < 3:
        role = 'female' if index == 1 else 'male'
        slots['speakerAudio'] = f'DialogueThreeShot20261023/audio/shot-{index}-{role}-native.wav'
    else:
        slots.update(femaleAudio=f'DialogueThreeShot20261023/audio/shot-3-female-native.wav', maleAudio=f'DialogueThreeShot20261023/audio/shot-3-male-native.wav')
    frames = plan['nativeFrames']
    seed = 2026102310 + index + (attempt - 1) * 100
    graph = json.loads((AI / 'Workflows' / (name + '.json')).read_text(encoding='utf-8'))
    prompt = graph['5']['inputs']['positive']
    negative = graph['5']['inputs']['negative']
    body = dict(projectId=run.state['projectId'], taskType='ImageToVideo', resourceClass='GPU', workflowId=workflow['id'], inputImagePath=slots['firstFrame'], stage=f'Dialogue-Three-Shot-{index}-Attempt-{attempt}', maxRetries=0,
                parameters=dict(workflowVersion=f'dialogue-three-shot-{index}-v1', positive=prompt, negative=negative, width=832, height=480, fps=25, frames=frames, duration=frames / 25, steps=6, cfg=1, seed=seed, inputSlots=slots))
    field = f'shot{index}Attempt{attempt}TaskId'
    path = once(run, field, body)
    run.save('AwaitingShotInspection', **{f'shot{index}Path': path, f'shot{index}Sha256': sha(DATA / path), f'shot{index}SelectedAttempt': attempt})
    print(str(DATA / path), flush=True)


def assemble(run):
    _, shots = sync_audio(run)
    files = []
    for index, shot in enumerate(shots, 1):
        path = run.state[f'shot{index}Path']
        if sha(DATA / path) != run.state[f'shot{index}Sha256']:
            raise RuntimeError('Selected shot changed')
        review = json.loads((FOLDER / f'shot-{index}-review.json').read_text(encoding='utf-8'))
        if review.get('decision') != 'SelectedForAssembly' or review.get('sourceSha256') != run.state[f'shot{index}Sha256']:
            raise RuntimeError('Actual shot inspection required')
        duration = shot['endSeconds'] - shot['startSeconds']
        body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU', stage=f'Three-Shot-{index}-Canvas', maxRetries=0,
                    parameters=dict(files=[path], targetWidth=1280, targetHeight=720, targetFps=24, targetDurationSeconds=duration, originalAudioVolume=0, outputName=f'three_shot_{index}_canvas.mp4'))
        canvas = once(run, f'canvas{index}TaskId', body)
        files.append(canvas)
        shot.update(index=index, label=['女方近景', '男方反打', '双人收尾'][index - 1], path=canvas, sha256=sha(DATA / canvas), nativePath=path, nativeSha256=run.state[f'shot{index}Sha256'])
    body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU', stage='Three-Shot-Exact10s-Assembly', maxRetries=0,
                parameters=dict(files=files, targetWidth=1280, targetHeight=720, targetFps=24, targetDurationSeconds=10, originalAudioVolume=0, outputName='dialogue_three_shot_clean_10s.mp4'))
    path = once(run, 'assemblyTaskId', body)
    run.save('AwaitingAssemblyInspection', shots=shots, assemblyPath=path, assemblySha256=sha(DATA / path))


def restore(run):
    review = json.loads((FOLDER / 'assembly-review.json').read_text(encoding='utf-8'))
    if review.get('decision') != 'SelectedForFinishing' or review.get('sourceSha256') != run.state['assemblySha256']:
        raise RuntimeError('Inspect actual three-shot assembly before restoration')
    status = run.api('/api/video-restore/status')
    if not status['ready']:
        raise RuntimeError(status['message'])
    cuts = [round(s['startSeconds'] * 24) for s in run.state['shots'][1:]]
    body = dict(projectId=run.state['projectId'], taskType='VideoRestore', resourceClass='GPU', stage='Three-Shot-Conservative-Restoration', maxRetries=0,
                parameters=dict(input=run.state['assemblyPath'], sourceSha256=run.state['assemblySha256'], engineVersion=status['engineVersion'], strength=.25, cutFrames=cuts))
    path = once(run, 'restoreTaskId', body)
    run.save('AwaitingRestorationInspection', restorePath=path, restoreSha256=sha(DATA / path))


def finish(run):
    selected = json.loads((FOLDER / 'finishing-review.json').read_text(encoding='utf-8'))
    path = selected['selectedPath']
    allowed = {run.state.get(k + 'Path'): run.state.get(k + 'Sha256') for k in ('assembly', 'restore') if run.state.get(k + 'Path')}
    if selected.get('decision') != 'SelectedForFinalMix' or path not in allowed or selected.get('selectedSha256') != allowed[path]:
        raise RuntimeError('Select a reviewed candidate generated by this run')
    if sha(DATA / path) != selected['selectedSha256']:
        raise RuntimeError('Selected finishing video changed')
    mix = 'DialogueThreeShot20261023/audio/dialogue-room-10s.wav'
    body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU', stage='Three-Shot-Final-Dialogue-Mix', maxRetries=0,
                parameters=dict(files=[path], targetWidth=1280, targetHeight=720, targetFps=24, targetDurationSeconds=10, originalAudioVolume=0, audioTracks=[dict(path=mix, volume=1, startSeconds=0, tempo=1)], subtitlePath='DialogueThreeShot20261023/audio/dialogue.srt', outputName='dialogue_three_shot_local_10s.mp4'))
    final = once(run, 'finalTaskId', body)
    run.save('AwaitingDeliveryVerification', finalPath=final, finalSha256=sha(DATA / final), mixPath=mix, mixSha256=sha(DATA / mix))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['prepare', 'video', 'assemble', 'restore', 'finish', 'check'], required=True)
    parser.add_argument('--shot', type=int, choices=[1, 2, 3])
    parser.add_argument('--attempt', type=int, default=1)
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    run = Run('http://127.0.0.1:18080', FOLDER / 'run.json')
    if args.stage == 'check' or run.state.get('stage') == 'ReadyForUserPreview':
        for key in ['final', 'assembly', 'restore', 'shot1', 'shot2', 'shot3']:
            if run.state.get(key + 'Path') and sha(DATA / run.state[key + 'Path']) != run.state[key + 'Sha256']:
                raise RuntimeError('Recorded media changed: ' + key)
        print('Read-only existing-state verification; no task submitted', flush=True)
        return
    with download_lock(FOLDER, filename='.three-shot.lock', conflict='Another three-shot runner is active; inspect recorded IDs'):
        run = Run('http://127.0.0.1:18080', FOLDER / 'run.json')
        prepare(run)
        if args.stage == 'video':
            if not args.shot:
                parser.error('--shot required')
            video(run, args.shot, args.attempt)
        if args.stage == 'assemble': assemble(run)
        if args.stage == 'restore': restore(run)
        if args.stage == 'finish': finish(run)


if __name__ == '__main__':
    main()

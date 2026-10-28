"""Queue-only, resumable SeedVR2 QHD finishing of the approved three-shot film."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'Dialogue2KSeedVR220261024'
OLD = DATA / 'DialogueThreeShot20261023'
API = 'http://127.0.0.1:18081'
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from run_local_acceptance import Acceptance, TaskFailure
from download_assets import download_lock


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def media(value):
    path = (DATA / value).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError('Expected controlled Data media')
    return path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Run(Acceptance):
    def poll(self, task_id, limit=6000):
        import psutil
        started, printed = time.monotonic(), 0
        while time.monotonic() - started < limit:
            detail = self.api(f'/api/tasks/{task_id}')
            task = detail['task']
            sample = dict(epoch=time.time(), taskId=task_id, status=task['status'],
                          progress=task.get('progress'), availableRamMiB=psutil.virtual_memory().available // 1024**2)
            try:
                raw = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu',
                                               '--format=csv,noheader,nounits'], encoding='utf-8', timeout=10)
                sample['gpu'] = [int(x.strip()) for x in raw.strip().split(',')]
            except (OSError, subprocess.SubprocessError):
                pass
            with (FOLDER / 'resources.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(sample) + '\n')
            if time.monotonic() - printed >= 45:
                print(json.dumps(sample), flush=True)
                printed = time.monotonic()
            if task['status'] == 'Succeeded':
                return detail
            if task['status'] in ('Failed', 'Cancelled'):
                raise TaskFailure(task_id, task['status'], str(task.get('errorMessage'))[:1600])
            time.sleep(5)
        raise RuntimeError('Existing task remains unresolved; preserve its ID, do not resubmit')


def preserved(run):
    for item in run.state.get('preserved', []):
        if sha(media(item['path'])) != item['sha256']:
            raise RuntimeError('Preserved source changed: ' + item['path'])
    if run.state.get('subtitleSha256') and sha(media(run.state['subtitlePath'])) != run.state['subtitleSha256']:
        raise RuntimeError('The bound original dialogue subtitles changed')


def once(run, field, body):
    preserved(run)
    if run.state.get(field + 'Input') and run.state[field + 'Input'] != body:
        raise RuntimeError('Frozen task parameters changed: ' + field)
    if not run.state.get(field):
        if run.state.get(field + 'SubmissionStarted'):
            raise RuntimeError('Submission outcome unresolved; no duplicate request: ' + field)
        preflight = run.api('/api/tasks/preflight', body, timeout=600)
        write(FOLDER / (field + '-preflight.json'), preflight)
        if not preflight['passed']:
            raise RuntimeError(str(preflight['issues']))
        run.save(**{field + 'Input': body, field + 'SubmissionStarted': True})
        response = run.api('/api/tasks', body, key=field, timeout=600)
        run.save(**{field: response.get('id') or response.get('taskId')})
        print(field, run.state[field], flush=True)
    detail = run.poll(run.state[field])
    write(FOLDER / (field + '-result.json'), detail)
    path = next(x['assetPath'] for x in detail['results'] if x.get('available') and x.get('assetPath', '').endswith('.mp4'))
    return path


def prepare(run):
    run.access()
    old = read(OLD / 'run.json')
    if old['stage'] != 'ReadyForUserPreview':
        raise RuntimeError('Original source must be the completed three-shot film')
    records = [{'path': old['finalPath'], 'sha256': old['finalSha256']},
               {'path': str((OLD / 'run.json').relative_to(DATA)), 'sha256': sha(OLD / 'run.json')},
               {'path': old['mixPath'], 'sha256': old['mixSha256']}]
    for shot in old['shots']:
        records.append({'path': shot['path'], 'sha256': shot['sha256']})
    frozen = dict(preserved=records, originalPath=old['finalPath'], originalSha256=old['finalSha256'],
                  timeline=old['timeline'], shots=old['shots'], outputWidth=2560, outputHeight=1440,
                  outputFps=24, outputFrames=240, outputSeconds=10, outputProfile='qhd1440',
                  subtitlePath='DialogueThreeShot20261023/audio/dialogue.srt',
                  route='Existing SeedVR2 3B FP8, independent per-shot reconstruction and super-resolution; no new acting or audio')
    if run.state.get('projectId') and any(run.state.get(k) != v for k, v in frozen.items()):
        raise RuntimeError('Approved source/timeline changed')
    run.save('PreparingQhd', **frozen)
    preserved(run)
    if not run.state.get('projectId'):
        name = '午后对白_SeedVR2逐镜头2K_' + run.state['runId'][:8]
        matches = [p for p in run.api('/api/projects') if p['name'] == name]
        if len(matches) == 1:
            project_id = matches[0]['id']
        elif run.state.get('projectSubmissionStarted'):
            raise RuntimeError('Project creation unresolved')
        else:
            run.save(projectSubmissionStarted=True)
            project_id = run.api('/api/projects', dict(name=name,
                description='Same approved three-shot acting, lines and timing. Local SeedVR2 QHD finishing comparison, not native 2K generation.',
                defaultWidth=2560, defaultHeight=1440, defaultFps=24))['id']
        run.save(projectId=project_id)
    run.save('ReadyForFirstShot')
    print('projectId', run.state['projectId'], flush=True)


def shot(run, index, attempt, strength):
    if not 1 <= index <= 3 or not 1 <= attempt <= 3:
        raise RuntimeError('Only one initial attempt and two targeted repairs per shot are allowed')
    if index > 1:
        review = read(FOLDER / 'shot-1-review.json')
        if review['decision'] != 'SelectedForAssembly':
            raise RuntimeError('Inspect the first actual QHD shot before continuing')
    if attempt > 1:
        review = read(FOLDER / f'shot-{index}-attempt-{attempt-1}-review.json')
        if review.get('decision') != 'RepairRequired' or not review.get('reason'):
            raise RuntimeError('Targeted repair requires an actual prior failure review')
    selected = run.state.get(f'shot{index}SelectedAttempt')
    if selected is not None and selected != attempt:
        raise RuntimeError('Existing selected shot is preserved')
    source = run.state['shots'][index - 1]
    status = run.api('/api/video-restore/status')
    if not status['ready']:
        raise RuntimeError('Existing local SeedVR2 environment is not ready')
    body = dict(projectId=run.state['projectId'], taskType='VideoRestore', resourceClass='GPU',
                stage=f'Dialogue-QHD-Shot-{index}-Attempt-{attempt}', maxRetries=0,
                parameters=dict(input=source['path'], sourceSha256=source['sha256'], engineVersion=status['engineVersion'],
                                strength=strength, cutFrames=[], outputProfile='qhd1440', targetWidth=2560, targetHeight=1440))
    field = f'shot{index}Attempt{attempt}TaskId'
    run.save(f'RestoringShot{index}')
    path = once(run, field, body)
    run.save(f'AwaitingShot{index}Inspection', **{f'shot{index}Attempt{attempt}Path': path,
             f'shot{index}Attempt{attempt}Sha256': sha(media(path))})
    print(path, flush=True)


def assemble(run):
    subtitle = media(run.state['subtitlePath'])
    text = subtitle.read_text(encoding='utf-8-sig')
    if any(text.count(line['text']) != 1 for line in run.state['timeline']):
        raise RuntimeError('The subtitle file must contain each of the original four lines exactly once')
    if not run.state.get('subtitleSha256'):
        run.save(subtitleSha256=sha(subtitle))
    preserved(run)
    files = []
    for index in range(1, 4):
        review = read(FOLDER / f'shot-{index}-review.json')
        attempt = review['attempt']
        path = run.state[f'shot{index}Attempt{attempt}Path']
        if review['decision'] != 'SelectedForAssembly' or review['sha256'] != sha(media(path)):
            raise RuntimeError('Actual per-shot review is required')
        run.save(**{f'shot{index}SelectedAttempt': attempt})
        files.append(path)
    body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU',
                stage='Dialogue-QHD-Three-Shot-Captioned-Assembly', maxRetries=0,
                parameters=dict(files=files, targetWidth=2560, targetHeight=1440, targetFps=24,
                    targetDurationSeconds=10, originalAudioVolume=0, subtitlePath=run.state['subtitlePath'],
                    outputName='dialogue_three_shot_2k_picture.mp4'))
    picture = once(run, 'pictureTaskId', body)
    run.save('PreservingOriginalAudio', picturePath=picture, pictureSha256=sha(media(picture)))
    body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU',
                stage='Dialogue-QHD-Original-Audio-Packets', maxRetries=0,
                parameters=dict(files=[picture], videoSha256=sha(media(picture)),
                    audioStreamCopyFrom=run.state['originalPath'], audioStreamCopySha256=run.state['originalSha256'],
                    allowResolutionDifference=True,
                    outputName='dialogue_three_shot_seedvr2_2k_10s.mp4'))
    final = once(run, 'finalTaskId', body)
    run.save('AwaitingFinalVerification', finalPath=final, finalSha256=sha(media(final)))
    print(final, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=['prepare', 'shot', 'assemble', 'check'])
    parser.add_argument('--index', type=int, default=1)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--strength', type=float, default=.35)
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / 'runner').mkdir(exist_ok=True)
    with download_lock(FOLDER / 'runner'):
        run = Run(API, FOLDER / 'run.json')
        if args.stage == 'check' or run.state.get('stage') == 'ReadyForUserPreview':
            preserved(run)
            if run.state.get('finalPath') and sha(media(run.state['finalPath'])) != run.state['finalSha256']:
                raise RuntimeError('Final artifact changed')
            print('Existing files verified; newTaskSubmitted=false', flush=True)
            return
        run.access()
        if args.stage == 'prepare': prepare(run)
        elif args.stage == 'shot': shot(run, args.index, args.attempt, args.strength)
        else: assemble(run)


if __name__ == '__main__':
    main()

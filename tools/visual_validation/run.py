"""Resumable local visual validation. GPU work is submitted only through the studio queue."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageOps
import psutil

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'VisualValidation20261024'
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from run_local_acceptance import Acceptance, TaskFailure

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def media(relative):
    p = (DATA / relative).resolve(strict=True)
    if not p.is_relative_to(DATA.resolve()) or not p.is_file(): raise ValueError('Controlled Data file required')
    return p
def rel(path): return str(Path(path).resolve().relative_to(DATA.resolve())).replace('\\', '/')

class Run(Acceptance):
    def preserve(self):
        for item in self.state.get('preserved', []):
            if sha(media(item['path'])) != item['sha256']: raise RuntimeError('Frozen source changed: ' + item['path'])
        for i in range(1,7):
            if self.state.get(f'keyframe{i}Path') and sha(media(self.state[f'keyframe{i}Path'])) != self.state[f'keyframe{i}Sha256']:
                raise RuntimeError('New keyframe asset drifted')
        if self.state.get('selectionSha256') and sha(FOLDER/'keyframe-selection.json') != self.state['selectionSha256']:
            raise RuntimeError('Selected pilot references changed')
        for field in ['h3Baseline','h3Controlled','acting','qhd','actingOriginalCompare','actingNewCompare']:
            if self.state.get(field+'Path') and self.state.get(field+'Sha256') and sha(media(self.state[field+'Path']))!=self.state[field+'Sha256']:
                raise RuntimeError('Frozen new video changed: '+field)
        for item in self.state.get('actingCandidates',[]):
            if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Retained acting candidate changed')
    def poll(self, task_id, limit=14400):
        start = time.monotonic(); last = 0; read_errors=0
        while time.monotonic() - start < limit:
            try:
                detail = self.api(f'/api/tasks/{task_id}'); task = detail['task'];read_errors=0
            except RuntimeError as error:
                read_errors+=1
                with (FOLDER/'status-read-errors.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(dict(taskId=task_id,time=time.time(),error=str(error)[:300],submissionRetried=False))+'\n')
                if read_errors>=3:raise
                print(f'Read-only status retry {read_errors} for existing task {task_id}; no submission retry',flush=True)
                time.sleep(5);continue
            try:
                raw = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu',
                    '--format=csv,noheader,nounits'], text=True, timeout=10)
                gpu = [int(x.strip()) for x in raw.strip().split(',')]
            except Exception: gpu = None
            sample = dict(epoch=time.time(), taskId=task_id, status=task['status'], progress=task.get('progress'),
                gpu=gpu, availableRamMiB=psutil.virtual_memory().available // 1024**2,
                freeDiskGiB=round(shutil.disk_usage(DATA).free / 1024**3, 2))
            with (FOLDER / 'resources.jsonl').open('a', encoding='utf-8') as stream: stream.write(json.dumps(sample) + '\n')
            if time.monotonic() - last >= 45: print(json.dumps(sample), flush=True); last = time.monotonic()
            if task['status'] in ['Succeeded', 'Failed', 'Cancelled']:
                write(FOLDER / f'task-{task_id}.json', detail)
                if task['status'] != 'Succeeded': raise TaskFailure(task_id, task['status'], str(task.get('errorMessage'))[:1600])
                return detail
            time.sleep(5)
        raise RuntimeError(f'Task {task_id} unresolved; never submit a duplicate')
    def once(self, field, body, endpoint='/api/tasks'):
        self.preserve()
        if self.state.get('stage') == 'ReadyForUserPreview' and not self.state.get(field):
            raise RuntimeError('Completed validation package is read-only; a new revision requires a separate run')
        if self.state.get(field + 'Input') not in [None, body]: raise RuntimeError('Frozen submission changed; use a new version')
        if not self.state.get(field):
            if self.state.get(field + 'Started'): raise RuntimeError('Submission outcome unresolved; inspect the recorded project before retrying')
            if endpoint == '/api/tasks':
                pre = self.api('/api/tasks/preflight', body, timeout=600)
                write(FOLDER / (field + '-preflight.json'), pre)
                if not pre['passed']: raise RuntimeError(str(pre['issues']))
            self.save(**{field + 'Input': body, field + 'Started': True})
            response = self.api(endpoint, body, key=field, timeout=600)
            self.save(**{field: response.get('id') or response.get('taskId')})
            print(field, self.state[field], flush=True)
        return self.poll(self.state[field])

def result(detail, suffix):
    return next(x['assetPath'] for x in detail['results'] if x.get('available') and x.get('assetPath', '').endswith(suffix))

def prepare(run):
    if run.state.get('prepared'): run.preserve(); print('Existing inputs and run preserved'); return
    old = read(DATA / 'FaceActing20261024/run.json')
    previous = read(DATA / 'DialogueThreeShot20261023/run.json')
    records = []
    source = DATA / 'FaceActing20261024/selected-master.png'
    paths = [old['finalPath'], previous['finalPath'], 'FaceActing20261024/run.json',
        'DialogueThreeShot20261023/run.json', rel(source), 'FaceActing20261024/reference-selection.json']
    shot = read(DATA / 'FaceActing20261024/task-1293.json')
    driver = result(shot, '.mp4'); paths.append(driver)
    for path in dict.fromkeys(paths): records.append(dict(path=path, sha256=sha(media(path))))
    # A documented crop of an existing still is reference preparation, never a new generated result.
    folder = FOLDER / 'inputs'; folder.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert('RGB')
    crop = (220, 0, 620, 400)
    reference = folder / 'female-reference.png'
    image.crop(crop).resize((768, 768), Image.Resampling.LANCZOS).save(reference)
    records.append(dict(path=rel(reference), sha256=sha(reference)))
    write(FOLDER / 'reference-preparation.json', dict(source=rel(source), sourceSha256=sha(source),
        crop=crop, output=rel(reference), size=[768, 768], operation='deterministic crop and resize; existing input, not new generation'))
    inventory = []
    for path in (ROOT.parent / 'Models').rglob('*'):
        if not path.is_file() or 'Flux2Klein4B' in path.parts: continue
        info = path.stat(); inventory.append(dict(path=str(path.relative_to(ROOT.parent / 'Models')).replace('\\', '/'), size=info.st_size, mtimeNs=info.st_mtime_ns))
    write(FOLDER / 'existing-model-inventory.json', dict(kind='size-and-mtime baseline, not a fresh content hash', files=inventory))
    backup_names = ['config/workflow-contracts.json', 'ComfyUiClient.cs', 'GenerationQueue.cs', 'TaskSubmissionPreflightService.cs']
    for name in backup_names:
        path = ROOT / (name if name.startswith('config/') else 'server/' + name)
        dest = FOLDER / 'backups/root' / path.relative_to(ROOT)
        if not dest.exists(): dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)
    (FOLDER / 'git-status-before.txt').write_text(subprocess.check_output(['git', 'status', '--short', '--branch'], cwd=ROOT, text=True), encoding='utf-8')
    run.save('InputsFrozen', prepared=True, preserved=records, originalFinalPath=old['finalPath'],
        olderFinalPath=previous['finalPath'], sourceMaster=rel(source), femaleReference=rel(reference),
        driverPath=driver, driverProvenance='Existing self-generated task1293; transferred performance is not new live-action footage',
        plan=['six keyframes', 'H3 first-only versus first-last controlled motion', 'local reference-driven portrait', 'selected QHD comparison'],
        localInferenceOnly=True, maxTargetedRepairs=2)
    print(json.dumps(dict(preserved=len(records), existingModelFiles=len(inventory), reference=rel(reference))), flush=True)

def project(run):
    run.access()
    if run.state.get('projectId'): return
    name = '画面优化小验证包_' + run.state['runId'][:8]
    matches = [p for p in run.api('/api/projects') if p['name'] == name]
    if matches: pid = matches[0]['id']
    elif run.state.get('projectStarted'): raise RuntimeError('Project creation outcome unresolved')
    else:
        run.save(projectStarted=True)
        pid = run.api('/api/projects', dict(name=name, description='Local visual validation with frozen prior media; experimental, human content review required.',
            defaultWidth=2560, defaultHeight=1440, defaultFps=24), key='project')['id']
    run.save(projectId=pid)

def register_keyframes(run):
    setup = ROOT / 'tools/visual_pilot_keyframes'
    definition = read(setup / 'contract-definition.json')
    definition.update(id='flux2-klein4b-keyframe-local-1024-v2', version='flux2-klein4b-keyframe-local-1024-v2',
        fileName='flux2_klein4b_keyframe_v2_api.json')
    source = setup / 'flux2_klein4b_keyframe_api.json'; target = ROOT.parent / 'Workflows' / definition['fileName']
    if target.exists() and sha(target) != sha(source): raise RuntimeError('Frozen V2 workflow differs')
    if not target.exists(): shutil.copy2(source, target)
    contracts = ROOT / 'config/workflow-contracts.json'; document = read(contracts)
    existing = [c for c in document['contracts'] if c['id'] == definition['id']]
    if existing and existing != [definition]: raise RuntimeError('Frozen V2 contract differs')
    if not existing: document['contracts'].append(definition); write(contracts, document)
    project(run); run.api('/api/workflows/scan', {}, timeout=600)
    run.save(keyframeWorkflowVersion=definition['version'], keyframeWorkflowName=target.stem, keyframeWorkflowSha256=sha(target))
    print('Final three-quarter-angle V2 route registered; earlier draft V1 preserved')

def keyframes(run, index):
    project(run)
    if not run.state.get('keyframeWorkflowVersion'): raise RuntimeError('Register frozen V2 route first')
    sys.path.insert(0, str(ROOT / 'tools/visual_pilot_keyframes'))
    from prepare import CASES, PRESERVE
    workflow = next(w for w in run.api('/api/workflows') if w['name'] == run.state['keyframeWorkflowName'])
    if sha(ROOT.parent / 'Workflows' / (run.state['keyframeWorkflowName'] + '.json')) != run.state['keyframeWorkflowSha256']:
        raise RuntimeError('Klein workflow drifted')
    for position, (case_id, instruction) in enumerate(CASES, 1):
        if index and position != index: continue
        body = dict(projectId=run.state['projectId'], taskType='Image', resourceClass='GPU', workflowId=workflow['id'],
            inputImagePath=run.state['femaleReference'], maxRetries=0, stage='Visual-Validation-' + case_id,
            parameters=dict(workflowVersion=run.state['keyframeWorkflowVersion'], width=1024, height=576,
                seed=20261024, steps=4, cfg=1, prompt=PRESERVE + instruction,
                inputSlots=dict(firstFrame=run.state['femaleReference'])))
        detail = run.once('keyframe' + str(position) + 'TaskId', body)
        path = result(detail, '.png')
        image = Image.open(media(path))
        if image.size != (1024, 576): raise RuntimeError('Unexpected keyframe dimensions')
        run.save('KeyframesInProgress', **{'keyframe' + str(position) + 'Path': path,
            'keyframe' + str(position) + 'Sha256': sha(media(path))})
    if all(run.state.get('keyframe' + str(i) + 'Path') for i in range(1, 7)):
        run.save('AwaitingKeyframeInspection', keyframesCompleted=True)
        print('Six newly generated keyframes ready for visual inspection', flush=True)

def selected_inputs(run):
    run.preserve()
    selection = read(FOLDER / 'keyframe-selection.json')
    if selection.get('decision') != 'SelectedForLocalPilot': raise RuntimeError('Inspect actual candidates before video work')
    outputs = {}
    for role in ['first', 'last']:
        item = selection[role]; source = media(item['path'])
        if sha(source) != item['sha256']: raise RuntimeError('Selected keyframe changed')
        output = FOLDER / 'inputs' / ('h3-' + role + '.png')
        image = ImageOps.fit(Image.open(source).convert('RGB'), (864, 480), method=Image.Resampling.LANCZOS)
        encoded=io.BytesIO();image.save(encoded,format='PNG')
        if output.exists() and output.read_bytes()!=encoded.getvalue(): raise RuntimeError('Frozen H3 input crop differs')
        if not output.exists(): output.write_bytes(encoded.getvalue())
        outputs[role] = dict(path=rel(output), sha256=sha(output))
    write(FOLDER / 'h3-inputs.json', dict(operation='Documented center-crop and resize from selected new keyframes', selected=selection, outputs=outputs))
    run.save(selectionSha256=sha(FOLDER/'keyframe-selection.json'))
    return outputs

def h3(run, mode):
    project(run); inputs = selected_inputs(run)
    prompt = ('A single locked camera close-up of the exact same adult woman, same identity, hair, cardigan and room. '
        'At first she rests with a neutral closed mouth. She slowly softens her eyes and develops only a tiny closed-lip smile, '
        'with gentle breathing and one natural blink. Keep her original three-quarter head angle and face proportions. '
        'No talking, no visible teeth, no large head turn, no camera movement. Background and window light remain stable. '
        'Finish in the same restrained slight-smile pose. Audio: quiet room tone, no speech, no music, no subtitles.')
    body = dict(projectId=run.state['projectId'], prompt=prompt, inputImagePath=inputs['first']['path'], seed=2026102407,
        profile='firstlast480' if mode == 'controlled' else 'baseline480', steps=20)
    if mode == 'controlled': body.update(lastFramePath=inputs['last']['path'],
        firstFrameSha256=inputs['first']['sha256'], lastFrameSha256=inputs['last']['sha256'])
    detail = run.once('h3' + mode.title() + 'TaskId', body, endpoint='/api/minimax/local/video')
    path = result(detail, '.mp4')
    run.save('AwaitingH3Inspection', **{'h3' + mode.title() + 'Path': path, 'h3' + mode.title() + 'Sha256': sha(media(path))})
    print(path, flush=True)

def acting(run):
    project(run)
    selection = read(FOLDER / 'keyframe-selection.json')
    if selection.get('decision') != 'SelectedForLocalPilot': raise RuntimeError('Actual image inspection required')
    source = media(selection.get('acting', selection['first'])['path'])
    manifest = FOLDER / 'acting-manifest.json'
    value = dict(sourcePath=str(source), sourceSha256=sha(source), drivingPath=str(media(run.state['driverPath'])),
        drivingSha256=sha(media(run.state['driverPath'])), outputDirectory=str(FOLDER/'acting-private-output'),
        durationSeconds=2, drivingStartSeconds=0, animationRegion='all', drivingMultiplier=.6,
        driverOrigin=run.state['driverProvenance'], licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
    if manifest.exists() and read(manifest) != value: raise RuntimeError('Acting manifest already frozen')
    if not manifest.exists(): write(manifest, value)
    engine = ROOT / 'tools/visual_pilot_acting/run.py'
    body = dict(projectId=run.state['projectId'], taskType='VisualActing', resourceClass='GPU', maxRetries=0,
        stage='Visual-Validation-Reference-Acting-2s', parameters=dict(manifest=rel(manifest), manifestSha256=sha(manifest), engineVersion=sha(engine)))
    detail = run.once('actingTaskId', body); path = result(detail, '.mp4')
    receipt = next(x['assetPath'] for x in detail['results'] if x.get('available') and 'visual_acting_receipt' in x.get('assetPath',''))
    run.save('AwaitingActingInspection', actingPath=path, actingSha256=sha(media(path)),actingReceiptPath=receipt)
    print(path, flush=True)

def normalize_acting(run):
    project(run)
    review = read(FOLDER / 'acting-review.json')
    if review.get('decision') != 'SelectedForComparison': raise RuntimeError('Inspect actual acting output first')
    if review.get('path')!=run.state['actingPath'] or review.get('sha256')!=sha(media(run.state['actingPath'])):
        raise RuntimeError('Reviewed acting take changed')
    for label, source in [('Original', run.state['driverPath']), ('New', run.state['actingPath'])]:
        body = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU', maxRetries=0,
            stage='Visual-Validation-Acting-' + label + '-24FPS', parameters=dict(files=[source], targetWidth=1280,
                targetHeight=720, targetFps=24, targetDurationSeconds=2, originalAudioVolume=0,
                outputName='visual_acting_' + label.lower() + '_2s_24fps.mp4'))
        detail = run.once('acting' + label + 'CompareTaskId', body); path = result(detail, '.mp4')
        run.save(**{'acting' + label + 'ComparePath': path,'acting' + label + 'CompareSha256':sha(media(path))})

def qhd(run):
    project(run)
    review = read(FOLDER / 'acting-review.json')
    if review.get('decision') != 'SelectedForComparison': raise RuntimeError('Select actual native output before enhancement')
    source = run.state['actingNewComparePath']; status = run.api('/api/video-restore/status')
    if not status['ready']: raise RuntimeError(status['message'])
    body = dict(projectId=run.state['projectId'], taskType='VideoRestore', resourceClass='GPU', maxRetries=0,
        stage='Visual-Validation-Selected-Portrait-QHD', parameters=dict(input=source, sourceSha256=sha(media(source)),
            engineVersion=status['engineVersion'], strength=.30, cutFrames=[], outputProfile='qhd1440', targetWidth=2560, targetHeight=1440))
    detail = run.once('qhdTaskId', body); path = result(detail, '.mp4')
    run.save('AwaitingFinalInspection', qhdPath=path, qhdSha256=sha(media(path)))
    print(path, flush=True)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--stage', choices=['prepare', 'project', 'register-keyframes', 'keyframes', 'h3', 'h3-pair', 'acting', 'normalize-acting', 'finish-acting', 'qhd', 'check'], required=True)
    parser.add_argument('--index', type=int, choices=range(0,7), default=0)
    parser.add_argument('--mode', choices=['baseline','controlled'], default='baseline')
    parser.add_argument('--api', default='http://127.0.0.1:18081'); args = parser.parse_args()
    run = Run(args.api, FOLDER / 'run.json')
    if run.state.get('completed') and args.stage!='check':
        run.preserve();print('Completed package is read-only; no new task or selection change');return
    if args.stage == 'prepare': prepare(run)
    elif args.stage == 'project': project(run)
    elif args.stage == 'register-keyframes': register_keyframes(run)
    elif args.stage == 'keyframes': keyframes(run,args.index)
    elif args.stage == 'h3': h3(run,args.mode)
    elif args.stage == 'h3-pair': h3(run,'baseline');h3(run,'controlled')
    elif args.stage == 'acting': acting(run)
    elif args.stage == 'normalize-acting': normalize_acting(run)
    elif args.stage == 'finish-acting': normalize_acting(run);qhd(run)
    elif args.stage == 'qhd': qhd(run)
    else: run.preserve(); print('Frozen source hashes Passed; no task submitted', flush=True)

if __name__ == '__main__': main()

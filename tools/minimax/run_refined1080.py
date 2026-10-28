"""Refine one local keyframe, then generate one native1080 H3 take via the service queue."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact, video_probe

DATA = Path(r'C:\install\AI\Data')
REPORT = DATA / 'H3Refined108020261020/run.json'
BASELINE = DATA / 'H3Native108020261019/attempt-2/run.json'
WORKFLOW = 'h3_keyframe_refine_1088_api.json'
VERSION = 'h3-keyframe-refine-1088-v1'
FIRST_PROMPT = (
    'Architectural photograph of the same empty red brick university courtyard, regular red brick courses '
    'and fine pale mortar joints, straight white window mullions, the same arched stone entrance, '
    'distinct small green leaves and visible slender branches, realistic grass texture, soft morning daylight, '
    'restrained natural colors, crisp material detail, consistent original composition.'
)
NEGATIVE = 'people, text, watermark, painterly, plastic, oversaturated, sharpening halos, blurry foliage, warped windows, melted bricks, duplicate objects'
PROMPT = (
    'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
    'integrated_multimodal_description: [Shot 1] Live-action architectural footage of the empty university '
    'courtyard in the reference image. Preserve the red brick facade, rectangular white window grid, '
    'arched entrance on the right, pale concrete path, lawn and single tree. One uninterrupted eye-level '
    'shot from 0.00 to 5.17 seconds. The stabilized camera pushes straight forward with small amplitude '
    'at slow, constant speed along the path toward the entrance, advancing about half a metre. The entrance '
    'grows gradually larger and the nearer tree shifts slightly against the distant wall. The camera '
    'keeps its heading, level horizon and focal length throughout. The tree trunk and main branches remain '
    'steady; a very light breeze moves only a few small leaf clusters gently at the outer tips. Individual '
    'leaf clusters retain their outlines and the gaps between branches remain visible. Fine brick courses, '
    'straight window mullions and stone joints retain consistent geometry and material texture as the '
    'camera advances. Crisp short-exposure appearance, natural depth of field, stable morning illumination, '
    'restrained realistic colors. The courtyard remains empty, no on-screen text.\n\n'
    'overall_soundscape: Faint birds in the distance and a very soft rustle of leaves in the quiet courtyard. '
    'Natural outdoor ambience, no speech.\n\nnon_diegetic_music: None.'
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve(run):
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    if baseline.get('technicalStatus') != 'Passed' or baseline.get('stage') != 'ReadyForUserPreview':
        raise RuntimeError('Existing native1080 baseline is not ready; preserved')
    frozen = dict(projectId=baseline['projectId'], seed=baseline['seed'], baselineTaskId=baseline['taskId'],
                  baselineVideoPath=baseline['videoPath'], baselineVideoSha256=baseline['videoSha256'],
                  sourceFirstFramePath=baseline['firstFramePath'], sourceFirstFrameSha256=baseline['firstFrameSha256'],
                  profile='native1080', width=1920, height=1088, deliveryWidth=1920, deliveryHeight=1080,
                  crop={'x': 0, 'y': 4, 'width': 1920, 'height': 1080}, frames=124, fps=24, steps=20,
                  prompt=PROMPT, firstFramePrompt=FIRST_PROMPT, negative=NEGATIVE)
    if (run.state.get('frameTaskId') or run.state.get('taskId')) and any(run.state.get(k) != v for k, v in frozen.items()):
        raise RuntimeError('Recorded frozen inputs differ; no new submission')
    for path, expected in [(baseline['videoPath'], baseline['videoSha256']),
                           (baseline['firstFramePath'], baseline['firstFrameSha256'])]:
        if sha(DATA / path) != expected:
            raise RuntimeError('Preserved baseline media fingerprint differs')
    run.save(**frozen, spatialUpscale=False,
             firstFrameOrigin='SD1.5 synthetic source at 1376x768, resized then low-denoise SD1.5 img2img at 1920x1088; not native photographic detail.',
             changeReason='New high-resolution low-denoise first-frame refinement and simpler straight, slower camera/limited leaf motion; fixed native1080/24fps/124frames/20steps/seed/CRF16.',
             error=None)


def submit_once(run, field, stage, endpoint, payload):
    if not run.state.get(field):
        marker = field + 'SubmissionStarted'
        if run.state.get(marker):
            raise RuntimeError('Submission outcome unresolved for ' + field + '; query tasks before retry')
        queue = run.api('/api/minimax/local/status')['queue']
        if queue.get('activeTasks') or queue.get('paused'):
            raise RuntimeError('Service queue is active or paused; no extra GPU task submitted')
        run.save(stage, **{marker: True, field + 'PreSubmissionQueue': queue})
        result = run.api(endpoint, payload, key=field, timeout=600)
        task_id = result.get('id') or result.get('taskId')
        if not task_id:
            raise RuntimeError('Submission response has no task ID; outcome unresolved')
        run.save(**{field: task_id})
        print(stage + ' task=' + str(task_id), flush=True)
    return run.poll(run.state[field], limit=11400 if field == 'taskId' else 1800)


def frames(run):
    if run.state.get('taskId'):
        print('Video already submitted; frozen first frame preserved.', flush=True)
        return
    lookup = {item['name']: item['id'] for item in run.api('/api/workflows')}
    detail = submit_once(run, 'frameTaskId', 'RefiningFirstFrame', '/api/tasks', {
        'projectId': run.state['projectId'], 'taskType': 'Image', 'resourceClass': 'GPU',
        'workflowId': lookup[Path(WORKFLOW).stem], 'inputImagePath': run.state['sourceFirstFramePath'],
        'stage': 'H3-Refined1080-Keyframe', 'maxRetries': 0,
        'parameters': {'workflowVersion': VERSION, 'width': 1920, 'height': 1088, 'fps': 1,
                       'inputSlots': {'firstFrame': run.state['sourceFirstFramePath']},
                       'prompt': FIRST_PROMPT, 'negative': NEGATIVE, 'seed': 2026102001,
                       'steps': 24, 'cfg': 4.0, 'denoise': 0.18}})
    relative = artifact(detail, ('.png',))
    with Image.open(DATA / relative) as still:
        if still.size != (1920, 1088):
            raise RuntimeError('Refined first frame dimensions differ')
        still.load()
    run.save('AwaitingFirstFrameInspection', firstFramePath=relative, firstFrameSha256=sha(DATA / relative),
             frameMetrics={k: detail['task'].get(k) for k in ('id', 'durationMs', 'vramPeakMiB')})
    print(json.dumps({'firstFramePath': relative}), flush=True)


def generate(run):
    inspection = REPORT.parent / 'first-frame-review.json'
    review = json.loads(inspection.read_text(encoding='utf-8'))
    frame, fingerprint = run.state['firstFramePath'], run.state['firstFrameSha256']
    if review.get('status') != 'SelectedForExperiment' or review.get('sha256') != fingerprint or sha(DATA / frame) != fingerprint:
        raise RuntimeError('Refined first frame has not passed visual selection for this experiment')
    if not run.state.get('taskId'):
        run.api('/api/minimax/local/verify', {}, timeout=600)
        protocol = json.loads((BASELINE.parent.parent / 'codec-protocol-check.json').read_text(encoding='utf-8'))
        if protocol.get('status') != 'Passed' or protocol.get('workflowSaveInputs') != json.loads(
                (Path(__file__).parent / 'minimax_h3_local_1088_i2v_api.json').read_text(encoding='utf-8'))['15']['inputs']:
            raise RuntimeError('Native1080 SaveVideo protocol fixture does not match')
    detail = submit_once(run, 'taskId', 'GeneratingRefinedNative1080', '/api/minimax/local/video', {
        'projectId': run.state['projectId'], 'profile': 'native1080', 'inputImagePath': frame,
        'prompt': PROMPT, 'seed': run.state['seed']})
    video, audio = artifact(detail, ('.mp4',)), artifact(detail, ('.wav',))
    probe = video_probe(video, 1920, 1080)
    graph = json.loads(probe['format']['tags']['prompt'])
    condition, crop, save = graph['6']['inputs'], graph['16']['inputs'], graph['15']['inputs']
    if (condition['prompt'] != PROMPT or (condition['width'], condition['height'], condition['length']) != (1920, 1088, 124)
            or graph['7']['inputs']['noise_seed'] != run.state['seed']
            or graph['5'].get('is_changed') != [fingerprint]
            or graph['10']['inputs']['steps'] != 20 or graph['14']['inputs']['fps'] != 24
            or any(crop[k] != v for k, v in run.state['crop'].items())
            or graph['14']['inputs']['images'] != ['16', 0] or crop['image'] != ['12', 0]
            or save['codec'] != 'h264' or save['codec.encoding'] != 're-encode' or save['codec.encoding.crf'] != 16.0
            or any('scale' in node['class_type'].lower() for node in graph.values())):
        raise RuntimeError('Actual execution differs from frozen native1080 inputs')
    preserve(run)
    if sha(DATA / frame) != fingerprint:
        raise RuntimeError('New first frame changed during video generation')
    run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview', publicationStatus='Blocked',
             videoPath=video, audioPath=audio, videoSha256=sha(DATA / video), probe=probe,
             metrics={k: detail['task'].get(k) for k in ('id', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')})
    print(json.dumps({'taskId': run.state['taskId'], 'videoPath': video, 'technicalStatus': 'Passed'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['frames', 'generate'], required=True)
    stage = parser.parse_args().stage
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(REPORT.parent, '.h3-refined1080.lock', 'Another refined1080 experiment is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            run.access()
            preserve(run)
            if stage == 'frames':
                frames(run)
            else:
                generate(run)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'Refined1080 {status}: {type(error).__name__}: {str(error)[:600]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

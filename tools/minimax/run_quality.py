"""Fresh H3 480p/768p comparison through the local service queue only."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure

DATA = Path(r'C:\install\AI\Data')
REPORT = DATA / 'H3Quality20261018/run.json'
FFPROBE = r'C:\install\FFmpeg\bin\ffprobe.exe'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'
FIRST_FRAME_PROMPT = (
    'Architectural photograph of a quiet university library courtyard on a bright clear morning. '
    'One coherent red brick academic building with straight vertical walls, a regular grid of rectangular windows, '
    'a single simple entrance and a gently receding brick pedestrian path. Medium wide eye-level composition, '
    '35mm architectural photography, corrected vertical perspective. The building occupies most of the frame; '
    'window mullions, brick mortar and paving joints are clearly resolved. One leafy tree frames the left edge, '
    'neatly cut lawn, soft directional morning sunlight, natural balanced greens, realistic brick material. '
    'Restrained documentary color, natural exposure, crisp moderate depth of field, empty peaceful campus.'
)
NEGATIVE = 'people, faces, text, signs, letters, watermark, logo, fisheye, tilted walls, warped windows, melted architecture, collage, painterly, cartoon, heavy blur, oversaturated, oversharpening halos'
VIDEO_PROMPT = (
    'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
    'integrated_multimodal_description: [Shot 1] Live-action architectural cinematography. '
    'The university courtyard in the reference image is the opening frame. Preserve its red brick facade, '
    'window grid, arched entrance at the far right, pale concrete path at the lower right, '
    'tree in the middle-right, and morning light. A static eye-level tripod shot '
    'keeps the composition and focal length constant for the full 5.17 seconds. From 0.00 to 1.00 seconds '
    'the scene settles naturally. From 1.00 to 4.20 seconds a light breeze gently moves only a few clusters '
    'of leaves on the middle-right tree; their soft shadows shift subtly on the grass. From 4.20 to 5.17 seconds '
    'the breeze eases. Brick mortar, window frames and the concrete path edges retain stable fine detail throughout. '
    'Natural restrained daylight, neutral documentary color, coherent geometry. The courtyard stays empty. '
    'One uninterrupted shot, no on-screen text.\n\n'
    'overall_soundscape: Quiet outdoor campus ambience, soft wind in the nearby leaves and one faint distant '
    'bird call. Low natural volume, no speech or narration, no traffic.\n\n'
    'non_diegetic_music: None.'
)


class QualityRun(Acceptance):
    def poll(self, task_id, limit=5400):
        return super().poll(task_id, limit)


def artifact(detail, extensions):
    result = Acceptance.result(detail, extensions)
    if not result:
        raise RuntimeError('Task has no available registered result: ' + str(detail['task']['id']))
    return result['assetPath']


def prepare(run):
    run.access()
    workflows = {w['name']: w['id'] for w in run.api('/api/workflows')}
    if not run.state.get('projectId'):
        name = 'H3原生768p画质对照_' + run.state['runId'][:8]
        matches = [p for p in run.api('/api/projects') if p['name'] == name]
        if len(matches) == 1:
            run.save(projectId=matches[0]['id'])
        elif run.state.get('projectSubmissionStarted'):
            raise RuntimeError('Project creation outcome unresolved; no duplicate creation')
        else:
            run.save('CreatingQualityProject', projectSubmissionStarted=True)
            created = run.api('/api/projects', {'name': name, 'description': 'Local H3 native 480p/768p comparison; same prepared keyframe, prompt, seed and steps. Human review required.', 'defaultWidth': 1376, 'defaultHeight': 768, 'defaultFps': 24})
            run.save(projectId=created['id'])
    if (run.state.get('quality768TaskId') or run.state.get('baseline480TaskId')) and run.state.get('videoPrompt') != VIDEO_PROMPT:
        raise RuntimeError('The prompt is already frozen for the comparison; changed prompt preserved without submitting')
    run.save(firstFramePrompt=FIRST_FRAME_PROMPT, negative=NEGATIVE, videoPrompt=VIDEO_PROMPT, seed=2026101841,
             modelRoute='MiniMax H3 FL2VA Q4 + Qwen Q2; existing pinned models', error=None)
    return workflows


def frames(run, workflows):
    if run.state.get('quality768TaskId') or run.state.get('baseline480TaskId'):
        print('The comparison already froze its first frame; existing tasks and stage preserved.', flush=True)
        return
    for index in (0, 1):
        key = 'candidate' + str(index)
        detail = run.task(key + 'TaskId', 'GeneratingFirstFrameCandidates', {
            'projectId': run.state['projectId'], 'taskType': 'Image', 'resourceClass': 'GPU',
            'workflowId': workflows['06_scene_keyframe_quality_api'], 'stage': 'H3-Quality-Keyframe', 'maxRetries': 0,
            'parameters': {'prompt': FIRST_FRAME_PROMPT, 'negative': NEGATIVE, 'width': 864, 'height': 480,
                           'steps': 28, 'cfg': 6.5, 'seed': 2026101840 + index}})
        run.save(**{key + 'Path': artifact(detail, ('.png', '.jpg', '.webp'))})
    run.save('AwaitingFirstFrameSelection')
    print(json.dumps({key: run.state[key] for key in ('candidate0Path', 'candidate1Path')}), flush=True)


def video_probe(relative, width, height):
    path = DATA / relative
    result = subprocess.run([FFPROBE, '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, check=True, timeout=120)
    info = json.loads(result.stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if video['width'] != width or video['height'] != height or Fraction(video['avg_frame_rate']) != 24 or int(video['nb_read_frames']) != 124:
        raise RuntimeError('Actual H3 output specification mismatch; no post resize/frame-count correction')
    if not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise RuntimeError('H3 output is missing its native audio')
    subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, check=True, timeout=120)
    return info


def generate(run, workflows, candidate):
    if candidate is None and not run.state.get('chosenCandidatePath'):
        raise RuntimeError('Review the fresh candidates and explicitly choose one before H3 generation')
    selected = run.state.get('chosenCandidatePath') or run.state['candidate' + str(candidate) + 'Path']
    if candidate is not None and selected != run.state['candidate' + str(candidate) + 'Path']:
        raise RuntimeError('This comparison already froze another first frame')
    detail = run.task('preparedFrameTaskId', 'Preparing768FirstFrame', {
        'projectId': run.state['projectId'], 'taskType': 'Image', 'resourceClass': 'GPU',
        'workflowId': workflows['h3_keyframe_upscale_api'], 'inputImagePath': selected,
        'stage': 'H3-Quality-FirstFrame-Prepare', 'maxRetries': 0,
        'parameters': {'workflowVersion': 'h3-quality-keyframe-x2-v1', 'inputSlots': {'firstFrame': selected},
                       'width': 1376, 'height': 768}})
    frame = artifact(detail, ('.png',))
    fingerprint = hashlib.sha256((DATA / frame).read_bytes()).hexdigest()
    if run.state.get('firstFrameSha256') and run.state['firstFrameSha256'] != fingerprint:
        raise RuntimeError('Prepared first frame drifted; previous run preserved')
    run.save(chosenCandidatePath=selected, firstFramePath=frame, firstFrameSha256=fingerprint)
    run.api('/api/minimax/local/verify', {}, timeout=600)
    # Test native 768p first; the baseline follows only after it succeeds.
    for profile, width, height in (('quality768', 1376, 768), ('baseline480', 864, 480)):
        field = profile + 'TaskId'
        if not run.state.get(field):
            run.save('GeneratingH3-' + profile)
            result = run.api('/api/minimax/local/video', {'projectId': run.state['projectId'], 'profile': profile,
                'inputImagePath': frame, 'prompt': VIDEO_PROMPT, 'seed': run.state['seed']}, key=field, timeout=600)
            run.save(**{field: result['id']})
        detail = run.poll(run.state[field])
        relative = artifact(detail, ('.mp4',))
        audio = artifact(detail, ('.wav',))
        info = video_probe(relative, width, height)
        run.save(**{profile + 'VideoPath': relative, profile + 'AudioPath': audio, profile + 'Probe': info,
                    profile + 'Metrics': {k: detail['task'].get(k) for k in ('id', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')}})
    if hashlib.sha256((DATA / frame).read_bytes()).hexdigest() != fingerprint:
        raise RuntimeError('First frame changed during the comparison')
    run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview', publicationStatus='Blocked')
    print(json.dumps({'quality768': run.state['quality768VideoPath'], 'baseline480': run.state['baseline480VideoPath']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['frames', 'generate'], required=True)
    parser.add_argument('--candidate', type=int, choices=[0, 1])
    args = parser.parse_args()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(REPORT.parent, '.h3-quality.lock', 'Another H3 quality comparison is active'):
        run = QualityRun('http://127.0.0.1:18080', REPORT)
        try:
            workflows = prepare(run)
            if args.stage == 'frames': frames(run, workflows)
            else: generate(run, workflows, args.candidate)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'H3 quality {status}: {type(error).__name__}: {str(error)[:600]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

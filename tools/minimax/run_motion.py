"""Generate a new native-768 H3 camera/tree-motion take through VideoStudio."""
import hashlib
import json
from pathlib import Path

from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact, video_probe


DATA = Path(r'C:\install\AI\Data')
REPORT = DATA / 'H3Motion20261019/run.json'
SOURCE_REPORT = DATA / 'H3Quality20261018/run.json'
PROMPT = (
    'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
    'integrated_multimodal_description: [Shot 1] A continuous live-action moving-camera shot in the university courtyard. '
    'Starting from the reference composition, the camera immediately travels forward along the pale concrete path '
    'at the lower right toward the arched entrance. From 0.00 to 5.17 seconds, a smooth stabilized dolly advances '
    'approximately two metres, curving slightly right to follow the path. The entrance visibly grows larger, '
    'about one third larger by the final frame. Near shrubs and the middle-right tree move across the frame '
    'faster than the distant brick facade, with clear depth parallax. The forward movement is visible throughout '
    'the shot. A steady breeze visibly sways the tree branches side to side and ripples broad clusters of green '
    'leaves throughout; the moving leaves cast shifting shadows on the lawn. Preserve the same courtyard, coherent '
    'brick walls, windows, tree and daylight as the viewpoint advances. Realistic perspective, natural motion blur, '
    'smooth camera speed, one uninterrupted shot. The courtyard remains empty.\n\n'
    'overall_soundscape: Audible wind through the moving leaves and faint distant birds in an outdoor campus '
    'courtyard. Natural ambience, no speech.\n\n'
    'non_diegetic_music: None.'
)


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(REPORT.parent, '.h3-motion.lock', 'Another H3 motion take is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            run.access()
            source = json.loads(SOURCE_REPORT.read_text(encoding='utf-8'))
            if source.get('stage') != 'ReadyForUserPreview' or source.get('technicalStatus') != 'Passed':
                raise RuntimeError('The existing 768p reference run is not ready; preserved')
            frame = source['firstFramePath']
            fingerprint = hashlib.sha256((DATA / frame).read_bytes()).hexdigest()
            if fingerprint != source['firstFrameSha256']:
                raise RuntimeError('The selected first frame changed; no submission')
            if run.state.get('taskId') and any(run.state.get(k) != v for k, v in {
                'prompt': PROMPT, 'firstFramePath': frame, 'firstFrameSha256': fingerprint,
                'seed': source['seed'], 'profile': 'quality768'
            }.items()):
                raise RuntimeError('Existing motion take has different frozen inputs; preserved')
            run.save(projectId=source['projectId'], profile='quality768', width=1376, height=768,
                     fps=24, frames=124, steps=20, seed=source['seed'], prompt=PROMPT,
                     firstFramePath=frame, firstFrameSha256=fingerprint,
                     baselineTaskId=source['quality768TaskId'], baselineVideoPath=source['quality768VideoPath'],
                     baselineVideoSha256=hashlib.sha256((DATA / source['quality768VideoPath']).read_bytes()).hexdigest(),
                     changeReason='Replace locked camera/subtle leaves with forward dolly, depth parallax and visible branch motion.',
                     error=None)
            if not run.state.get('taskId'):
                if run.state.get('submissionStarted'):
                    raise RuntimeError('Previous submission outcome is unresolved; query the queue before retrying')
                run.api('/api/minimax/local/verify', {}, timeout=600)
                run.save('SubmittingMotionTake', submissionStarted=True)
                result = run.api('/api/minimax/local/video', {
                    'projectId': run.state['projectId'], 'profile': 'quality768', 'inputImagePath': frame,
                    'prompt': PROMPT, 'seed': run.state['seed']
                }, key='motion768', timeout=600)
                run.save('GeneratingMotionTake', taskId=result['id'])
                print('H3 motion task=' + str(result['id']), flush=True)
            detail = run.poll(run.state['taskId'], limit=5400)
            video = artifact(detail, ('.mp4',))
            audio = artifact(detail, ('.wav',))
            probe = video_probe(video, 1376, 768)
            graph = json.loads(probe['format']['tags']['prompt'])
            if (graph['6']['inputs']['prompt'] != PROMPT
                    or graph['7']['inputs']['noise_seed'] != run.state['seed']
                    or graph['5'].get('is_changed') != [fingerprint]):
                raise RuntimeError('Actual video execution metadata differs from the frozen motion request')
            if hashlib.sha256((DATA / frame).read_bytes()).hexdigest() != fingerprint:
                raise RuntimeError('First frame changed during generation')
            if hashlib.sha256((DATA / run.state['baselineVideoPath']).read_bytes()).hexdigest() != run.state['baselineVideoSha256']:
                raise RuntimeError('The previous video changed during generation')
            run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview', publicationStatus='Blocked',
                     videoPath=video, audioPath=audio, videoSha256=hashlib.sha256((DATA / video).read_bytes()).hexdigest(),
                     probe=probe, metrics={k: detail['task'].get(k) for k in ('id', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')})
            print(json.dumps({'taskId': run.state['taskId'], 'videoPath': video, 'technicalStatus': 'Passed'}), flush=True)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'H3 motion {status}: {type(error).__name__}: {str(error)[:600]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

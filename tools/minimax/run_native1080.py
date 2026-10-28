"""One explicit native 1920x1088 H3 experiment, cropped to 1080; queue only."""
import argparse
import hashlib
import json
from pathlib import Path

from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact, video_probe

DATA = Path(r'C:\install\AI\Data')
REPORT = DATA / 'H3Native108020261019/run.json'
SOURCE_REPORT = DATA / 'H3Motion20261019/run.json'
PROMPT = (
    'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
    'integrated_multimodal_description: [Shot 1] A continuous live-action architectural shot in the university '
    'courtyard shown in the reference image. Preserve the same red brick facade, regular windows, arched entrance '
    'at the far right, concrete path, middle-right tree and morning daylight. From 0.00 to 5.17 seconds, a smooth '
    'stabilized camera advances slowly about one metre along the concrete path toward the arched entrance, '
    'curving slightly right. The entrance grows visibly larger and the nearer tree shifts against the distant '
    'building with clear depth parallax. The forward movement continues steadily throughout the shot. A gentle '
    'breeze visibly sways the larger branches and broad clusters of leaves slowly side to side. Each leaf cluster '
    'keeps a distinct contour as it moves, with clear small gaps between branches. Crisp short-exposure appearance, '
    'sharp foliage edges in motion, fine brick mortar, clean window mullions, natural moderate depth of field. '
    'Restrained daylight and documentary color, coherent straight walls and perspective, one uninterrupted shot. '
    'The courtyard remains empty, no on-screen text.\n\n'
    'overall_soundscape: Soft audible wind through the tree and faint distant birds in a quiet outdoor campus '
    'courtyard. Natural ambience, no speech.\n\n'
    'non_diegetic_music: None.'
)


def main():
    global REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=[1, 2, 3], default=1)
    attempt = parser.parse_args().attempt
    original_report = REPORT
    if attempt > 1:
        REPORT = original_report.parent / f'attempt-{attempt}' / 'run.json'
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(REPORT.parent, '.h3-native1080.lock', 'Another native1080 experiment is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            run.access()
            if attempt > 1:
                previous_report = original_report if attempt == 2 else original_report.parent / f'attempt-{attempt - 1}' / 'run.json'
                previous = json.loads(previous_report.read_text(encoding='utf-8'))
                previous_task = run.api(f"/api/tasks/{previous['taskId']}")['task']
                if previous_task['status'] != 'Failed':
                    raise RuntimeError('Previous GPU task is not confirmed Failed; no retry submission')
                run.save(previousAttemptReport=str(previous_report), previousTaskId=previous['taskId'],
                         previousFailure=previous_task.get('errorMessage'), repair='SaveVideo V3 flat codec keys; full 1080p CPU/audio fixture passed; native deadline 180 minutes.')
            source = json.loads(SOURCE_REPORT.read_text(encoding='utf-8'))
            if source.get('technicalStatus') != 'Passed' or source.get('stage') != 'ReadyForUserPreview':
                raise RuntimeError('The existing motion reference is not ready; preserved')
            frame = source['firstFramePath']
            fingerprint = hashlib.sha256((DATA / frame).read_bytes()).hexdigest()
            if fingerprint != source['firstFrameSha256']:
                raise RuntimeError('First frame changed; no submission')
            frozen = dict(profile='native1080', prompt=PROMPT, firstFramePath=frame,
                          firstFrameSha256=fingerprint, seed=source['seed'])
            if run.state.get('taskId') and any(run.state.get(k) != v for k, v in frozen.items()):
                raise RuntimeError('Existing experiment has different frozen inputs; preserved')
            run.save(**frozen, projectId=source['projectId'], width=1920, height=1088,
                     deliveryWidth=1920, deliveryHeight=1080, crop={'x': 0, 'y': 4, 'width': 1920, 'height': 1080},
                     spatialUpscale=False, fps=24, frames=124, steps=20,
                     firstFrameOrigin='Existing selected SD1.5 first frame, prepared with RealESRGAN x2 to 1376x768; reused explicitly for comparison.',
                     baselineTaskId=source['taskId'], baselineVideoPath=source['videoPath'],
                     baselineVideoSha256=source['videoSha256'],
                     changeReason='Explicit native1080 trial; slower visible dolly and branch motion, crisp foliage cues instead of natural motion blur; CRF16 encoding. Not a resolution-only controlled comparison.',
                     error=None)
            if not run.state.get('taskId'):
                if run.state.get('submissionStarted'):
                    raise RuntimeError('Submission outcome unresolved; query queue before any retry')
                queue = run.api('/api/minimax/local/status')['queue']
                run.save(preSubmissionQueue=queue)
                # The pinned model verification and managed queue perform admission before submission.
                run.api('/api/minimax/local/verify', {}, timeout=600)
                protocol = json.loads((original_report.parent / 'codec-protocol-check.json').read_text(encoding='utf-8'))
                if protocol.get('status') != 'Passed' or protocol.get('workflowSaveInputs') != json.loads(
                        (Path(__file__).parent / 'minimax_h3_local_1088_i2v_api.json').read_text(encoding='utf-8'))['15']['inputs']:
                    raise RuntimeError('Current SaveVideo encoding protocol has not passed the CPU fixture')
                run.save('SubmittingNative1080', submissionStarted=True)
                result = run.api('/api/minimax/local/video', {
                    'projectId': run.state['projectId'], 'profile': 'native1080', 'inputImagePath': frame,
                    'prompt': PROMPT, 'seed': run.state['seed']
                }, key='native1080', timeout=600)
                run.save('GeneratingNative1080', taskId=result['id'])
                print('H3 native1080 task=' + str(result['id']), flush=True)
            detail = run.poll(run.state['taskId'], limit=11400)
            video, audio = artifact(detail, ('.mp4',)), artifact(detail, ('.wav',))
            probe = video_probe(video, 1920, 1080)
            graph = json.loads(probe['format']['tags']['prompt'])
            condition, crop = graph['6']['inputs'], graph['16']['inputs']
            if (condition['prompt'] != PROMPT or (condition['width'], condition['height'], condition['length']) != (1920, 1088, 124)
                    or graph['7']['inputs']['noise_seed'] != run.state['seed']
                    or graph['5'].get('is_changed') != [fingerprint]
                    or any(crop[k] != v for k, v in run.state['crop'].items())
                    or graph['14']['inputs']['images'] != ['16', 0]
                    or graph['16']['inputs']['image'] != ['12', 0]
                    or graph['15']['inputs']['codec'] != 'h264'
                    or graph['15']['inputs']['codec.encoding'] != 're-encode'
                    or graph['15']['inputs']['codec.encoding.crf'] != 16.0):
                raise RuntimeError('Actual execution metadata differs from the frozen native1080 experiment')
            if any('scale' in node['class_type'].lower() for node in graph.values()):
                raise RuntimeError('Unexpected spatial upscale node in native experiment')
            for path, expected in [(frame, fingerprint), (run.state['baselineVideoPath'], run.state['baselineVideoSha256'])]:
                if hashlib.sha256((DATA / path).read_bytes()).hexdigest() != expected:
                    raise RuntimeError('An existing input or comparison asset changed during generation')
            run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview', publicationStatus='Blocked',
                     videoPath=video, audioPath=audio, videoSha256=hashlib.sha256((DATA / video).read_bytes()).hexdigest(),
                     probe=probe, metrics={k: detail['task'].get(k) for k in ('id', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')})
            print(json.dumps({'taskId': run.state['taskId'], 'videoPath': video, 'technicalStatus': 'Passed'}), flush=True)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'H3 native1080 {status}: {type(error).__name__}: {str(error)[:600]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

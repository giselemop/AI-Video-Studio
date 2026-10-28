"""Generate a new 60fps-conditioned campus shot through VideoStudio's queue."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure

DATA = Path(r'C:\install\AI\Data')
FFPROBE = r'C:\install\FFmpeg\bin\ffprobe.exe'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'


def probe(path, width, height, frames, seconds):
    result = subprocess.run([FFPROBE, '-v', 'error', '-count_frames', '-show_streams',
                             '-show_format', '-of', 'json', str(path)],
                            check=True, capture_output=True, text=True, timeout=120)
    info = json.loads(result.stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (video['width'] != width or video['height'] != height
            or Fraction(video['avg_frame_rate']) != 60
            or int(video['nb_read_frames']) != frames
            or abs(float(info['format']['duration']) - seconds) > .002):
        raise RuntimeError('Native-60 experiment output does not match its declared specification')
    return info


def generate(run):
    run.access()
    sources = json.loads((DATA / 'CampusPreview20261018/run.json').read_text(encoding='utf-8'))
    image = (DATA / sources['libraryImagePath']).resolve(strict=True)
    if not image.is_relative_to(DATA) or not image.is_file():
        raise RuntimeError('Campus first frame must remain within Data')
    source_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    if run.state.get('sourceSha256') and source_hash != run.state['sourceSha256']:
        raise RuntimeError('The selected first frame changed; previous result preserved')
    if run.state.get('stage') == 'ReadyForUserPreview':
        probe(DATA / run.state['videoAssetPath'], 1280, 720, 300, 5)
        print('Existing native-60 experiment preserved; no duplicate task submitted.', flush=True)
        return
    run.save(sourceSha256=source_hash, sourceImagePath=sources['libraryImagePath'],
             projectId=sources['projectId'], generationFps=60, generatedFrames=305,
             frameInterpolation=False, error=None)
    workflows = [w for w in run.api('/api/workflows') if w['name'] == 'ltx_native60_experiment_api' and w.get('enabled')]
    if len(workflows) != 1:
        raise RuntimeError('Scan the explicitly selected native-60 experiment workflow first')
    detail = run.task('native60TaskId', 'GeneratingNative60', {
        'projectId': sources['projectId'], 'taskType': 'ImageToVideo', 'resourceClass': 'GPU',
        'workflowId': workflows[0]['id'], 'inputImagePath': sources['libraryImagePath'],
        'stage': 'Campus-LTX-Native60-Experiment', 'maxRetries': 0,
        'parameters': {'workflowVersion': 'ltx-native60-experiment-v1',
                       'inputSlots': {'firstFrame': sources['libraryImagePath']},
                       'prompt': 'One continuous cinematic wide shot of the university library courtyard. A very slow gentle camera push toward the library entrance. Leaves and their soft shadows move slightly in a light breeze, two distant adult students walk slowly across the plaza. Keep the red brick library, rectangular windows, steps and bench completely stable. Natural realistic motion, no sudden movement, no scene transition.',
                       'negative': 'cartoon, anime, illustration, low quality, blurry, text, letters, signage, watermark, logo, warped architecture, bent windows, melted building, collage, duplicated people, close-up face, malformed body, traffic, cars, night',
                       'width': 512, 'height': 320, 'frames': 305, 'fps': 60,
                       'duration': 305 / 60, 'steps': 8, 'cfg': 3, 'seed': 2026101912,
                       'frameInterpolation': False, 'contentReview': 'NeedReview'}
    })
    video = run.result(detail, ('.mp4',))
    if video is None:
        raise RuntimeError('Native generation completed without an available MP4')
    info = probe(DATA / video['assetPath'], 512, 320, 305, 305 / 60)
    # Compare decoded full-frame checksums, rather than trusting only FPS metadata.
    decoded = subprocess.run([FFMPEG, '-v', 'error', '-i', str(DATA / video['assetPath']),
                              '-map', '0:v:0', '-f', 'framemd5', '-'],
                             check=True, capture_output=True, text=True, timeout=120)
    hashes = [line.rsplit(',', 1)[-1].strip() for line in decoded.stdout.splitlines()
              if line and not line.startswith('#')]
    if len(hashes) != 305:
        raise RuntimeError('Full decode did not yield all 305 generated frames')
    frame_checks = {'decodedFrames': len(hashes), 'uniqueDecodedFrames': len(set(hashes)),
                    'adjacentExactDuplicates': sum(a == b for a, b in zip(hashes, hashes[1:])),
                    'note': 'Exact checksum differences alone do not establish motion quality.'}
    run.save(nativeVideoAssetPath=video['assetPath'], nativeProbe=info, frameChecks=frame_checks,
             nativeMetrics={key: detail['task'].get(key) for key in
                            ('id', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')})
    delivery = run.task('deliveryTaskId', 'DeliveringNative60', {
        'projectId': sources['projectId'], 'taskType': 'Concat', 'resourceClass': 'CPU',
        'stage': 'Campus-LTX-Native60-Delivery', 'maxRetries': 0,
        'parameters': {'files': [video['assetPath']], 'outputName': 'campus_native60_experiment_5s.mp4',
                       'targetDurationSeconds': 5, 'targetWidth': 1280,
                       'targetHeight': 720, 'targetFps': 60}
    })
    final = run.result(delivery, ('.mp4',))
    if final is None:
        raise RuntimeError('Native-60 delivery has no available MP4')
    final_path = DATA / final['assetPath']
    final_info = probe(final_path, 1280, 720, 300, 5)
    subprocess.run([FFMPEG, '-v', 'error', '-i', str(final_path), '-f', 'null', '-'],
                   capture_output=True, check=True, timeout=120)
    if source_hash != hashlib.sha256(image.read_bytes()).hexdigest():
        raise RuntimeError('First frame changed during the experiment')
    run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview',
             publicationStatus='Blocked', probe=final_info, videoAssetPath=final['assetPath'],
             absoluteVideoPath=str(final_path), originalFrameUnchanged=True)
    print(json.dumps({'video': str(final_path), 'nativeTaskId': run.state['native60TaskId'],
                      'deliveryTaskId': run.state['deliveryTaskId'], 'nativeFrames': 305,
                      'deliveryFrames': 300, 'fps': 60, 'seconds': 5, 'frameChecks': frame_checks}), flush=True)


def main():
    report = DATA / 'LtxNative6020261018/run.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(report.parent, '.native60.lock', 'Another native-60 experiment is active'):
        run = Acceptance('http://127.0.0.1:18080', report)
        try:
            generate(run)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'Native-60 experiment {status}: {str(error)[:500]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

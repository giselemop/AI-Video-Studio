"""Enhance the approved campus preview sources through the real service queue.

Keeps source files unchanged and resumes recorded tasks instead of submitting
duplicate GPU jobs. Content review and publication remain separate.
"""
from __future__ import annotations

import argparse
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def asset(data: Path, relative: str) -> Path:
    candidate = (data / relative).resolve(strict=True)
    if not candidate.is_relative_to(data) or not candidate.is_file():
        raise ValueError('Media must be a file within the configured Data directory')
    return candidate


def probe(ffprobe: Path, path: Path, width: int, height: int,
          fps: int, frames: int, seconds: float) -> dict:
    result = subprocess.run([str(ffprobe), '-v', 'error', '-count_frames',
                             '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, check=True, timeout=120)
    info = json.loads(result.stdout)
    video = next(item for item in info['streams'] if item['codec_type'] == 'video')
    if (video['width'] != width or video['height'] != height
            or Fraction(video['avg_frame_rate']) != fps
            or int(video['nb_read_frames']) != frames
            or abs(float(info['format']['duration']) - seconds) > .002):
        raise RuntimeError(f'Actual media does not match {width}x{height}/{fps}fps/{frames}frames: {path.name}')
    return info


def metrics(detail: dict) -> dict:
    return {key: detail['task'].get(key) for key in
            ('id', 'status', 'durationMs', 'vramPeakMiB', 'startedAt', 'finishedAt')}


def enhance(args, run: Acceptance):
    config = json.loads((ROOT / 'config/appsettings.json').read_text(encoding='utf-8-sig'))
    data = Path(config['Paths']['Data']).resolve(strict=True)
    sources = json.loads(args.sources.read_text(encoding='utf-8-sig'))
    run.access()
    snapshot = []
    for key in ('avenueVideoPath', 'libraryVideoPath', 'videoAssetPath'):
        path = asset(data, sources[key])
        snapshot.append({'field': key, 'assetPath': sources[key], 'sha256': sha256(path)})
    if run.state.get('sourceSnapshot') and snapshot != run.state['sourceSnapshot']:
        raise RuntimeError('Source files changed since this run started; existing results preserved')
    run.save(projectId=sources['projectId'], sourceSnapshot=snapshot,
             originalVideoAssetPath=sources['videoAssetPath'], error=None)
    if run.state['stage'] == 'ReadyForUserPreview':
        probe(args.ffprobe, asset(data, run.state['videoAssetPath']), 1280, 720, 30, 300, 10)
        print('Existing verified upscale output preserved; no duplicate tasks submitted.', flush=True)
        return
    workflow = [item for item in run.api('/api/workflows')
                if item['name'] == 'realesrgan_x2_video_api' and item.get('enabled')]
    if len(workflow) != 1:
        raise RuntimeError('Prepare and scan the pinned Real-ESRGAN workflow before running')
    output_paths = []
    task_metrics = []
    for label in ('avenue', 'library'):
        relative = sources[label + 'VideoPath']
        source_probe = probe(args.ffprobe, asset(data, relative), 512, 320, 24, 121, 121 / 24)
        detail = run.task(label + 'UpscaleTaskId', 'Upscaling-' + label, {
            'projectId': sources['projectId'], 'taskType': 'Video', 'resourceClass': 'GPU',
            'workflowId': workflow[0]['id'], 'inputImagePath': relative,
            'stage': 'Campus-AI-Upscale-X2', 'maxRetries': 0,
            'parameters': {'workflowVersion': 'realesrgan-x2-video-v1',
                           'inputSlots': {'sourceVideo': relative},
                           'width': 1024, 'height': 640, 'frames': 121, 'fps': 24,
                           'duration': 121 / 24, 'provider': 'RealESRGANLocal',
                           'contentReview': 'NeedReview'}
        })
        video = run.result(detail, ('.mp4',))
        if video is None:
            raise RuntimeError('Upscale task lacks an available registered MP4 artifact')
        info = probe(args.ffprobe, asset(data, video['assetPath']), 1024, 640, 24, 121, 121 / 24)
        original_audio = any(item['codec_type'] == 'audio' for item in source_probe['streams'])
        output_audio = any(item['codec_type'] == 'audio' for item in info['streams'])
        if original_audio != output_audio:
            raise RuntimeError('Upscale changed source audio presence')
        output_paths.append(video['assetPath'])
        task_metrics.append(metrics(detail))
        run.save(**{label + 'UpscaledVideoPath': video['assetPath'], label + 'Probe': info,
                    'upscaleTaskMetrics': task_metrics})
    detail = run.task('deliveryTaskId', 'AssemblingEnhancedPreview', {
        'projectId': sources['projectId'], 'taskType': 'Concat', 'resourceClass': 'CPU',
        'stage': 'Campus-Upscale-Delivery', 'maxRetries': 0,
        'parameters': {'files': output_paths, 'outputName': 'campus_morning_10s_realesrgan_x2.mp4',
                       'targetDurationSeconds': 10, 'targetWidth': 1280, 'targetHeight': 720,
                       'targetFps': 30}
    })
    video = run.result(detail, ('.mp4',))
    if video is None:
        raise RuntimeError('Delivery task lacks an available MP4 artifact')
    output = asset(data, video['assetPath'])
    info = probe(args.ffprobe, output, 1280, 720, 30, 300, 10)
    subprocess.run([str(args.ffmpeg), '-v', 'error', '-i', str(output), '-f', 'null', '-'],
                   capture_output=True, check=True, timeout=120)
    for item in snapshot:
        if sha256(asset(data, item['assetPath'])) != item['sha256']:
            raise RuntimeError('An original file changed during enhancement')
    run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview',
             publicationStatus='Blocked', videoAssetPath=video['assetPath'],
             absoluteVideoPath=str(output), probe=info, deliveryMetrics=metrics(detail),
             originalFilesUnchanged=True)
    print(json.dumps({'video': str(output), 'deliveryTaskId': run.state['deliveryTaskId'],
                      'duration': 10, 'fps': 30, 'frames': 300}, ensure_ascii=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, default=Path(r'C:\install\AI\Data\CampusPreview20261018\run.json'))
    parser.add_argument('--report', type=Path, default=Path(r'C:\install\AI\Data\CampusUpscale20261018\run.json'))
    parser.add_argument('--base-url', default='http://127.0.0.1:18080')
    parser.add_argument('--ffprobe', type=Path, default=Path(r'C:\install\FFmpeg\bin\ffprobe.exe'))
    parser.add_argument('--ffmpeg', type=Path, default=Path(r'C:\install\FFmpeg\bin\ffmpeg.exe'))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(args.report.parent, '.campus-upscale.lock', 'Another campus enhancement run is active'):
        run = Acceptance(args.base_url, args.report)
        try:
            enhance(args, run)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(f'Enhancement {status}: {type(error).__name__}: {str(error)[:500]}', flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

"""Verify the real three-shot export and expose a local, reviewable preview.

This helper does not submit inference jobs or change business task states.
Run with the existing Qwen3TTS Python environment (numpy/soundfile installed).
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'DialogueThreeShot20261023'
FFMPEG = Path(r'C:\install\FFmpeg\bin\ffmpeg.exe')
FFPROBE = FFMPEG.with_name('ffprobe.exe')
PREVIEW = 'dialogue-three-shot-preview'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def media_path(value):
    """Resolve media only inside the actual controlled Data root."""
    path = Path(value)
    path = (path if path.is_absolute() else DATA / path).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError('Media must be a real file inside Data')
    return path


def relative_media(value):
    return media_path(value).relative_to(DATA.resolve()).as_posix()


def sha(path):
    with media_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def previous_media(run):
    if run.get('previousPath'):
        path = run['previousPath']
        expected = run.get('previousSha256')
    else:
        old = read_json(DATA / 'DialoguePilot20261023' / 'run.json')
        path, expected = old['finalPath'], old['finalSha256']
    if expected and sha(path) != expected:
        raise RuntimeError('The previous pilot changed')
    return path


def timeline_and_shots(run):
    timeline = run.get('timeline')
    if timeline is None:
        timeline = read_json(FOLDER / 'audio' / 'timeline.json')
    if not isinstance(timeline, list) or len(timeline) != 4:
        raise RuntimeError('Exactly four dialogue lines are required')
    expected = [('female', '哟，约会回来了？'), ('male', '哼，要你管。'),
                ('female', '好啦，不逗你了。'), ('male', '这还差不多。')]
    cursor = 0.0
    for item, (role, text) in zip(timeline, expected):
        start, end = float(item['startSeconds']), float(item['endSeconds'])
        if item['role'] != role or item['text'] != text or not cursor <= start < end <= 10:
            raise RuntimeError('Dialogue role/text/timing does not match the approved script')
        cursor = end
    shots = run['shots']
    if not isinstance(shots, list) or len(shots) != 3:
        raise RuntimeError('Exactly three shots are required')
    cursor = 0.0
    for shot in shots:
        start, end = float(shot['startSeconds']), float(shot['endSeconds'])
        if abs(start - cursor) > 1 / 240 or end <= start:
            raise RuntimeError('Shot timeline has a gap or overlap')
        cursor = end
    if abs(cursor - 10) > 1 / 240:
        raise RuntimeError('The three-shot timeline must cover exactly ten seconds')
    return timeline, shots


def mix_path(run):
    value = run.get('mixPath') or run.get('audioMixPath')
    if not value:
        audio = read_json(FOLDER / 'audio' / 'run.json')
        value = audio.get('mixPath') or audio.get('finalMixPath')
    if not value:
        raise RuntimeError('Record the exact final mix WAV in run.json mixPath')
    path = media_path(value)
    expected = run.get('mixSha256')
    if expected and sha(path) != expected:
        raise RuntimeError('The selected dialogue mix changed')
    return path


def correlation(actual, expected):
    if len(actual) != len(expected) or len(actual) < 2:
        raise RuntimeError('Audio length mismatch inside a checked speech segment')
    if np.std(expected) < 1e-7 or np.std(actual) < 1e-7:
        raise RuntimeError('Expected audible speech is missing or silent')
    value = float(np.corrcoef(actual, expected)[0, 1])
    if not np.isfinite(value):
        raise RuntimeError('Audio correlation is not finite')
    return value


def verify(run):
    report = {'status': 'Failed', 'scope': 'Technical export/audio integrity only',
              'contentStatus': 'NeedReview', 'publicationStatus': 'Blocked'}
    try:
        path = media_path(run['finalPath'])
        digest = sha(path)
        if digest != run['finalSha256']:
            raise RuntimeError('Final export SHA256 does not match the recorded file')
        timeline, shots = timeline_and_shots(run)
        probe = json.loads(subprocess.check_output([
            str(FFPROBE), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)
        ], encoding='utf-8'))
        write_json(FOLDER / 'final-probe.json', probe)
        video = next(item for item in probe['streams'] if item['codec_type'] == 'video')
        audio_stream = next(item for item in probe['streams'] if item['codec_type'] == 'audio')
        if (video['width'], video['height'], Fraction(video['avg_frame_rate'])) != (1280, 720, Fraction(24)):
            raise RuntimeError('Expected a 1280x720, 24 FPS delivery')
        if abs(float(video.get('duration', probe['format']['duration'])) - 10) > 1 / 240:
            raise RuntimeError('Video duration is not exactly ten seconds')
        hashes = subprocess.check_output([
            str(FFMPEG), '-v', 'error', '-xerror', '-i', str(path),
            '-map', '0:v:0', '-f', 'framemd5', '-'
        ], encoding='utf-8')
        (FOLDER / 'final-framemd5.txt').write_text(hashes, encoding='utf-8')
        frame_rows = [line for line in hashes.splitlines() if line and not line.startswith('#')]
        if len(frame_rows) != 240:
            raise RuntimeError(f'Full decode produced {len(frame_rows)} frames instead of 240')
        mix = mix_path(run)
        expected_audio, sr = sf.read(mix, dtype='float32')
        if expected_audio.ndim != 1 or len(expected_audio) != sr * 10:
            raise RuntimeError('The selected mix must be a mono, exact ten-second WAV')
        raw = subprocess.check_output([
            str(FFMPEG), '-v', 'error', '-xerror', '-i', str(path),
            '-map', '0:a:0', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'
        ])
        decoded = np.frombuffer(raw, dtype='<f4')
        if len(decoded) < len(expected_audio):
            raise RuntimeError('The decoded audio is shorter than the complete selected mix')
        complete = correlation(decoded[:len(expected_audio)], expected_audio)
        if complete < .995:
            raise RuntimeError(f'Complete dialogue mix correlation is too low: {complete}')
        lines = []
        for item in timeline:
            start, end = round(item['startSeconds'] * sr), round(item['endSeconds'] * sr)
            value = correlation(decoded[start:end], expected_audio[start:end])
            if value < .985:
                raise RuntimeError(f'Dialogue line {item["index"]} correlation is too low: {value}')
            lines.append({'index': item['index'], 'role': item['role'], 'text': item['text'],
                          'correlation': value, 'missingSpeechSamples': max(0, end - len(decoded))})
        previous = previous_media(run)
        preserved = []
        before = FOLDER / 'preserved-before.json'
        if before.exists():
            for item in read_json(before):
                if sha(item['path']) != item['sha256']:
                    raise RuntimeError('A previously preserved artifact changed')
                preserved.append(item)
        shot_sources = []
        for shot in shots:
            source = shot.get('path') or shot.get('videoPath')
            if source:
                source_digest = sha(source)
                recorded = shot.get('sha256') or shot.get('videoSha256')
                if recorded and source_digest != recorded:
                    raise RuntimeError('A selected shot source changed')
                shot_sources.append({'index': shot.get('index'), 'path': relative_media(source), 'sha256': source_digest})
        report.update(status='Passed', finalPath=str(path), finalSha256=digest,
                      width=1280, height=720, fps=24, frames=240, durationSeconds=10,
                      decodedFrames=len(frame_rows),
                      uniqueDecodedHashes=len({line.split(',')[-1].strip() for line in frame_rows}),
                      audio={'codec': audio_stream['codec_name'], 'sampleRate': sr,
                             'expectedSamples': len(expected_audio), 'decodedSamples': len(decoded),
                             'completeMixCorrelation': complete, 'lines': lines},
                      mixPath=relative_media(mix), mixSha256=sha(mix),
                      previousPath=relative_media(previous), previousSha256=sha(previous),
                      preservedFiles=len(preserved), shotSources=shot_sources,
                      reviewedAt=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        report['error'] = str(exc)
        write_json(FOLDER / 'delivery-verification.json', report)
        raise
    write_json(FOLDER / 'delivery-verification.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


def verified(run):
    report = read_json(FOLDER / 'delivery-verification.json')
    if report.get('status') != 'Passed' or report.get('finalSha256') != sha(run['finalPath']):
        raise RuntimeError('Verify the actual final export before exposing it in the preview')
    return report


def preview(run):
    verified(run)
    timeline, shots = timeline_and_shots(run)
    poster = FOLDER / 'final-poster.jpg'
    subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-i', str(media_path(run['finalPath'])),
                    '-frames:v', '1', str(poster)], check=True)
    labels = ['含笑打趣', '佯装不服', '温柔让步', '轻松满意']
    manifest = {'finalPath': relative_media(run['finalPath']), 'posterPath': relative_media(poster),
                'previousPath': relative_media(previous_media(run)),
                'mixPath': relative_media(mix_path(run)),
                'durationSeconds': 10, 'technicalStatus': 'Passed', 'contentStatus': 'NeedReview',
                'shots': [{'index': item.get('index', i + 1),
                           'label': item.get('label') or item.get('title') or f'镜头 {i + 1}',
                           'startSeconds': item['startSeconds'], 'endSeconds': item['endSeconds']}
                          for i, item in enumerate(shots)],
                'lines': [dict(item, emotionLabel=item.get('emotionLabel') or labels[i]) for i, item in enumerate(timeline)],
                'note': '同人物、同台词，先确定对白节奏，再生成三个镜头。请重点比较语气、眼神反应和口型。'}
    write_json(FOLDER / 'preview-manifest.json', manifest)
    write_json(ROOT / 'web' / 'public' / (PREVIEW + '.json'), manifest)
    for suffix in ['.html', '.json']:
        shutil.copy2(ROOT / 'web' / 'public' / (PREVIEW + suffix), ROOT / 'web' / 'dist' / (PREVIEW + suffix))
    print('http://127.0.0.1:18080/' + PREVIEW + '.html', flush=True)


def complete(run):
    """Record readiness only after the caller has saved actual browser evidence."""
    verified(run)
    browser = read_json(FOLDER / 'browser-final-playback.json')
    if (browser.get('status') != 'Passed' or browser.get('ended') is not True or
            browser.get('muted') is not False or browser.get('volumePercent') != 100 or
            abs(float(browser.get('duration', -1)) - 10) > .05):
        raise RuntimeError('Actual complete, unmuted browser playback evidence is required')
    # This is a local progress file, never a business database task-state override.
    run.update(stage='ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview',
               publicationStatus='Blocked', previewUrl='http://127.0.0.1:18080/' + PREVIEW + '.html',
               updatedAt=datetime.now(timezone.utc).isoformat())
    write_json(FOLDER / 'run.json', run)
    print('ReadyForUserPreview; content still requires human review', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['verify', 'preview', 'complete'], required=True)
    args = parser.parse_args()
    run = read_json(FOLDER / 'run.json')
    {'verify': verify, 'preview': preview, 'complete': complete}[args.stage](run)


if __name__ == '__main__':
    main()

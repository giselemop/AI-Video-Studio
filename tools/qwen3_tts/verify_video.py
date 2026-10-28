"""Check the actual final video, source preservation and Qwen audio correspondence."""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'Qwen3Video20261022'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    run = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    if run['stage'] not in ['AwaitingPlaybackInspection', 'ReadyForUserPreview']: raise RuntimeError('A completed actual assembly is required')
    video = DATA / run['finalVideoPath']
    if digest(video) != run['finalVideoSha256']: raise RuntimeError('Final video changed')
    preserved = []
    for source in run['assemblySources']:
        if digest(DATA / source['path']) != source['sha256']: raise RuntimeError('A newly generated source changed')
        preserved.append({'taskId': source['taskId'], 'sha256': source['sha256'], 'status': 'Passed'})
    for number in [1, 2]:
        graph = json.loads((FOLDER / f'shot-{number:02}/execution-graph.json').read_text(encoding='utf-8'))
        condition = graph['6']['inputs']
        if [condition['width'], condition['height']] != run['generationCanvas'] or condition['length'] != 124:
            raise RuntimeError('Source generation canvas or length changed')
        if run['profile'] == 'native1080':
            crop = graph['16']['inputs']
            if (crop['width'], crop['height'], crop['x'], crop['y']) != (1920, 1080, 0, 4):
                raise RuntimeError('Native1080 source did not use the fixed four-row crop')
    if digest(DATA / run['sourceAudioPath']) != run['sourceAudioSha256']: raise RuntimeError('Original Qwen WAV changed')
    actual = FOLDER / 'final-audio.f32'
    expected = FOLDER / 'reference-fitted-audio.f32'
    complete = FOLDER / 'complete-fitted-audio.f32'
    for input_path, output_path, filters in [
        (video, actual, 'atrim=duration=10,asetpts=PTS-STARTPTS'),
        (DATA / run['sourceAudioPath'], complete, 'atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,asetpts=N/SR/TB'),
        # Match the production mixer's sample-clock normalization after padding.
        # atempo can leave its final packet PTS slightly ahead of the sample count.
        (DATA / run['sourceAudioPath'], expected, 'atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,apad=whole_dur=10,asetpts=N/SR/TB,atrim=duration=10')
    ]:
        if not output_path.exists():
            subprocess.run([FFMPEG, '-v', 'error', '-i', str(input_path), '-vn', '-af', filters, '-ar', '24000', '-ac', '1', '-f', 'f32le', '-n', str(output_path)], check=True)
    a = np.fromfile(actual, dtype='<f4'); b = np.fromfile(expected, dtype='<f4')
    if len(a) != 240000 or len(b) != 240000 or not np.isfinite(a).all(): raise RuntimeError('Decoded audio duration or values differ')
    full = np.fromfile(complete, dtype='<f4')
    if not 0 < len(full) <= 240000 or not np.isfinite(full).all():
        raise RuntimeError('The complete fitted narration does not fit in the ten-second video')
    correlation = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(correlation) or correlation < .97:
        raise RuntimeError('Final audio does not sufficiently match the complete fitted Qwen source: ' + str(correlation))
    audio = {'status': 'Passed', 'sampleRate': 24000, 'samples': len(a), 'durationSeconds': 10,
        'correlationWithFittedQwen': correlation, 'tempo': 1.32, 'startSeconds': .12,
        'completeFittedSamples': len(full), 'completeFittedDurationSeconds': len(full) / 24000,
        'narrationSamplesTruncated': 0,
        'peakDb': float(20*np.log10(max(np.max(np.abs(a)), 1e-9))), 'rmsDb': float(20*np.log10(max(np.sqrt(np.mean(a*a)), 1e-9))),
        'sourceAudioSha256': run['sourceAudioSha256'], 'contentReview': 'NeedReview'}
    (FOLDER / 'audio-correspondence.json').write_text(json.dumps(audio, indent=2), encoding='utf-8')
    hashes = subprocess.check_output([FFMPEG, '-v', 'error', '-i', str(video), '-map', '0:v:0', '-f', 'framemd5', '-'], encoding='utf-8')
    (FOLDER / 'final-framemd5.txt').write_text(hashes, encoding='utf-8')
    frames = [line.rsplit(',', 1)[-1].strip() for line in hashes.splitlines() if line and not line.startswith('#')]
    if len(frames) != 240: raise RuntimeError('Final decoded frame count differs')
    contact = Image.new('RGB', (1440, 540), '#111111')
    for i, seconds in enumerate([0, 2.4, 4.8, 5.3, 7.4, 9.7]):
        image_path = FOLDER / f'final-{seconds:04.1f}.png'
        if not image_path.exists(): subprocess.run([FFMPEG, '-v', 'error', '-ss', str(seconds), '-i', str(video), '-frames:v', '1', '-n', str(image_path)], check=True)
        image = Image.open(image_path).convert('RGB'); image.thumbnail((480, 270))
        x,y=(i%3)*480,(i//3)*270;contact.paste(image,(x,y));ImageDraw.Draw(contact).text((x+8,y+8),f'{seconds:.1f} seconds',fill='white')
    contact.save(FOLDER / 'final-contact.png')
    report = {'status': 'Passed', 'decodedFrames': len(frames), 'uniqueDecodedFrameHashes': len(set(frames)), 'sources': preserved,
        'originalQwenAudioPreserved': True, 'finalVideoSha256': digest(video), 'contentReview': 'NeedReview'}
    (FOLDER / 'preservation-and-frames.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'audio': audio, 'frames': len(frames), 'uniqueFrameHashes': len(set(frames))}), flush=True)


if __name__ == '__main__': main()

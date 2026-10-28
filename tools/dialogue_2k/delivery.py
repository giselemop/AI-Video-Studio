"""Actual media verification and review page; never submits inference tasks."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import API, DATA, FOLDER, ROOT, Run, media, preserved, read, sha, write

FFMPEG = Path(r'C:\install\FFmpeg\bin\ffmpeg.exe')
FFPROBE = FFMPEG.with_name('ffprobe.exe')


def probe(path):
    return json.loads(subprocess.check_output([str(FFPROBE), '-v', 'error', '-show_streams', '-show_format',
                                              '-of', 'json', str(path)], encoding='utf-8'))


def frame_hashes(path, target):
    raw = subprocess.check_output([str(FFMPEG), '-v', 'error', '-xerror', '-i', str(path),
                                   '-map', '0:v:0', '-f', 'framemd5', '-'], encoding='utf-8')
    target.write_text(raw, encoding='utf-8')
    return [line.split(',')[-1].strip() for line in raw.splitlines() if line and not line.startswith('#')]


def audio_packets(path):
    return subprocess.check_output([str(FFMPEG), '-v', 'error', '-i', str(path), '-map', '0:a:0',
                                    '-c:a', 'copy', '-f', 'adts', '-'])


def audio_pcm(path):
    return subprocess.check_output([str(FFMPEG), '-v', 'error', '-i', str(path), '-map', '0:a:0',
                                    '-ac', '1', '-ar', '24000', '-f', 'f32le', '-'])


def verify(run):
    preserved(run)
    path, original = media(run.state['finalPath']), media(run.state['originalPath'])
    if sha(path) != run.state['finalSha256']:
        raise RuntimeError('Final artifact SHA256 changed')
    data = probe(path)
    write(FOLDER / 'final-probe.json', data)
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    if (video['width'], video['height'], Fraction(video['avg_frame_rate']), int(video['nb_frames'])) != (2560, 1440, Fraction(24), 240):
        raise RuntimeError('Final must be real 2560x1440, 24 FPS, 240 frames')
    if abs(float(video.get('duration', data['format']['duration'])) - 10) > .001:
        raise RuntimeError('Final video duration is not exactly ten seconds')
    hashes = frame_hashes(path, FOLDER / 'final-framemd5.txt')
    if len(hashes) != 240 or len(set(hashes)) != 240:
        raise RuntimeError('Missing or repeated decoded output frames')
    packets_before, packets_after = audio_packets(original), audio_packets(path)
    if packets_before != packets_after:
        raise RuntimeError('Original AAC packets were not preserved')
    pcm_before, pcm_after = audio_pcm(original), audio_pcm(path)
    if pcm_before != pcm_after:
        raise RuntimeError('Decoded original audio differs')
    decoded = np.frombuffer(pcm_after, dtype='<f4')
    lines = []
    for line in run.state['timeline']:
        start, end = round(line['startSeconds'] * 24000), round(line['endSeconds'] * 24000)
        speech = decoded[start:end]
        if len(speech) != end-start or np.sqrt(np.mean(speech**2)) < 1e-5:
            raise RuntimeError('Missing dialogue audio')
        lines.append(dict(index=line['index'], role=line['role'], text=line['text'],
                          startSeconds=line['startSeconds'], endSeconds=line['endSeconds'],
                          decodedSamples=len(speech), missingSpeechSamples=0,
                          sameOriginalPcm=True, pcmSha256=hashlib.sha256(speech.tobytes()).hexdigest()))
    shots = []
    for index, source in enumerate(run.state['shots'], 1):
        attempt = run.state[f'shot{index}SelectedAttempt']
        field = f'shot{index}Attempt{attempt}TaskId'
        detail = read(FOLDER / (field + '-result.json'))
        if detail['task']['status'] != 'Succeeded':
            raise RuntimeError('A selected restoration task did not succeed')
        receipt = next((media(r['assetPath']) for r in detail['results']
                        if r.get('available') and r.get('assetPath', '').endswith('.json')), None)
        if receipt is None:
            raise RuntimeError('Missing actual GPU inference receipt')
        inference = read(receipt)
        expected_frames = source['frames']
        if (inference['width'], inference['height'], inference['frames'], inference['fps']) != (2560, 1440, expected_frames, 24):
            raise RuntimeError('Per-shot receipt does not match requested QHD output')
        if inference['sourceSha256'] != source['sha256'] or inference['outputProfile'] != 'qhd1440':
            raise RuntimeError('Restoration source/profile mismatch')
        actual_path = media(run.state[f'shot{index}Attempt{attempt}Path'])
        shot_hashes = frame_hashes(actual_path, FOLDER / f'shot-{index}-framemd5.txt')
        if len(shot_hashes) != expected_frames:
            raise RuntimeError('Per-shot decoded frame count mismatch')
        shots.append(dict(index=index, taskId=run.state[field], frames=expected_frames,
                          sourceSha256=source['sha256'], path=str(actual_path.relative_to(DATA)).replace('\\', '/'),
                          receiptPath=str(receipt.relative_to(DATA)).replace('\\', '/'), inference=inference))
    samples = [json.loads(line) for line in (FOLDER / 'resources.jsonl').read_text(encoding='utf-8').splitlines() if line]
    gpu = [s['gpu'][0] for s in samples if s.get('gpu')]
    ram = [s['availableRamMiB'] for s in samples]
    report = dict(status='Passed', scope='Technical export, exact original audio and per-shot inference provenance; content requires review',
        finalPath=run.state['finalPath'], finalSha256=run.state['finalSha256'], originalPath=run.state['originalPath'],
        originalSha256=run.state['originalSha256'], width=2560, height=1440, fps=24, frames=240,
        durationSeconds=10, decodedFrames=len(hashes), uniqueDecodedHashes=len(set(hashes)),
        audioPacketsIdentical=True, aacSha256=hashlib.sha256(packets_after).hexdigest(),
        decodedPcmIdentical=True, pcmSha256=hashlib.sha256(pcm_after).hexdigest(), decodedAudioSamples=len(decoded),
        dialogue=lines, shots=shots, preservedFiles=len(run.state['preserved']),
        sampledPeakDeviceVramMiB=max(gpu) if gpu else None, sampledMinAvailableRamMiB=min(ram) if ram else None,
        resourceSamples=len(samples), checkedAt=datetime.now(timezone.utc).isoformat())
    task_rows = []
    for field, task_id in run.state.items():
        result_file = FOLDER / (field + '-result.json')
        if field.endswith('TaskId') and type(task_id) is int and result_file.is_file():
            task = read(result_file)['task']
            task_rows.append({key: task.get(key) for key in ['id', 'taskType', 'resourceClass', 'status', 'startedAt', 'finishedAt', 'durationMs']})
    events = []
    for task in task_rows:
        if task['resourceClass'] == 'GPU' and task['startedAt'] and task['finishedAt']:
            events += [(task['startedAt'], 1), (task['finishedAt'], -1)]
    current, maximum = 0, 0
    for _, delta in sorted(events, key=lambda row: (row[0], row[1])):
        current += delta
        maximum = max(maximum, current)
    if maximum > 1 or any(task['status'] != 'Succeeded' for task in task_rows):
        raise RuntimeError('Actual task status or GPU concurrency did not meet the run contract')
    summary = dict(branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, encoding='utf-8').strip(),
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, encoding='utf-8').strip(), tasks=task_rows,
        maxActualGpuConcurrency=maximum, gpuTaskMilliseconds=sum(t['durationMs'] or 0 for t in task_rows if t['resourceClass']=='GPU'),
        cpuTaskMilliseconds=sum(t['durationMs'] or 0 for t in task_rows if t['resourceClass']=='CPU'),
        originalAudioPacketsIdentical=True, originalDecodedPcmIdentical=True, preservedSources=run.state['preserved'])
    write(FOLDER / 'execution-summary.json', summary)
    write(FOLDER / 'verification.json', report)
    run.save('AwaitingBrowserPlayback', technicalStatus='Passed')
    print(json.dumps({k: report[k] for k in ['status', 'width', 'height', 'frames', 'durationSeconds',
        'audioPacketsIdentical', 'decodedPcmIdentical', 'sampledPeakDeviceVramMiB']}, ensure_ascii=False), flush=True)


def preview(run):
    report = read(FOLDER / 'verification.json')
    comparison = read(FOLDER / 'comparison/inspection.json')
    if report['status'] != 'Passed' or report['finalSha256'] != sha(media(run.state['finalPath'])):
        raise RuntimeError('Verify the current real artifact before exposing a preview')
    if comparison['afterSha256'] != report['finalSha256'] or comparison['beforeSha256'] != run.state['originalSha256']:
        raise RuntimeError('Actual before/after comparison is missing or stale')
    manifest = dict(originalPath=run.state['originalPath'], finalPath=run.state['finalPath'],
        facesPath='Dialogue2KSeedVR220261024/comparison/faces-before-after.jpg',
        lines=run.state['timeline'], shots=run.state['shots'], technicalStatus='Passed',
        contentStatus='NeedReview', durationSeconds=10, width=2560, height=1440, fps=24,
        audioPacketsIdentical=True, finalSha256=run.state['finalSha256'])
    for folder in [ROOT / 'web/public', ROOT / 'web/dist']:
        write(folder / 'dialogue-2k-compare.json', manifest)
    shutil.copy2(ROOT / 'web/public/dialogue-2k-compare.html', ROOT / 'web/dist/dialogue-2k-compare.html')
    write(FOLDER / 'preview-manifest.json', manifest)
    run.save(previewUrl='http://127.0.0.1:18080/dialogue-2k-compare.html')
    print(run.state['previewUrl'], flush=True)


def complete(run):
    evidence = read(FOLDER / 'browser-final-playback.json')
    if evidence.get('status') != 'Passed' or evidence.get('finalSha256') != run.state['finalSha256']:
        raise RuntimeError('Actual full browser playback evidence is required')
    verification = read(FOLDER / 'verification.json')
    if verification['status'] != 'Passed':
        raise RuntimeError('Technical verification is required')
    preserved(run)
    run.save('ReadyForUserPreview', technicalStatus='Passed', contentStatus='NeedReview', publicationStatus='Blocked')
    print('ReadyForUserPreview', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=['verify', 'preview', 'complete'])
    args = parser.parse_args()
    run = Run(API, FOLDER / 'run.json')
    if args.stage == 'verify': verify(run)
    elif args.stage == 'preview': preview(run)
    else: complete(run)


if __name__ == '__main__':
    main()

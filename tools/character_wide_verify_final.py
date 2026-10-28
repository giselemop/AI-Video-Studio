"""Evidence for the real 15-second cutaway edit; content review stays separate."""
import json
import re
import subprocess
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageStat
from character_wide_cutaway import Cutaway, ROOT, DATA, OUT, sha, write
from character_wide_verify import FFMPEG, FFPROBE, task

REPORT = OUT / 'final-checks.json'
EVIDENCE = OUT / 'final'

def run(args, timeout=180):
    result = subprocess.run([str(x) for x in args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[:2500])
    return result.stdout

def probe(path):
    return json.loads(run([FFPROBE, '-v', 'error', '-count_frames', '-show_streams',
                           '-show_format', '-of', 'json', path]))

def audio_hash(path):
    return run([FFMPEG, '-v', 'error', '-i', path, '-map', '0:a:0', '-c:a', 'copy',
                '-f', 'hash', '-hash', 'sha256', '-']).decode('ascii').strip()

def frames(path, indices, name):
    dest = EVIDENCE / name
    dest.mkdir(parents=True, exist_ok=True)
    files = [dest / ('frame-%02d.png' % (i + 1)) for i in range(len(indices))]
    if any(x.exists() for x in files):
        if not all(x.exists() for x in files):
            raise RuntimeError('Partial frame evidence must be inspected; it will not be overwritten')
    else:
        selection = '+'.join('eq(n,%d)' % n for n in indices).replace(',', r'\,')
        run([FFMPEG, '-v', 'error', '-i', path, '-vf', 'select=' + selection,
             '-fps_mode', 'passthrough', '-an', '-n', dest / 'frame-%02d.png'])
    return dict(zip(indices, files))

def mae(left, right):
    with Image.open(left) as a, Image.open(right) as b:
        a, b = a.convert('RGB'), b.convert('RGB')
        if a.size != b.size:
            raise RuntimeError('Frame sizes differ')
        return round(sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3, 3)

def main():
    p = Cutaway()
    s = p.state
    p.preserve()
    EVIDENCE.mkdir(exist_ok=True)
    e = s['editTasks']['final']
    original = DATA / s['sourceVideoPath']
    final = DATA / e['assetPath']
    wide = DATA / s['video']['assetPath']
    report = dict(status='Running', taskId=e['id'], checks=[], contentReview='NeedReview',
                  publication='Blocked', cutFrames=[s['cutStartFrame'], s['cutEndFrame']])
    def check(name, ok, detail=None):
        item = dict(name=name, status='Passed' if ok else 'Failed')
        if detail is not None:
            item['detail'] = detail
        report['checks'].append(item)
        if not ok:
            report['status'] = 'Failed'
            write(REPORT, report)
            raise AssertionError(name + ': ' + str(detail))

    check('all five queued edits and their saved outputs exist and match',
          all(x.get('status') == 'Succeeded' and sha(DATA / x['assetPath']) == x['sha256']
              and task(x['id'])['status'] == 'Succeeded' for x in s['editTasks'].values())
          and set(s['editTasks']) == {'head', 'cut', 'tail', 'picture', 'final'})
    check('original and cutaway video preserved', sha(original) == s['sourceVideoSha256']
          and sha(wide) == s['video']['sha256'])
    check('cutaway video provenance and preview inspection passed',
          json.loads((OUT / 'video-checks.json').read_text(encoding='utf-8'))['status'] == 'Passed'
          and s['video']['inspection']['decision'] == 'Passed')

    old_probe, new_probe = probe(original), probe(final)
    write(EVIDENCE / 'original-ffprobe.json', old_probe)
    write(EVIDENCE / 'final-ffprobe.json', new_probe)
    def info(data):
        v = next(x for x in data['streams'] if x['codec_type'] == 'video')
        a = next(x for x in data['streams'] if x['codec_type'] == 'audio')
        return dict(width=v['width'], height=v['height'], fps=v['avg_frame_rate'],
                    frames=int(v['nb_read_frames']), audio=a['codec_name'],
                    duration=float(data['format']['duration']))
    oi, ni = info(old_probe), info(new_probe)
    report['originalMedia'], report['finalMedia'] = oi, ni
    check('both videos are 15s at 864x480, 24fps and 360 frames with AAC',
          all(x['width'] == 864 and x['height'] == 480 and x['fps'] == '24/1'
              and x['frames'] == 360 and x['audio'] == 'aac'
              and abs(x['duration'] - 15) < 0.05 for x in [oi, ni]), [oi, ni])
    run([FFMPEG, '-v', 'error', '-i', final, '-f', 'null', '-'])
    check('full final video and audio decode', True)
    old_audio, new_audio = audio_hash(original), audio_hash(final)
    report['originalAudioSha256'], report['finalAudioSha256'] = old_audio, new_audio
    check('original AAC soundtrack packets are unchanged', old_audio == new_audio, old_audio)

    indices = [0, 24, 160, 209, 210, 220, 245, 246, 300, 359]
    old_frames = frames(original, indices, 'original-frames')
    final_frames = frames(final, indices, 'final-frames')
    wide_frames = frames(wide, [0, 10, 35], 'wide-frames')
    outside = {str(n): mae(old_frames[n], final_frames[n])
               for n in [0, 24, 160, 209, 246, 300, 359]}
    inside = {str(n): mae(wide_frames[n - 210], final_frames[n])
              for n in [210, 220, 245]}
    report['decodedRgbMeanAbsoluteDifference'] = dict(outsideCut=outside, insideCut=inside)
    check('sampled frames follow original outside cut and wide source inside cut',
          max([*outside.values(), *inside.values()]) < 8, report['decodedRgbMeanAbsoluteDifference'])

    srt = (DATA / 'CharacterPlotContinuation20261028' / 'window-narration.srt').read_text(encoding='utf-8')
    stamps = re.findall(r'(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)', srt)
    def seconds(group):
        h, m, sec, ms = map(int, group)
        return 3600*h + 60*m + sec + ms/1000
    intervals = [[seconds(row[:4]), seconds(row[4:])] for row in stamps]
    check('the inserted cut does not cover any original subtitle interval',
          len(intervals) == 3 and all(b <= 8.75 or a >= 10.25 for a, b in intervals),
          intervals)

    media = p.s.get(p.base + '/api/media', params={'assetPath': e['assetPath']},
                    headers={'Range': 'bytes=0-1023'}, timeout=30)
    with final.open('rb') as f:
        expected = f.read(1024)
    check('media endpoint serves correct seekable bytes',
          media.status_code == 206 and media.content == expected, media.status_code)

    sheet = Image.new('RGB', (1728, 798), '#101827')
    draw = ImageDraw.Draw(sheet)
    for i, n in enumerate(indices):
        with Image.open(final_frames[n]) as im:
            sheet.paste(im.resize((432, 240)), ((i % 4) * 432, (i // 4) * 266))
        draw.text(((i % 4) * 432 + 8, (i // 4) * 266 + 244),
                  'final frame %d | %.3fs' % (n, n / 24), fill='white')
    sheet.save(EVIDENCE / 'contact-sheet.jpg', quality=95)
    p.preserve()
    report.update(status='Passed', sha256=e['sha256'],
                  originalSha256=s['sourceVideoSha256'], wideSha256=s['video']['sha256'])
    write(REPORT, report)
    print('%d final technical checks Passed. Visual and user review remain separate.' % len(report['checks']))

if __name__ == '__main__':
    main()

"""Compare actual decoded motion frames; never turns motion magnitude into approval."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

import numpy as np
from PIL import Image, ImageDraw, ImageFont


DATA = Path(r'C:\install\AI\Data')
FOLDER = DATA / 'H3Motion20261019'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'


def frame(path, seconds):
    output = subprocess.run([FFMPEG, '-v', 'error', '-ss', str(seconds), '-i', str(path),
                             '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                            capture_output=True, check=True, timeout=60)
    return Image.open(io.BytesIO(output.stdout)).convert('RGB')


def motion(path):
    decoded = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-an', '-vf',
                              'scale=344:192:flags=area,format=gray', '-f', 'rawvideo', '-'],
                             capture_output=True, check=True, timeout=60)
    values = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(-1, 192, 344).astype(np.float32)
    checksums = subprocess.run([FFMPEG, '-v', 'error', '-i', str(path), '-map', '0:v:0',
                                '-f', 'framemd5', '-'], capture_output=True, text=True, check=True, timeout=60)
    hashes = [line.rsplit(',', 1)[-1].strip() for line in checksums.stdout.splitlines() if line and not line.startswith('#')]
    return {
        'frameCount': len(hashes), 'uniqueDecodedFrames': len(set(hashes)),
        'adjacentMeanAbsoluteLumaChange': round(float(np.abs(np.diff(values, axis=0)).mean()), 4),
        'frame12To108MeanAbsoluteLumaChange': round(float(np.abs(values[108] - values[12]).mean()), 4),
        'measurement': '8-bit grayscale at 344x192; image change is not a motion-quality or perceptual score.'
    }


def main():
    state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    if state.get('stage') != 'ReadyForUserPreview' or state.get('technicalStatus') != 'Passed':
        raise RuntimeError('The new native768 video must finish its technical checks before review')
    paths = {'before': DATA / state['baselineVideoPath'], 'after': DATA / state['videoPath']}
    fingerprints = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()}
    if fingerprints['before'] != state['baselineVideoSha256'] or fingerprints['after'] != state['videoSha256']:
        raise RuntimeError('An existing video changed; preserved')
    contact = Image.new('RGB', (1376, 1278), '#10141c')
    draw = ImageDraw.Draw(contact)
    font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 24)
    for row, seconds in enumerate((0.5, 2.5, 4.5)):
        for col, key in enumerate(('before', 'after')):
            still = frame(paths[key], seconds)
            still.save(FOLDER / f'{key}-{seconds}s.png')
            contact.paste(still.resize((688, 384), Image.Resampling.LANCZOS), (col * 688, row * 426 + 42))
            title = '旧版：固定机位' if key == 'before' else '新版：前移与树枝运动'
            draw.text((col * 688 + 12, row * 426 + 5), f'{title} / {seconds}s', font=font, fill='#e9eef7')
    contact.save(FOLDER / 'motion-contact.png')
    diagnostics = {key: motion(path) for key, path in paths.items()}
    for key, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != fingerprints[key]:
            raise RuntimeError('Video changed while extracting diagnostic frames')
    url = 'http://127.0.0.1:18080/h3-motion-compare.html?' + urlencode({
        'before': state['baselineVideoPath'], 'after': state['videoPath']})
    result = {'comparisonUrl': url, 'videoSha256': fingerprints, 'diagnostics': diagnostics,
              'contactSheet': str(FOLDER / 'motion-contact.png'), 'contentStatus': 'NeedReview',
              'note': 'Use actual playback and human review to assess camera motion, branch motion and artifacts.'}
    (FOLDER / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

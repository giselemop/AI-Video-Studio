"""Extract matching diagnostic frames and native-detail crops from the H3 pair."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont


DATA = Path(r'C:\install\AI\Data')
FOLDER = DATA / 'H3Quality20261018'
FFMPEG = r'C:\install\FFmpeg\bin\ffmpeg.exe'


def frame(path, seconds):
    result = subprocess.run([FFMPEG, '-v', 'error', '-ss', str(seconds), '-i', str(path),
                             '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                            capture_output=True, check=True, timeout=60)
    return Image.open(io.BytesIO(result.stdout)).convert('RGB')


def main():
    state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    if state.get('technicalStatus') != 'Passed' or state.get('stage') != 'ReadyForUserPreview':
        raise RuntimeError('Both videos must finish and pass technical probes before comparison')
    videos = {key: DATA / state[key + 'VideoPath'] for key in ('baseline480', 'quality768')}
    source_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in videos.items()}
    font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 24)
    times = (0.5, 2.5, 4.5)
    # Only diagnostic images are resized. Original videos are never rewritten.
    contact = Image.new('RGB', (1376, 3 * (384 + 42)), '#10141c')
    draw = ImageDraw.Draw(contact)
    crops = Image.new('RGB', (1120, 3 * (420 + 42)), '#10141c')
    crop_draw = ImageDraw.Draw(crops)
    for row, seconds in enumerate(times):
        y = row * 426
        crop_y = row * 462
        for col, key in enumerate(('baseline480', 'quality768')):
            native = frame(videos[key], seconds)
            native.save(FOLDER / f'{key}-{seconds}s.png')
            aligned = native.resize((1376, 768), Image.Resampling.LANCZOS)
            contact.paste(aligned.resize((688, 384), Image.Resampling.LANCZOS), (col * 688, y + 42))
            label = 'H3 480p 放大' if col == 0 else 'H3 原生768p'
            draw.text((col * 688 + 12, y + 5), f'{label} / {seconds}s', font=font, fill='#e9eef7')
            # Same facade rectangle in the common 1376x768 coordinate system.
            crops.paste(aligned.crop((160, 160, 720, 580)), (col * 560, crop_y + 42))
            crop_draw.text((col * 560 + 12, crop_y + 5), f'{label} / {seconds}s', font=font, fill='#e9eef7')
    contact.save(FOLDER / 'comparison-contact.png')
    crops.save(FOLDER / 'comparison-crops.png')
    for key, path in videos.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[key]:
            raise RuntimeError('Source video changed while preparing diagnostic frames')
    url = 'http://127.0.0.1:18080/h3-quality-compare.html?' + urlencode({
        'before': state['baseline480VideoPath'], 'after': state['quality768VideoPath']})
    output = {'comparisonUrl': url, 'timesSeconds': times, 'videoSha256': source_hashes,
              'contactSheet': str(FOLDER / 'comparison-contact.png'),
              'detailCrops': str(FOLDER / 'comparison-crops.png'),
              'contentStatus': 'NeedReview', 'note': 'Diagnostic images only; no automatic perceptual quality score.'}
    (FOLDER / 'review.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'comparisonUrl': url, 'sourceHashesUnchanged': True}))


if __name__ == '__main__':
    main()

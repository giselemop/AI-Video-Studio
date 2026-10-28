"""Inspect real native1080 frames against the preserved native768 motion take."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont
from review_motion import frame, motion

DATA = Path(r'C:\install\AI\Data')
FOLDER = DATA / 'H3Native108020261019'


def main():
    global FOLDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=[1, 2, 3], default=1)
    attempt = parser.parse_args().attempt
    if attempt > 1:
        FOLDER = FOLDER / f'attempt-{attempt}'
    state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    if state.get('stage') != 'ReadyForUserPreview' or state.get('technicalStatus') != 'Passed':
        raise RuntimeError('The native1080 task must finish technical checks before review')
    paths = {'before': DATA / state['baselineVideoPath'], 'after': DATA / state['videoPath']}
    expected = {'before': state['baselineVideoSha256'], 'after': state['videoSha256']}
    for key, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[key]:
            raise RuntimeError('An existing comparison video changed; preserved')
    contact = Image.new('RGB', (1536, 1422), '#10141c')
    draw = ImageDraw.Draw(contact)
    font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 23)
    for row, seconds in enumerate((0.5, 2.5, 4.5)):
        for col, key in enumerate(('before', 'after')):
            still = frame(paths[key], seconds)
            still.save(FOLDER / f'{key}-{seconds}s.png')
            scaled = still.copy()
            scaled.thumbnail((768, 432), Image.Resampling.LANCZOS)
            contact.paste(scaled, (col * 768, row * 474 + 42))
            title = '768p旧运动版' if key == 'before' else '1080p原生实验'
            draw.text((col * 768 + 12, row * 474 + 5), f'{title} / {seconds}s', font=font, fill='#e9eef7')
    contact.save(FOLDER / 'native1080-contact.png')
    result = {
        'comparisonUrl': 'http://127.0.0.1:18080/h3-native1080-compare.html?' + urlencode({
            'before': state['baselineVideoPath'], 'after': state['videoPath']}),
        'videoSha256': expected, 'diagnostics': {key: motion(path) for key, path in paths.items()},
        'contactSheet': str(FOLDER / 'native1080-contact.png'), 'contentStatus': 'NeedReview',
        'note': 'Same reference/seed; resolution, motion wording and encoding changed. Decoded frame change is not a quality score. Review full motion, foliage consistency and architecture.'
    }
    for key, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[key]:
            raise RuntimeError('Video changed while extracting diagnostic frames')
    (FOLDER / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()

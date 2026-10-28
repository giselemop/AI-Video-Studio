"""Extract genuine before/after frames for the fixed-1080p reference/motion comparison."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont
from review_motion import frame, motion

DATA = Path(r'C:\install\AI\Data')
FOLDER = DATA / 'H3Refined108020261020'


def main():
    state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
    if state.get('stage') != 'ReadyForUserPreview' or state.get('technicalStatus') != 'Passed':
        raise RuntimeError('The refined1080 task has not finished its technical checks')
    paths = {'before': DATA / state['baselineVideoPath'], 'after': DATA / state['videoPath']}
    expected = {'before': state['baselineVideoSha256'], 'after': state['videoSha256']}
    for key, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[key]:
            raise RuntimeError('Comparison media fingerprint differs; preserved')
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
            title = '1080p原版1178' if key == 'before' else '1080p首帧与运动优化'
            draw.text((col * 768 + 12, row * 474 + 5), f'{title} / {seconds}s', font=font, fill='#e9eef7')
    contact.save(FOLDER / 'refined1080-contact.png')
    result = {
        'comparisonUrl': 'http://127.0.0.1:18080/h3-refined1080-compare.html?' + urlencode({
            'before': state['baselineVideoPath'], 'after': state['videoPath'],
            'firstBefore': state['sourceFirstFramePath'], 'firstAfter': state['firstFramePath']}),
        'videoSha256': expected, 'diagnostics': {key: motion(path) for key, path in paths.items()},
        'contactSheet': str(FOLDER / 'refined1080-contact.png'), 'contentStatus': 'NeedReview',
        'note': 'Both native1080/24fps/124frames/20steps, same video seed/model/encoding. First frame and motion prompt both changed. Pixel change is not a quality score.'}
    for key, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[key]:
            raise RuntimeError('Video changed during review')
    (FOLDER / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()

"""Recover a publicly displayed small source file only when its pinned Git hash matches."""
import hashlib
import itertools
import json
from pathlib import Path

lines = [
    '# coding: utf-8',
    '"""',
    'tools to measure elapsed time',
    '"""',
    'import time',
    'class Timer(object):',
    '    """A simple timer."""',
    '    def __init__(self):',
    '        self.total_time = 0.',
    '        self.calls = 0',
    '        self.start_time = 0.',
    '        self.diff = 0.',
    '    def tic(self):',
    '        # using time.time instead of time.clock because time time.clock',
    '        # does not normalize for multithreading',
    '        self.start_time = time.time()',
    '    def toc(self, average=True):',
    '        self.diff = time.time() - self.start_time',
    '        return self.diff',
    '    def clear(self):',
    '        self.start_time = 0.',
    '        self.diff = 0.',
]
expected = '3570fa45d3ff36376471b82a5b3c02efe46eed98'
positions = (1, 4, 5, 6, 7, 12, 16, 19, 22)
for blanks in itertools.product(range(3), repeat=len(positions)):
    if sum(blanks) not in (6, 7):
        continue
    expanded = []
    blank_map = dict(zip(positions, blanks))
    for i, line in enumerate(lines):
        expanded.extend([''] * blank_map.get(i, 0))
        expanded.append(line)
    expanded.extend([''] * blank_map.get(len(lines), 0))
    body = ('\n'.join(expanded) + '\n').encode()
    if hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() == expected:
        target = Path(r'C:\install\AI\LivePortraitPilot\official\src\utils\timer.py')
        target.write_bytes(body)
        receipt = Path(r'C:\install\AI\Data\VisualValidation20261024\acting-setup\download-source.json')
        manifest = json.loads(receipt.read_text())
        manifest['files'] = [x for x in manifest['files'] if x['path'] != str(target)]
        manifest['files'].append({'path': str(target), 'bytes': len(body), 'gitBlobSha': expected,
                                  'sha256': hashlib.sha256(body).hexdigest(),
                                  'url': 'https://github.com/KlingAIResearch/LivePortrait/blob/main/src/utils/timer.py',
                                  'transport': 'publicly displayed source recovered with exact pinned Git blob validation'})
        receipt.write_text(json.dumps(manifest, indent=2))
        print('Pinned official Timer recovered: ' + expected)
        break
else:
    raise RuntimeError('Displayed source formatting did not reproduce pinned Git blob; nothing installed')

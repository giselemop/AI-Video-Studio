"""Install the explicit H3 comparison workflows, preserving any differing files."""
import hashlib
import json
from pathlib import Path

from download_assets import download_lock
from run_local_acceptance import Acceptance


def main():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / 'config/appsettings.json').read_text(encoding='utf-8-sig'))
    target_root = Path(config['Paths']['Workflows'])
    target_root.mkdir(parents=True, exist_ok=True)
    files = ('minimax_h3_local_i2v_api.json', 'minimax_h3_local_768_i2v_api.json', 'h3_keyframe_upscale_api.json')
    source_root = root / 'tools/minimax'
    for name in files:
        source = source_root / name
        json.loads(source.read_text(encoding='utf-8'))
        target = target_root / name
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError('Existing workflow differs and was preserved: ' + name)
    with download_lock(target_root, '.h3-quality-prepare.lock', 'Another H3 quality preparation is active'):
        for name in files:
            source = source_root / name
            target = target_root / name
            if not target.exists():
                with target.open('xb') as output:
                    output.write(source.read_bytes())
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError('Workflow changed during preparation: ' + name)
            print(json.dumps({'workflow': name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
    report = Path(config['Paths']['Data']) / 'H3Quality20261018/run.json'
    run = Acceptance('http://127.0.0.1:18080', report)
    run.access()
    run.api('/api/minimax/local/register', {})
    scanned = run.api('/api/workflows/scan', {})
    print(json.dumps({'registered': True, 'scanned': scanned.get('scanned'), 'generationSubmissions': 0}))


if __name__ == '__main__':
    main()

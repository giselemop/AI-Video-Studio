"""Download the explicitly pinned SeedVR2 model data, preserving existing files."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import download, download_lock


def main():
    config = json.loads((ROOT / 'config/seedvr2.json').read_text(encoding='utf-8'))
    engine = Path(config['engineDirectory'])
    revision = subprocess.check_output(['git', '-C', str(engine), 'rev-parse', 'HEAD'], encoding='utf-8').strip()
    if revision != config['engineRevision']:
        raise RuntimeError('SeedVR2 engine revision differs; existing checkout preserved')
    subprocess.run(['git', '-C', str(engine), 'diff', '--quiet'], check=True)
    target = Path(config['modelDirectory'])
    target.mkdir(parents=True, exist_ok=True)
    with download_lock(target, '.seedvr-download.lock', 'Another SeedVR2 download is active'):
        for file in config['files']:
            asset = dict(file, target=file['file'], repository=config['repository'], revision=config['revision'])
            download(asset, target, workers=4, chunk_size=16*1024**2)
        receipt = dict(repository=config['repository'], revision=config['revision'], engineRevision=revision, files=config['files'])
        (target / 'deployment.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({'status':'Passed','modelDirectory':str(target),'engineRevision':revision}), flush=True)


if __name__ == '__main__': main()

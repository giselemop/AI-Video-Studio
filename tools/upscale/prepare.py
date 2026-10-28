"""Prepare pinned official Real-ESRGAN data in the existing ComfyUI environment."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import atomic_replace, download_lock


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    config = json.loads((ROOT / 'config/appsettings.json').read_text(encoding='utf-8-sig'))
    manifest = json.loads((ROOT / 'config/video-upscale-assets.json').read_text(encoding='utf-8-sig'))
    model = manifest['model']
    models = Path(config['Paths']['Models']).resolve()
    workflows = Path(config['Paths']['Workflows']).resolve()
    target = (models / model['target']).resolve()
    if not target.is_relative_to(models) or target.name != 'RealESRGAN_x2plus.pth':
        raise RuntimeError('The model must stay in the configured central model directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(models, '.realesrgan-x2-prepare.lock', 'Another upscale preparation is running'):
        if target.exists():
            if target.stat().st_size != model['size'] or digest(target) != model['sha256']:
                raise RuntimeError('Existing model differs from the pinned file; preserved')
        else:
            partial = target.with_name(target.name + '.part')
            if partial.exists():
                if partial.stat().st_size != model['size'] or digest(partial) != model['sha256']:
                    raise RuntimeError('Incomplete existing partial preserved; inspect before resuming')
            else:
                with requests.get(model['sourceUrl'], stream=True, timeout=(25, 90)) as response:
                    response.raise_for_status()
                    with partial.open('xb') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                if partial.stat().st_size != model['size'] or digest(partial) != model['sha256']:
                    raise RuntimeError('Downloaded model does not match the pinned size and SHA-256')
            atomic_replace(partial, target)
        source = ROOT / 'tools/upscale' / manifest['workflowFile']
        workflow = workflows / manifest['workflowFile']
        workflows.mkdir(parents=True, exist_ok=True)
        if workflow.exists():
            if workflow.read_bytes() != source.read_bytes():
                raise RuntimeError('Existing workflow differs; preserved')
        else:
            with workflow.open('xb') as output, source.open('rb') as incoming:
                shutil.copyfileobj(incoming, output)
        print(json.dumps({'model': target.name, 'sha256': digest(target), 'workflow': workflow.name,
                          'workflowSha256': digest(workflow), 'apiKeyRequired': False}))


if __name__ == '__main__':
    main()

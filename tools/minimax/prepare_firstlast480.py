"""Install one additive local first/last H3 graph and contract; never submit GPU work."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT.parent / 'Workflows'
NAME = 'minimax_h3_local_fl2v_480_api.json'


def main():
    graph = json.loads((ROOT / 'tools/minimax/minimax_h3_local_i2v_api.json').read_text(encoding='utf-8-sig'))
    graph['16'] = {'class_type': 'LoadImage', 'inputs': {'image': 'minimax_last_frame.png'}}
    graph['6']['inputs']['last_frame'] = ['16', 0]
    graph['15']['inputs']['filename_prefix'] = 'minimax_firstlast480/video'
    raw = json.dumps(graph, ensure_ascii=False, indent=2) + '\n'
    for folder in (ROOT / 'tools/minimax', WORKFLOWS):
        target = folder / NAME
        if target.exists() and target.read_text(encoding='utf-8-sig') != raw:
            raise RuntimeError('Existing different workflow preserved: ' + str(target))
        if not target.exists() or target.read_bytes() != raw.encode('utf-8'):
            target.write_bytes(raw.encode('utf-8'))
    sha = hashlib.sha256(raw.encode()).hexdigest()
    manifest = json.loads((ROOT / 'config/minimax-local-assets.json').read_text(encoding='utf-8-sig'))
    path = ROOT / 'config/workflow-contracts.json'
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    entry = {
        'id': 'minimax-h3-firstlast480-v1', 'version': 'minimax-h3-firstlast480-v1', 'fileName': NAME,
        'workflowType': 'ImageToVideo', 'productionEligible': False, 'experimental': True,
        'licenseStatus': 'LOCAL_ONLY_PENDING_REVIEW', 'taskTypes': ['ImageToVideo'],
        'modelFiles': [a['file'] for a in manifest['assets']],
        'modelSha256': {a['file']: a['sha256'] for a in manifest['assets']},
        'nodes': [
            {'role': 'model', 'nodeId': '1', 'classType': 'UnetLoaderGGUF', 'inputName': 'unet_name', 'required': True},
            {'role': 'positivePrompt', 'nodeId': '6', 'classType': 'MiniMaxH3ImageToVideo', 'inputName': 'prompt', 'required': True},
            {'role': 'seed', 'nodeId': '7', 'classType': 'RandomNoise', 'inputName': 'noise_seed', 'required': True},
            {'role': 'save', 'nodeId': '15', 'classType': 'SaveVideo', 'inputName': 'filename_prefix', 'required': True}],
        'slots': [{'role': role, 'nodeId': node, 'classType': 'LoadImage', 'inputName': 'image', 'required': True}
                  for role, node in [('firstFrame', '5'), ('lastFrame', '16')]],
        'media': {'defaultWidth': 864, 'defaultHeight': 480, 'allowedDimensions': [{'width': 864, 'height': 480}],
                  'outputFrames': [124], 'nativeFps': 24, 'allowedFps': [24], 'exactFrameCount': True,
                  'executionFrameOffset': 0, 'guideFrameOffset': 0, 'requiresGuide': False, 'preserveAudio': True},
        'notes': f'sha256={sha} | Pinned local H3 first/last-frame 480p experiment. Explicit node5 firstFrame and node16 lastFrame; exact 864x480 static inputs with SHA256, last target frame 123. Managed H3 admission and queue verify both inputs. No model replacement or production approval.'}
    existing = [e for e in document['contracts'] if e['id'] == entry['id']]
    if existing and existing != [entry]:
        raise RuntimeError('Existing different H3 contract preserved')
    if not existing:
        document['contracts'].append(entry)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'workflow': NAME, 'sha256': sha, 'contract': entry['id']}))


if __name__ == '__main__':
    main()

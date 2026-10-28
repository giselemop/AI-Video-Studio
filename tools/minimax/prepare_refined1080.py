"""Install an isolated first-frame refinement contract without replacing existing routes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(r'C:\install\AI\Data\H3Refined108020261020')
NAME = 'h3_keyframe_refine_1088_api.json'


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'tools/minimax' / NAME
    target = Path(r'C:\install\AI\Workflows') / NAME
    catalog = ROOT / 'config/workflow-contracts.json'
    original = catalog.read_bytes()
    document = json.loads(original)
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    contract = {
        'id': 'h3-keyframe-refine-1088-v1', 'version': 'h3-keyframe-refine-1088-v1', 'fileName': NAME,
        'workflowType': 'Image', 'productionEligible': False, 'experimental': True,
        'licenseStatus': 'LOCAL_ONLY_PENDING_REVIEW', 'taskTypes': ['Image', 'Keyframe'],
        'modelFiles': ['v1-5-pruned-emaonly-fp16.safetensors'],
        'modelSha256': {'v1-5-pruned-emaonly-fp16.safetensors': 'e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916'},
        'nodes': [
            {'role': 'checkpoint', 'nodeId': '1', 'classType': 'CheckpointLoaderSimple', 'inputName': 'ckpt_name'},
            {'role': 'positivePrompt', 'nodeId': '2', 'classType': 'CLIPTextEncode', 'inputName': 'text'},
            {'role': 'negativePrompt', 'nodeId': '3', 'classType': 'CLIPTextEncode', 'inputName': 'text'},
            {'role': 'resize', 'nodeId': '5', 'classType': 'ImageScale', 'inputName': 'width'},
            {'role': 'encode', 'nodeId': '6', 'classType': 'VAEEncodeTiled', 'inputName': 'pixels'},
            {'role': 'latent', 'nodeId': '7', 'classType': 'KSampler', 'inputName': 'seed'},
            {'role': 'decode', 'nodeId': '8', 'classType': 'VAEDecodeTiled', 'inputName': 'samples'},
            {'role': 'output', 'nodeId': '9', 'classType': 'SaveImage', 'inputName': 'filename_prefix'}],
        'slots': [{'role': 'firstFrame', 'nodeId': '4', 'classType': 'LoadImage', 'inputName': 'image', 'required': True}],
        'media': {'defaultWidth': 1920, 'defaultHeight': 1088,
                  'allowedDimensions': [{'width': 1920, 'height': 1088}], 'nativeFps': 1, 'exactFrameCount': False},
        'notes': 'sha256=' + fingerprint + ' | Explicit local SD1.5 low-denoise high-resolution reference refinement; tiled VAE, not photographic recovery or automatic content approval.'}
    matches = [item for item in document['contracts'] if item['id'] == contract['id']]
    if matches and matches != [contract]:
        raise RuntimeError('Existing refinement contract differs; preserved')
    if target.exists() and target.read_bytes() != source.read_bytes():
        raise RuntimeError('Existing central refinement workflow differs; preserved')
    backup = DATA / 'workflow-contracts.before.json'
    if not backup.exists():
        with backup.open('xb') as output:
            output.write(original)
    if not target.exists():
        with target.open('xb') as output:
            output.write(source.read_bytes())
    if not matches:
        text = original.decode('utf-8-sig')
        marker = '"contracts": ['
        insertion = json.dumps(contract, ensure_ascii=False, indent=2)
        insertion = '\n'.join('    ' + line for line in insertion.splitlines())
        replacement = text.replace(marker, marker + '\n' + insertion + ',', 1)
        if len(json.loads(replacement)['contracts']) != len(document['contracts']) + 1:
            raise RuntimeError('Catalog insertion failed')
        catalog.write_text(replacement, encoding='utf-8', newline='')
    print(json.dumps({'workflow': NAME, 'sha256': fingerprint, 'contractAdded': not bool(matches), 'generationSubmissions': 0}))


if __name__ == '__main__':
    main()

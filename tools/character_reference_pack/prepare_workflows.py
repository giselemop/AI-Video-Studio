"""Register explicit local Klein reference-pack workflows without changing old routes."""
from pathlib import Path
import copy
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
WORKFLOWS=ROOT.parent/'Workflows'
cfg_path=ROOT/'config/workflow-contracts.json'
cfg=json.loads(cfg_path.read_text(encoding='utf-8-sig'))
base=next(c for c in cfg['contracts'] if c['fileName']=='flux2_klein4b_keyframe_v2_api.json')
graph=json.loads((WORKFLOWS/base['fileName']).read_text(encoding='utf-8-sig'))
for dual in [False,True]:
    workflow=copy.deepcopy(graph)
    name='character_pack_klein4b_dual_api.json' if dual else 'character_pack_klein4b_single_api.json'
    key='character-pack-klein4b-dual-1536-v1' if dual else 'character-pack-klein4b-single-1536-v1'
    workflow['13']['inputs'].update(width=1536,height=864)
    workflow['15']['inputs'].update(width=1536,height=864)
    workflow['7']['inputs']['text']='Reference photograph of the same adult character. Preserve exact identity and the specified complete wardrobe. One person only, neutral pose and soft studio lighting.'
    workflow['18']['inputs']['filename_prefix']='CharacterReferencePack20261026/'+('dual' if dual else 'single')
    contract=copy.deepcopy(base)
    contract.update(id=key,version=key,fileName=name)
    contract['media'].update(defaultWidth=1536,defaultHeight=864,allowedDimensions=[dict(width=1536,height=864)])
    if dual:
        workflow.update({
            '20':dict(class_type='LoadImage',inputs=dict(image='character-full-body-anchor.png')),
            '21':dict(class_type='ImageScaleToTotalPixels',inputs=dict(image=['20',0],upscale_method='lanczos',megapixels=1.0,resolution_steps=1)),
            '22':dict(class_type='VAEEncode',inputs=dict(pixels=['21',0],vae=['3',0])),
            '23':dict(class_type='ReferenceLatent',inputs=dict(conditioning=['8',0],latent=['22',0])),
            '24':dict(class_type='ReferenceLatent',inputs=dict(conditioning=['10',0],latent=['22',0]))
        })
        workflow['11']['inputs'].update(positive=['23',0],negative=['24',0])
        contract['slots'].append(dict(role='wardrobeReference',nodeId='20',classType='LoadImage',inputName='image',required=True))
        contract['nodes'].extend([dict(role='wardrobePositiveReference',nodeId='23',classType='ReferenceLatent',inputName='latent'),dict(role='wardrobeNegativeReference',nodeId='24',classType='ReferenceLatent',inputName='latent')])
    encoded=(json.dumps(workflow,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    digest=hashlib.sha256(encoded).hexdigest()
    contract['notes']='sha256='+digest+' | Local experimental character reference pack. Explicit identity reference'+(' plus wardrobe/body reference' if dual else '')+'. 1536x864, 4-step distilled FP8, no automatic identity or production approval.'
    for directory in [WORKFLOWS,Path(__file__).parent]:
        target=directory/name
        if target.exists() and target.read_bytes()!=encoded:raise RuntimeError('Refuse to overwrite a different frozen pack workflow: '+str(target))
        if not target.exists():target.write_bytes(encoded)
    existing=next((c for c in cfg['contracts'] if c['id']==key),None)
    if existing and existing!=contract:raise RuntimeError('Existing reference-pack contract differs')
    if not existing:cfg['contracts'].append(contract)
    (Path(__file__).parent/(key+'.contract.json')).write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
cfg_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Two explicit reference-pack routes prepared; no GPU task submitted')

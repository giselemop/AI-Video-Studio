"""Register a five-reference fixed-background graph; no model installation."""
from pathlib import Path
import sys,json,copy,requests
sys.path.insert(0,str(Path(__file__).parent))
from common import ROOT,OUT,sha,write,mysql

def run():
    source=ROOT.parent/'Workflows/character_story_klein4b_four_api.json';graph=json.loads(source.read_text(encoding='utf-8'))
    graph.update({
      '50':dict(class_type='LoadImage',inputs=dict(image='frozen-scene-composition.png')),
      '51':dict(class_type='ImageScaleToTotalPixels',inputs=dict(image=['50',0],upscale_method='lanczos',megapixels=1.0,resolution_steps=1)),
      '52':dict(class_type='VAEEncode',inputs=dict(pixels=['51',0],vae=['3',0])),
      '53':dict(class_type='ReferenceLatent',inputs=dict(conditioning=['43',0],latent=['52',0])),
      '54':dict(class_type='ReferenceLatent',inputs=dict(conditioning=['44',0],latent=['52',0])),
      '60':dict(class_type='SolidMask',inputs=dict(value=0.0,width=1536,height=864)),
      '61':dict(class_type='SolidMask',inputs=dict(value=1.0,width=420,height=814)),
      '62':dict(class_type='FeatherMask',inputs=dict(mask=['61',0],left=32,top=32,right=32,bottom=0)),
      '63':dict(class_type='MaskComposite',inputs=dict(destination=['60',0],source=['62',0],x=300,y=50,operation='add')),
      '64':dict(class_type='SolidMask',inputs=dict(value=1.0,width=430,height=856)),
      '65':dict(class_type='FeatherMask',inputs=dict(mask=['64',0],left=32,top=32,right=32,bottom=0)),
      '66':dict(class_type='MaskComposite',inputs=dict(destination=['63',0],source=['65',0],x=820,y=8,operation='add')),
      '67':dict(class_type='ImageCompositeMasked',inputs=dict(destination=['50',0],source=['17',0],x=0,y=0,resize_source=False,mask=['66',0]))})
    graph['11']['inputs'].update(positive=['53',0],negative=['54',0]);graph['18']['inputs']['images']=['67',0]
    filename='character_scene_klein4b_five_locked_api.json';version='character-scene-klein4b-five-locked-1536-v1'
    content=json.dumps(graph,ensure_ascii=False,indent=2)+'\n';dest=ROOT.parent/'Workflows'/filename
    if dest.exists() and dest.read_text(encoding='utf-8')!=content:raise RuntimeError('Existing scene graph differs; preserve it')
    dest.write_text(content,encoding='utf-8');(ROOT/'tools/character_scene'/filename).write_text(content,encoding='utf-8')
    contract=copy.deepcopy(json.loads((ROOT/'tools/character_story/character-story-klein4b-four-1536-v1.contract.json').read_text(encoding='utf-8')))
    contract.update(id=version,version=version,fileName=filename,notes='sha256='+sha(dest)+' | Fixed-camera only. Four actor identity/wardrobe inputs plus explicit scene input. Final compositor preserves background outside two validated actor regions. Not general identity/scene control and not H3 Ref2VA. Content review required.')
    contract['slots'].append(dict(role='sceneReference',nodeId='50',classType='LoadImage',inputName='image',required=True))
    for role,node,cls,inputName in [('scenePositive','53','ReferenceLatent','latent'),('sceneNegative','54','ReferenceLatent','latent'),('backgroundMask','60','SolidMask','width'),('leftActorMask','61','SolidMask','width'),('rightActorMask','64','SolidMask','width'),('sceneCompositor','67','ImageCompositeMasked','mask')]:contract['nodes'].append(dict(role=role,nodeId=node,classType=cls,inputName=inputName))
    config=ROOT/'config/workflow-contracts.json';settings=json.loads(config.read_text(encoding='utf-8-sig'));old=next((c for c in settings['contracts'] if c['id']==version),None)
    if old is not None and old!=contract:raise RuntimeError('Existing scene contract differs')
    if old is None:settings['contracts'].append(contract);write(config,settings)
    write(ROOT/'tools/character_scene'/('character-scene-klein4b-five-locked-1536-v1.contract.json'),contract)
    info=requests.get('http://127.0.0.1:8188/object_info',timeout=45).json();assert all(n['class_type'] in info for n in graph.values())
    write(OUT/'workflow.json',dict(status='Passed',workflowFile=str(dest),workflowSha256=sha(dest),allActualNodesAvailable=True,slotRoles=[s['role'] for s in contract['slots']],empiricalStatus='Pending',newModels=0,h3Ref2VA=False))
    masked=copy.deepcopy(graph);masked.update({
      '68':dict(class_type='EmptyImage',inputs=dict(width=1536,height=864,batch_size=1,color=8421504)),
      '69':dict(class_type='ImageCompositeMasked',inputs=dict(destination=['50',0],source=['68',0],x=0,y=0,resize_source=False,mask=['74',0])),
      '70':dict(class_type='SolidMask',inputs=dict(value=0.0,width=1536,height=864)),
      '71':dict(class_type='SolidMask',inputs=dict(value=1.0,width=336,height=340)),
      '72':dict(class_type='MaskComposite',inputs=dict(destination=['70',0],source=['71',0],x=342,y=32,operation='add')),
      '73':dict(class_type='SolidMask',inputs=dict(value=1.0,width=350,height=340)),
      '74':dict(class_type='MaskComposite',inputs=dict(destination=['72',0],source=['73',0],x=845,y=0,operation='add'))});masked['51']['inputs']['image']=['69',0]
    filename2='character_scene_klein4b_five_masked_locked_api.json';version2='character-scene-klein4b-five-masked-locked-1536-v1';content2=json.dumps(masked,ensure_ascii=False,indent=2)+'\n';dest2=dest.with_name(filename2)
    prior2=next((c for c in settings['contracts'] if c['id']==version2),None)
    reviseUnused='--revise-unused' in sys.argv and mysql("SELECT COUNT(*) FROM generation_tasks WHERE JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.workflowVersion'))='"+version2+"';")=='0'
    if dest2.exists() and dest2.read_text(encoding='utf-8')!=content2:
        if not reviseUnused or prior2 is None or ('sha256='+sha(dest2)) not in prior2['notes']:raise RuntimeError('Existing masked scene graph differs; preserve used or unknown work')
        (OUT/'unexecuted-draft-before-head-mask.json').write_bytes(dest2.read_bytes())
    dest2.write_text(content2,encoding='utf-8');(ROOT/'tools/character_scene'/filename2).write_text(content2,encoding='utf-8')
    contract2=copy.deepcopy(contract);contract2.update(id=version2,version=version2,fileName=filename2,notes='sha256='+sha(dest2)+' | Scene conditioning blanks old head poses, retaining body composition. Final compositor uses original scene pixels outside actor regions. Fixed-camera preview only; identities, anatomy and seams require inspection. No H3 Ref2VA.')
    contract2['nodes']+= [dict(role='neutralSceneFill',nodeId='68',classType='EmptyImage',inputName='width'),dict(role='sceneHeadPoseExclusion',nodeId='69',classType='ImageCompositeMasked',inputName='mask'),dict(role='leftHeadMask',nodeId='71',classType='SolidMask',inputName='width'),dict(role='rightHeadMask',nodeId='73',classType='SolidMask',inputName='width')]
    old2=next((c for c in settings['contracts'] if c['id']==version2),None)
    if old2 is not None and old2!=contract2:
        if not reviseUnused:raise RuntimeError('Existing masked scene contract differs')
        settings['contracts'][settings['contracts'].index(old2)]=contract2;write(config,settings)
    if old2 is None:settings['contracts'].append(contract2);write(config,settings)
    write(ROOT/'tools/character_scene'/('character-scene-klein4b-five-masked-locked-1536-v1.contract.json'),contract2);assert all(n['class_type'] in info for n in masked.values())
    print('Five independent inputs and explicit background compositor installed; actual Comfy node availability checked. No model download.')
if __name__=='__main__':run()

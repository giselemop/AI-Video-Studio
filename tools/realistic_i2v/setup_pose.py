"""Prepare a procedural OpenPose guide and a pinned queue workflow; no inference."""
import copy
import hashlib
import json
import math
from pathlib import Path
import io
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'RealisticI2V20261022'


def main():
    folder=DATA/'ReferenceGuides/RealisticI2V20261022'
    folder.mkdir(parents=True,exist_ok=True)
    # COCO-18 body keypoints and the upstream ControlNet RGB bone convention.
    points=[(937,159),(940,239),(872,267),(830,382),(790,491),
        (1005,268),(1035,391),(1026,510),(906,503),(895,652),(880,803),
        (981,503),(983,652),(1001,803),(925,148),(949,148),(912,160),(964,160)]
    colors=[(255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),
        (0,255,0),(0,255,85),(0,255,170),(0,255,255),(0,170,255),(0,85,255),
        (0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85)]
    limbs=[(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),
        (1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
    scale=3
    canvas=Image.new('RGB',(1536*scale,864*scale))
    for index,(a,b) in enumerate(limbs):
        layer=canvas.copy()
        ImageDraw.Draw(layer).line([tuple(v*scale for v in points[a]),tuple(v*scale for v in points[b])],fill=colors[index],width=10*scale)
        canvas=Image.blend(canvas,layer,.6)
    draw=ImageDraw.Draw(canvas)
    for (x,y),color in zip(points,colors):draw.ellipse(((x-6)*scale,(y-6)*scale,(x+6)*scale,(y+6)*scale),fill=color)
    canvas=canvas.resize((1536,864),Image.Resampling.LANCZOS)
    guide=folder/'standing-pose.png'
    buffer=io.BytesIO();canvas.save(buffer,format='PNG');encoded=buffer.getvalue()
    if guide.exists() and guide.read_bytes()!=encoded:raise RuntimeError('Existing pose guide differs; preserved')
    if not guide.exists():guide.write_bytes(encoded)
    (folder/'standing-pose.json').write_text(json.dumps(dict(width=1536,height=864,
        bodyKeypoints=points,provenance='Procedural COCO18 guide, not a generated photograph',
        source='https://github.com/lllyasviel/ControlNet/blob/main/annotator/openpose/util.py'),indent=2),encoding='utf-8')
    workflow=json.loads((ROOT/'tools/realistic_i2v/realvisxl_reference_api.json').read_text(encoding='utf-8'))
    workflow['8']=dict(class_type='ControlNetLoader',inputs=dict(control_net_name='xinsir_openpose_sdxl_1.0.safetensors'))
    workflow['9']=dict(class_type='LoadImage',inputs=dict(image='standing-pose.png'))
    workflow['10']=dict(class_type='ControlNetApplyAdvanced',inputs=dict(positive=['2',0],negative=['3',0],
        control_net=['8',0],image=['9',0],strength=1.0,start_percent=0.0,end_percent=.9))
    workflow['5']['inputs'].update(positive=['10',0],negative=['10',1])
    workflow['7']['inputs']['filename_prefix']='realistic_i2v/pose_reference'
    raw=json.dumps(workflow,indent=2)+'\n';digest=hashlib.sha256(raw.encode()).hexdigest()
    filename='realvisxl_openpose_reference_api.json'
    for target in [ROOT/'tools/realistic_i2v'/filename,ROOT.parent/'Workflows'/filename]:
        if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=workflow:raise RuntimeError('Existing pose workflow differs; preserved')
        target.write_bytes(raw.encode('utf-8'))
    config=ROOT/'config/workflow-contracts.json'
    catalog=json.loads(config.read_text(encoding='utf-8'))
    contract=copy.deepcopy(next(c for c in catalog['contracts'] if c['fileName']=='realvisxl_reference_api.json'))
    contract.update(id='realvisxl-openpose-reference-1536-v1',version='realvisxl-openpose-reference-1536-v1',fileName=filename)
    model='xinsir_openpose_sdxl_1.0.safetensors'
    contract['modelFiles'].append(model)
    contract['modelSha256'][model]='b8524e557a7df60d081f5d4a0eb109967d107df217943bf88c2d99b9ebcc06c5'
    contract['nodes'].extend([dict(role='controlNetLoader',nodeId='8',classType='ControlNetLoader',inputName='control_net_name'),
        dict(role='controlNet',nodeId='10',classType='ControlNetApplyAdvanced',inputName='strength')])
    contract['slots']=[dict(role='pose',nodeId='9',classType='LoadImage',inputName='image',required=True)]
    contract['notes']=f'sha256={digest} | Explicit local SDXL OpenPose reference; fixed body pose, content inspection required.'
    existing=next((c for c in catalog['contracts'] if c['fileName']==filename),None)
    if existing and existing!=contract:raise RuntimeError('Existing pose contract differs; preserved')
    if not existing:
        catalog['contracts'].insert(0,contract);config.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='Passed',workflow=filename,workflowSha256=digest,
        posePath=guide.relative_to(DATA).as_posix(),poseSha256=hashlib.sha256(guide.read_bytes()).hexdigest())),flush=True)


if __name__=='__main__':main()

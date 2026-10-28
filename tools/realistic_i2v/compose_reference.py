"""Prepare a local, traceable book layout and masked SDXL harmonization workflow."""
import copy
import hashlib
import json
from pathlib import Path
import random
from PIL import Image,ImageDraw,ImageFilter

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'RealisticI2V20261022'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    original=DATA/state['reference3TaskIdPath']
    assert digest(original)==state['reference3TaskIdSha256']
    image=Image.open(original).convert('RGB')
    scale=3;size=(image.width*scale,image.height*scale)
    base=image.resize(size,Image.Resampling.LANCZOS).convert('RGBA')
    points=[(808,626),(971,611),(1032,644),(861,661)]
    def polygon(draw,xy,fill):draw.polygon([(int(x*scale),int(y*scale)) for x,y in xy],fill=fill)
    shadow=Image.new('RGBA',size);sd=ImageDraw.Draw(shadow)
    polygon(sd,[(x+7,y+10) for x,y in points],(12,9,7,125))
    base=Image.alpha_composite(base,shadow.filter(ImageFilter.GaussianBlur(5*scale)))
    book=Image.new('RGBA',size);draw=ImageDraw.Draw(book)
    polygon(draw,[(808,634),(971,619),(1032,652),(861,669)],(103,13,19,255))
    polygon(draw,[(808,627),(861,662),(861,668),(808,634)],(107,18,21,255))
    polygon(draw,[(861,661),(1032,644),(1030,652),(862,668)],(222,211,187,255))
    for offset in [2,4,6]:
        draw.line([(862*scale,(661+offset)*scale),(1030*scale,(644+offset)*scale)],fill=(163,151,128,255),width=1)
    cover=Image.new('RGBA',size);cd=ImageDraw.Draw(cover)
    polygon(cd,points,(169,29,35,255))
    texture=Image.new('RGBA',size);td=ImageDraw.Draw(texture);rng=random.Random(2026102207)
    coverMask=cover.getchannel('A')
    for _ in range(26000):
        x=rng.randrange(805*scale,1035*scale);y=rng.randrange(608*scale,663*scale)
        if coverMask.getpixel((x,y)):
            value=rng.randrange(-15,16)
            td.point((x,y),fill=(max(0,169+value),max(0,29+value),max(0,35+value),100))
    cover=Image.alpha_composite(cover,texture)
    cd=ImageDraw.Draw(cover)
    cd.line([(x*scale,y*scale) for x,y in points+[points[0]]],fill=(200,58,57,255),width=2*scale)
    cd.line([(956*scale,613*scale),(1015*scale,646*scale)],fill=(56,18,21,255),width=3*scale)
    book=Image.alpha_composite(book,cover)
    base=Image.alpha_composite(base,book).convert('RGB').resize(image.size,Image.Resampling.LANCZOS)
    # Keep the original untouched everywhere outside the small book/shadow region.
    mask=Image.new('L',image.size);md=ImageDraw.Draw(mask)
    md.polygon([(792,612),(978,597),(1055,643),(1042,680),(855,690),(793,646)],fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(5))
    layout=Image.composite(base,image,mask)
    target=DATA/'ReferenceGuides/RealisticI2V20261022';target.mkdir(parents=True,exist_ok=True)
    layoutPath=target/'book-layout.png';maskPath=target/'book-edit-mask.png'
    for path,value in [(layoutPath,layout),(maskPath,mask.convert('RGB'))]:
        if path.exists():
            if Image.open(path).tobytes()!=value.tobytes():raise RuntimeError('Existing layout differs; preserved')
        else:value.save(path)
    receipt=dict(sourcePath=state['reference3TaskIdPath'],sourceSha256=digest(original),
        layoutPath=layoutPath.relative_to(DATA).as_posix(),layoutSha256=digest(layoutPath),
        maskPath=maskPath.relative_to(DATA).as_posix(),maskSha256=digest(maskPath),bookTopCorners=points,
        method='Deterministic local book placement followed by masked SDXL harmonization; original woman is protected',
        shotRevision='Seated woman picks up one book beside her and pauses; no standing transition')
    (FOLDER/'book-layout.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    graph={
        '1':dict(class_type='CheckpointLoaderSimple',inputs=dict(ckpt_name='RealVisXL_V5.0_fp16.safetensors')),
        '2':dict(class_type='CLIPTextEncode',inputs=dict(clip=['1',1],text='One closed red hardcover notebook resting flat on a wooden bench seat, white paper edges, natural light and contact shadow, realistic photograph')),
        '3':dict(class_type='CLIPTextEncode',inputs=dict(clip=['1',1],text='open book, bag, multiple books, letters, text, logo, deformed book, cartoon')),
        '4':dict(class_type='LoadImage',inputs=dict(image='book-layout.png')),
        '5':dict(class_type='LoadImage',inputs=dict(image='book-edit-mask.png')),
        '6':dict(class_type='ImageToMask',inputs=dict(image=['5',0],channel='red')),
        '7':dict(class_type='VAEEncodeTiled',inputs=dict(pixels=['4',0],vae=['1',2],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)),
        '8':dict(class_type='SetLatentNoiseMask',inputs=dict(samples=['7',0],mask=['6',0])),
        '9':dict(class_type='KSampler',inputs=dict(model=['1',0],positive=['2',0],negative=['3',0],latent_image=['8',0],seed=2026102207,steps=24,cfg=5.0,sampler_name='dpmpp_sde',scheduler='karras',denoise=.28)),
        '10':dict(class_type='VAEDecodeTiled',inputs=dict(samples=['9',0],vae=['1',2],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)),
        '11':dict(class_type='ImageCompositeMasked',inputs=dict(destination=['4',0],source=['10',0],x=0,y=0,resize_source=False,mask=['6',0])),
        '12':dict(class_type='SaveImage',inputs=dict(images=['11',0],filename_prefix='realistic_i2v/book_reference'))}
    filename='realvisxl_book_reference_api.json';raw=(json.dumps(graph,indent=2)+'\n').encode('utf-8')
    for path in [ROOT/'tools/realistic_i2v'/filename,ROOT.parent/'Workflows'/filename]:
        if path.exists() and path.read_bytes()!=raw:raise RuntimeError('Existing book workflow differs; preserved')
        path.write_bytes(raw)
    contractPath=ROOT/'config/workflow-contracts.json';catalog=json.loads(contractPath.read_text(encoding='utf-8'))
    contract=copy.deepcopy(next(c for c in catalog['contracts'] if c['fileName']=='realvisxl_reference_api.json'))
    contract.update(id='realvisxl-book-reference-1536-v1',version='realvisxl-book-reference-1536-v1',fileName=filename)
    contract['nodes']=[dict(role=role,nodeId=node,classType=kind,inputName=name) for role,node,kind,name in [
        ('checkpoint','1','CheckpointLoaderSimple','ckpt_name'),('positivePrompt','2','CLIPTextEncode','text'),
        ('negativePrompt','3','CLIPTextEncode','text'),('sampler','9','KSampler','seed'),('output','12','SaveImage','filename_prefix')]]
    contract['slots']=[dict(role=role,nodeId=node,classType='LoadImage',inputName='image',required=True) for role,node in [('firstFrame','4'),('editMask','5')]]
    contract['notes']='sha256='+hashlib.sha256(raw).hexdigest()+' | Masked local book harmonization; exact unmasked subject preservation; content inspection required.'
    existing=next((c for c in catalog['contracts'] if c['fileName']==filename),None)
    if existing and existing!=contract:raise RuntimeError('Existing book contract differs; preserved')
    if not existing:
        catalog['contracts'].insert(0,contract);contractPath.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='Passed',**receipt,workflowSha256=hashlib.sha256(raw).hexdigest())),flush=True)


if __name__=='__main__':main()

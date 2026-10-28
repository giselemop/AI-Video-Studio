"""Read-only inventory and inspection sheets; never submits a GPU task."""
from pathlib import Path
import sys, json, hashlib
import requests
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]; DATA=ROOT.parent/'Data'; OUT=DATA/'CharacterReferenceRepair20261027'
sys.path.insert(0,str(ROOT/'tools'))
from character_prompt_policy import POLICY, SLOTS, compose

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def media(path):
    p=(DATA/path).resolve(strict=True)
    if not p.is_relative_to(DATA.resolve()):raise ValueError('Data boundary')
    return p
def sheet(cid,refs):
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    canvas=Image.new('RGB',(1536,((len(refs)+2)//3)*330),'#18212c');draw=ImageDraw.Draw(canvas)
    for i,r in enumerate(refs):
        im=Image.open(media(r['assetPath'])).convert('RGB');im=ImageOps.contain(im,(504,286))
        x=(i%3)*512;y=(i//3)*330;canvas.paste(im,(x+(512-im.width)//2,y))
        draw.text((x+5,y+289),f"ref{r['id']} {r['kind']}",font=font,fill='white')
        draw.text((x+5,y+310),r['reviewStatus'],font=font,fill='#ddd')
    p=OUT/f'inspect/character-{cid}.jpg';p.parent.mkdir(parents=True,exist_ok=True);canvas.save(p,quality=95)

def run():
    s=requests.Session();base='http://127.0.0.1:18080'
    chars=s.get(base+'/api/characters',timeout=30).json();records=[]
    for c in chars:
        refs=s.get(base+f"/api/characters/{c['id']}/references",timeout=30).json()
        for r in refs:
            if r['available']:r['actualSha256']=sha(media(r['assetPath']))
        records.append(dict(character=c,references=refs))
        visible=[r for r in reversed(refs) if r['available'] and r['reviewStatus']!='Rejected']
        if visible:sheet(c['id'],visible)
    state=dict(policy=POLICY['version'],characters=records,versions=s.get(base+'/api/character-library',timeout=30).json()['versions'],
       health=s.get(base+'/api/health',timeout=30).json(),queue=s.get('http://127.0.0.1:8188/queue',timeout=30).json())
    path=OUT/'inventory-before.json'
    if path.exists():raise RuntimeError('Existing before snapshot preserved; inspect it rather than overwrite')
    write(path,state)
    for r in records:print(r['character']['id'],r['character']['name'],len(r['references']),flush=True)
    print('Total references',sum(len(r['references']) for r in records))
if __name__=='__main__':run()

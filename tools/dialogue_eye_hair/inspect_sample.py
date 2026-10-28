"""Dense actual frames for eye/hair and speaking-mouth seam review."""
from run import *
import cv2,numpy as np
from PIL import Image,ImageDraw
def frame(p,i):
    c=cv2.VideoCapture(str(media(p)));c.set(cv2.CAP_PROP_POS_FRAMES,i);ok,x=c.read();c.release()
    if not ok:raise RuntimeError('Missing decoded comparison frame')
    return x
def head(x):
    h,w=x.shape[:2];return x[round(h*.055):round(h*.48),round(w*.17):round(w*.44)]
def sheet(items,name,cols=4):
    out=Image.new('RGB',(320*cols,350*((len(items)+cols-1)//cols)),'#10151c');d=ImageDraw.Draw(out)
    for k,(label,x) in enumerate(items):
        im=Image.fromarray(cv2.cvtColor(head(x),cv2.COLOR_BGR2RGB));im.thumbnail((320,320));xx=k%cols*320;yy=k//cols*350;out.paste(im,(xx+(320-im.width)//2,yy+30));d.text((xx+5,yy+7),label,fill='white')
    out.save(FOLDER/name)
def main():
    s=read(FOLDER/'run.json');p=s['wideCanvasPath'];indices=[0,4,12,24,36,48,53,58,72,89,94,96,98,104,120,143]
    sheet([(f'NEW {4+i/24:.3f}s | wide{i}',frame(p,i)) for i in indices],'sample-mouth-and-hair.png')
    items=[]
    for i in [188,190,191,192,193,195,196,200]:
        items += [(f'BEFORE {i/24:.3f}s',frame(s['inputs']['before'],i)),(f'GUARD {i/24:.3f}s',frame(p,i-96))]
    sheet(items,'sample-dense-before-after.png',4)
    receipt=read(media(s['wideMergeReceiptPath']))
    if len(receipt['frames'])!=151 or not receipt['femaleSideProfileBlinkDisabled'] or any(x['femaleOutsideMouthMaxChange'] or x['maleCompositeMaxChange'] for x in receipt['frames']):raise RuntimeError('Protected source trace failed')
    source=cv2.imread(str(media(s['inputs']['source'])));c=cv2.VideoCapture(str(media(s['wideMergePath'])));rows=[]
    masks=dict(eyes=(slice(120,170),slice(325,390)),hair=(slice(25,160),slice(220,325)))
    while True:
        ok,x=c.read()
        if not ok:break
        errors={k:float(np.abs(x[box].astype(np.float32)-source[box].astype(np.float32)).mean()) for k,box in masks.items()}
        if max(errors.values())>4:raise RuntimeError('Encoded eye/hair source error too large')
        rows.append(dict(frame=len(rows),**errors))
    c.release()
    if len(rows)!=151:raise RuntimeError('Native decode count differs')
    write(FOLDER/'sample-pixel-checks.json',dict(status='Passed',preEncodeOutsideFemaleMouthMaxChange=0,preEncodeMaleCompositeMaxChange=0,nativeFrames=151,encodedReferenceRoiErrors=rows,scope='Source anchoring before encoding; after encoding mean ROI errors bounded, not pixel equality or a perceptual score'))
    print('Passed:151-frame source eye/hair protection; actual dense panels ready for visual review')
if __name__=='__main__':main()

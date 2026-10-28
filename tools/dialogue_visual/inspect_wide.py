"""Create actual decoded wide-shot contacts around restoration chunk joins."""
from run import *
import cv2,numpy as np
from PIL import Image,ImageDraw

s=read(FOLDER/'run.json');indices=[0,32,33,34,65,66,67,98,99,100,131,132,133,143]
def frame(path,index):
    cap=cv2.VideoCapture(str(media(path)));cap.set(cv2.CAP_PROP_POS_FRAMES,index)
    ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Missing actual wide frame')
    return pixels

for page,start in enumerate(range(0,len(indices),4),1):
    selected=indices[start:start+4];contact=Image.new('RGB',(1024,320*len(selected)),'#10151c');draw=ImageDraw.Draw(contact)
    for row,index in enumerate(selected):
        for col,(path,position,label) in enumerate([(s['inputs']['original'],index+96,'PREVIOUS'),(s['detail3Path'],index,'NEW')]):
            pixels=frame(path,position)
            im=Image.fromarray(cv2.cvtColor(pixels,cv2.COLOR_BGR2RGB)).resize((512,288),Image.Resampling.LANCZOS)
            contact.paste(im,(col*512,row*320+32));draw.text((col*512+8,row*320+10),f'{label} | local {index} | global {index+96}',fill='white')
    contact.save(FOLDER/f'wide-inspect-{page}.png')
rows=[]
for index in [33,66,99,132]:
    values={}
    for prefix in ['canvas','qhd','detail']:
        a=cv2.resize(frame(s[prefix+'3Path'],index-1),(1280,720)).astype(np.float32)
        b=cv2.resize(frame(s[prefix+'3Path'],index),(1280,720)).astype(np.float32)
        values[prefix]=float(np.abs(b-a).mean())
    rows.append(dict(localFrame=index,meanAdjacentPixelDifference=values))
write(FOLDER/'wide-chunk-diagnostics.json',dict(status='Recorded',frames=indices,chunkBoundaryPixelDifferences=rows,
    scope='Actual decoded adjacent frame differences; diagnostic only, not continuity or aesthetic score'))
print('Actual wide contacts created; visual inspection still required')

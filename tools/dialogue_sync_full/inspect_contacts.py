"""Decode real full-shot comparisons for human inspection; no invented visual scores."""
from run import *
import cv2
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('--stage',choices=['driver','canvas','final'],required=True);p.add_argument('--index',type=int,choices=[1,2,3],default=1);a=p.parse_args();s=read(FOLDER/'run.json');shot=SHOTS[a.index-1]
fps=25 if a.stage=='driver' else 24;n=shot['native'] if a.stage=='driver' else shot['frames'];indices=sorted(set([0,5,round(n*.25),round(n*.5),round(n*.75),n-2,n-1]))
path=s[f'driver{a.index}Path'] if a.stage=='driver' else s[f'canvas{a.index}Path'] if a.stage=='canvas' else s['finalPath']
contact=Image.new('RGB',(1024,320*len(indices)),'#10151c');draw=ImageDraw.Draw(contact)
for row,i in enumerate(indices):
    original=shot['start']+min(shot['frames']-1,round(i/fps*24));new=i+shot['start'] if a.stage=='final' else i
    for side,p,frame,label in [(0,s['inputs']['original'],original,'PREVIOUS'),(1,path,new,'NEW '+a.stage.upper())]:
        cap=cv2.VideoCapture(str(media(p)));cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,image=cap.read();cap.release()
        if not ok:raise RuntimeError('Actual frame missing')
        im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).resize((512,288),Image.Resampling.LANCZOS);contact.paste(im,(512*side,row*320+32));draw.text((512*side+8,row*320+10),label+f' | frame{frame} | {frame/(24 if side==0 or a.stage=="final" else fps):.3f}s',fill='white')
contact.save(FOLDER/f'shot-{a.index}-{a.stage}-contact.png');print('Actual decoded contacts saved; inspect before selection')

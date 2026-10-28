"""Actual face crops at QHD chunk join and largest landmark difference frames."""
from run import *
import cv2
from PIL import Image,ImageDraw
s=read(FOLDER/'run.json');a=read(FOLDER/'audit-canvas.json');b=read(FOLDER/'audit-new.json');diagnostics=read(FOLDER/'qhd-mouth-diagnostics.json')
for clip in CLIPS:
    name=clip['name'];before=next(x for x in a['clips'] if x['clip']==name);after=next(x for x in b['clips'] if x['clip']==name)
    for person,role in enumerate(clip['roles']):
        row=next(x for x in diagnostics['observations'] if x['clip']==name and x['role']==role);indices=sorted(set([32,33,34,row['largestDifferenceFrames'][0]['frame']]))
        contact=Image.new('RGB',(640,352*len(indices)),'#10151c');draw=ImageDraw.Draw(contact)
        for line,index in enumerate(indices):
            for side,(path,observations,label) in enumerate([(s[name+'CanvasPath'],before,'BEFORE QHD'),(s[name+'FinalPath'],after,'FINAL')]):
                cap=cv2.VideoCapture(str(media(path)));cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=cap.read();cap.release()
                if not ok:raise RuntimeError('QHD comparison frame missing')
                image=cv2.resize(image,(1280,720));x1,y1,x2,y2=observations['observations'][index]['people'][person]['bbox'];size=min(max(x2-x1,y2-y1)*1.35,720)
                x=min(max((x1+x2-size)/2,0),1280-size);y=min(max((y1+y2-size)/2,0),720-size)
                im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).crop((x,y,x+size,y+size)).resize((320,320),Image.Resampling.LANCZOS);contact.paste(im,(side*320,line*352+32))
                draw.text((side*320+8,line*352+10),label+f' | {name} {role} | frame{index}',fill='white')
        contact.save(FOLDER/f'qhd-inspect-{name}-{role}.png')
print('Actual QHD join/largest-difference face contacts saved; visual review required')

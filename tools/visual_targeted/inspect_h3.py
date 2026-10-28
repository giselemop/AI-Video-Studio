"""Actual-frame mouth aperture observations; no identity or quality score."""
from run import *
import cv2,numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
from identity_foundation import import_runtime
*_,FaceAnalysis=import_runtime()
app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68'])
app.prepare(ctx_id=-1,det_size=(640,640))
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.preserve()
moments=[0,12,24,36,48,61,72,84,92,104,116,123];canvas=Image.new('RGB',(2400,440),'#10151c');draw=ImageDraw.Draw(canvas);rows=[]
for row,p in enumerate([r.state['inputs']['h3ControlledPath'],r.state['h3RepairPath']]):
    cap=cv2.VideoCapture(str(media(p)));i=0;values=[]
    while True:
        ok,img=cap.read()
        if not ok:break
        faces=app.get(img)
        if not faces:raise RuntimeError('Face unavailable for aperture observation')
        f=max(faces,key=lambda v:np.prod(v.bbox[2:]-v.bbox[:2]));pts=f.landmark_3d_68[:,:2]
        width=np.linalg.norm(pts[60]-pts[64]);gap=np.mean([np.linalg.norm(pts[a]-pts[b]) for a,b in [(61,67),(62,66),(63,65)]])
        values.append(dict(frame=i,innerLipApertureRatio=float(gap/max(width,1))))
        if i in moments:
            x1,y1,x2,y2=f.bbox;cx=(x1+x2)/2;cy=(y1+y2)/2;size=max(x2-x1,y2-y1)*1.2
            im=Image.fromarray(cv2.cvtColor(img,cv2.COLOR_BGR2RGB)).crop((cx-size/2,cy-size/2,cx+size/2,cy+size/2)).resize((200,200))
            col=moments.index(i);canvas.paste(im,(col*200,row*220+25));draw.text((col*200+3,row*220+4),('OLD' if row==0 else 'NEW')+f' {i}',fill='white')
        i+=1
    cap.release()
    if i!=124:raise RuntimeError('H3 frame count differs')
    mid=[v['innerLipApertureRatio'] for v in values[24:105]]
    rows.append(dict(path=p,frames=values,middleP95=float(np.percentile(mid,95)),middleMax=float(max(mid))))
canvas.save(FOLDER/'h3-mouth-contact.png')
write(FOLDER/'h3-aperture-observations.json',dict(status='Passed',device='CPU',rows=rows,
    interpretation='Normalized 68-point inner-lip landmark gap on actual frames; diagnostic only, not proof of teeth visibility, identity or naturalness'))
print('H3 all124 frames inspected for normalized mouth-gap observations')

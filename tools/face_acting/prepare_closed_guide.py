"""Bounded CPU mouth-closure guide for the next local diffusion attempt, never a final take."""
import cv2
import numpy as np
from run import FOLDER,DATA,API,Run,read,write,media

run=Run(API,FOLDER/'run.json')
for role in ['female','male']:
    geometry=run.state['geometry'][role];p=np.asarray(geometry['points'],np.float32)
    source=cv2.imread(str(media(geometry['input'])))
    erase=np.zeros(source.shape[:2],np.uint8)
    cv2.fillConvexPoly(erase,cv2.convexHull(p[48:60].astype(np.int32)),255)
    erase=cv2.dilate(erase,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(23,23)))
    guide=cv2.inpaint(source,erase,9,cv2.INPAINT_TELEA)
    left,right=p[48].copy(),p[54].copy();center=(left+right)/2
    left=center+(left-center)*.88;right=center+(right-center)*.88
    width=float(np.linalg.norm(right-left));axis=(right-left)/max(width,1e-6);normal=np.array([-axis[1],axis[0]],np.float32)
    # A narrow closed lip guide replaces the old exposed teeth; the GPU reconstructs it.
    upper=[];lower=[];seam=[]
    for t in np.linspace(0,1,45):
        base=left+(right-left)*t
        sag=normal*(np.sin(np.pi*t)*width*.035)
        seam.append(base+sag)
        upper.append(base+sag-normal*(np.sin(np.pi*t)*width*.025))
        lower.append(base+sag+normal*(np.sin(np.pi*t)*width*.045))
    lip=np.asarray(upper+lower[::-1],np.int32)
    original_lip=source[np.clip(p[50:53,1].astype(int),0,767),np.clip(p[50:53,0].astype(int),0,767)]
    color=np.median(original_lip,axis=0).astype(int)
    cv2.fillPoly(guide,[lip],tuple(int(x) for x in color))
    cv2.polylines(guide,[np.asarray(seam,np.int32)],False,tuple(int(max(0,x*.58)) for x in color),2,cv2.LINE_AA)
    mask=cv2.imread(str(media(geometry['mask'])),cv2.IMREAD_GRAYSCALE).astype(np.float32)/255
    guide=np.rint(source*(1-mask[:,:,None])+guide*mask[:,:,None]).astype(np.uint8)
    path=FOLDER/'references'/role/'closed-guide.png';cv2.imwrite(str(path),guide)
    if role=='female':
        write(FOLDER/'female-reference-repair-2.json',dict(category='Reference/Prompt',reason='All three initial references retained exposed teeth instead of closed lips.',
             changes=dict(input='closed-guide.png; CPU-only removal of original teeth and narrow closed-lip guide',denoise=.62,cfg=5.0),
             scope='Guide only; final reference must be a real new ComfyUI image, preserve original upper identity features.'))
print('Local closed-lip guides prepared; no media task submitted',flush=True)

"""Reuse the verified closure correction for the male reference before his first attempt."""
import cv2
import numpy as np
from run import FOLDER,API,Run,media,write

run=Run(API,FOLDER/'run.json');g=run.state['geometry']['male'];p=np.asarray(g['points'],np.float32)
source=cv2.imread(str(media(g['input'])));erase=np.zeros(source.shape[:2],np.uint8)
cv2.fillConvexPoly(erase,cv2.convexHull(p[48:60].astype(np.int32)),255)
erase=cv2.dilate(erase,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(29,29)))
guide=cv2.inpaint(source,erase,11,cv2.INPAINT_TELEA)
left,right=p[48].copy(),p[54].copy();old=(left+right)/2;center=(p[62]+p[66])/2
left=center+(left-old)*.9;right=center+(right-old)*.9
width=float(np.linalg.norm(right-left));normal=np.array([-(right-left)[1],(right-left)[0]])/width
upper=[];lower=[];seam=[]
for t in np.linspace(0,1,60):
    base=left+(right-left)*t+normal*width*.02*np.sin(np.pi*t)
    seam.append(base);upper.append(base-normal*width*.025*np.sin(np.pi*t));lower.append(base+normal*width*.04*np.sin(np.pi*t))
cv2.fillPoly(guide,[np.asarray(upper+lower[::-1],np.int32)],(51,58,88))
cv2.polylines(guide,[np.asarray(seam,np.int32)],False,(30,33,44),2,cv2.LINE_AA)
mask=cv2.imread(str(media(g['mask'])),cv2.IMREAD_GRAYSCALE).astype(np.float32)/255
guide=np.rint(source*(1-mask[:,:,None])+guide*mask[:,:,None]).astype(np.uint8)
cv2.imwrite(str(FOLDER/'references/male/closed-guide.png'),guide)
write(FOLDER/'male-initial-reference-plan.json',dict(reason='Apply female-reference finding before the first male attempt; erase fixed exposed teeth and place closed lips at the original upper/lower lip centre.',denoise=.62,cfg=5.0,newVoice=False))
print('Male closed-lip initial guide prepared',flush=True)

"""Final bounded reference repair: correct the occluded far mouth corner, not the actor identity."""
import cv2
import numpy as np
from run import FOLDER,DATA,API,Run,read,write,media

run=Run(API,FOLDER/'run.json');g=run.state['geometry']['female'];p=np.asarray(g['points'],np.float32)
original=cv2.imread(str(media(g['input'])))
mask=cv2.imread(str(media(g['mask'])),cv2.IMREAD_GRAYSCALE)
mouth=np.zeros_like(mask)
# Visual correction to unreliable far-side 3D landmarks on this one fixed 3/4 portrait.
cv2.ellipse(mouth,(495,548),(101,73),0,0,360,255,-1)
mask=np.maximum(mask,cv2.GaussianBlur(mouth,(0,0),5))
guide=cv2.inpaint(original,mouth,11,cv2.INPAINT_TELEA)
left=np.array([426.,539.],np.float32);right=np.array([547.,536.],np.float32)
upper=[];lower=[];seam=[]
for t in np.linspace(0,1,60):
    base=left+(right-left)*t+np.array([0,3*np.sin(np.pi*t)],np.float32)
    seam.append(base);upper.append(base+[0,-4*np.sin(np.pi*t)]);lower.append(base+[0,7*np.sin(np.pi*t)])
cv2.fillPoly(guide,[np.asarray(upper+lower[::-1],np.int32)],(75,83,115))
cv2.polylines(guide,[np.asarray(seam,np.int32)],False,(43,45,64),2,cv2.LINE_AA)
alpha=mask.astype(np.float32)/255
guide=np.rint(original*(1-alpha[:,:,None])+guide*alpha[:,:,None]).astype(np.uint8)
folder=FOLDER/'references/female'
cv2.imwrite(str(folder/'closed-guide-v3.png'),guide);cv2.imwrite(str(folder/'mask-v3.png'),cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
write(FOLDER/'female-reference-repair-3.json',dict(category='Mask/Reference',reason='Occluded far-side mouth landmarks clipped the real mouth corner; second-round guide placed the closed lip line too high and retained a bright old mouth corner.',
    input=str((folder/'closed-guide-v3.png').relative_to(DATA)),mask=str((folder/'mask-v3.png').relative_to(DATA)),
    changes='Include entire visually checked mouth ellipse, lower lip guide to the original upper/lower lip centre, keep original eyes/nose/hair; denoise .62 CFG5.',
    automaticReferenceRepairsUsed=2))
print('Final bounded mouth-corner repair guide prepared',flush=True)

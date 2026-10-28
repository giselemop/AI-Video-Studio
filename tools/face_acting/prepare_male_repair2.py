"""Protect the entire downcast eye region after a rejected double-eyelid artifact."""
import cv2
import numpy as np
from run import FOLDER,DATA,API,Run,media,write

run=Run(API,FOLDER/'run.json');g=run.state['geometry']['male'];p=np.asarray(g['points'],np.float32)
mask=cv2.imread(str(media(g['mask'])),cv2.IMREAD_GRAYSCALE)
boundary=int(np.ceil(np.max(p[36:48,1])+38))
mask[:boundary,:]=0
path=FOLDER/'references/male/mask-v2.png';cv2.imwrite(str(path),cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
write(FOLDER/'male-reference-repair-2.json',dict(category='Mask',reason='Initial male patch added open eye shapes around the preserved closed-eye lines, giving a double-eyelid artifact. Reject it.',
    mask=str(path.relative_to(DATA)),input='FaceActing20261024/references/male/closed-guide.png',
    changes=f'Protect all pixels above y={boundary}, covering both entire original eye sockets; edit only lower cheeks, mouth and chin.',
    automaticReferenceRepairsUsed=1))
print('Entire male eye region protected for targeted repair',flush=True)

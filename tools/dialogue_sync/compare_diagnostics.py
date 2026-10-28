"""Record same-frame mouth geometry before/after QHD, for visual follow-up only."""
from run import *
import numpy as np
before=read(FOLDER/'audit-canvas.json');after=read(FOLDER/'audit-new.json');rows=[]
for clip in CLIPS:
    a=next(x for x in before['clips'] if x['clip']==clip['name']);b=next(x for x in after['clips'] if x['clip']==clip['name'])
    if a['frames']!=b['frames']:raise RuntimeError('Diagnostic timelines differ')
    for person,role in enumerate(clip['roles']):
        source=np.array([x['people'][person]['gap'] for x in a['observations']]);final=np.array([x['people'][person]['gap'] for x in b['observations']]);delta=np.abs(source-final);order=np.argsort(delta)[::-1]
        rows.append(dict(clip=clip['name'],role=role,matchedFrames=len(delta),meanGapDifference=float(delta.mean()),maxGapDifference=float(delta.max()),
            largestDifferenceFrames=[dict(frame=int(i),nativeGap=float(source[i]),finalGap=float(final[i]),absoluteDifference=float(delta[i])) for i in order[:3]]))
write(FOLDER/'qhd-mouth-diagnostics.json',dict(status='Recorded',observations=rows,scope='Same-frame normalized landmark geometry before/after QHD; diagnostic only, not phoneme accuracy or perceptual quality pass'))
print(json.dumps(rows,ensure_ascii=True))

"""Inspect actual chunk joins and largest mouth-geometry changes after QHD."""
from verify_helpers import *
s=read(FOLDER/'run.json');before=read(FOLDER/'audit-canvas.json');after=read(FOLDER/'audit-new.json');diagnostics=[]
def crop(path,index,bbox,size):
    image=cv2.resize(frame(path,index),(1280,720));x1,y1,x2,y2=bbox;length=min(max(x2-x1,y2-y1)*1.35,720);x=min(max((x1+x2-length)/2,0),1280-length);y=min(max((y1+y2-length)/2,0),720-length)
    return Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).crop((x,y,x+length,y+length)).resize((size,size),Image.Resampling.LANCZOS)
for shot in SHOTS:
    i=shot['index'];name='shot'+str(i);a=next(x for x in before['clips'] if x['clip']==name);b=next(x for x in after['clips'] if x['clip']==name)
    for person,role in enumerate(shot['roles']):
        gaps=np.array([x['people'][person]['gap'] for x in a['observations']]);final=np.array([x['people'][person]['gap'] for x in b['observations']]);delta=np.abs(gaps-final);order=np.argsort(delta)[::-1][:3]
        diagnostics.append(dict(clip=name,role=role,matchedFrames=len(delta),meanGapDifference=float(delta.mean()),maxGapDifference=float(delta.max()),largestDifferenceFrames=[dict(frame=int(v),nativeGap=float(gaps[v]),finalGap=float(final[v]),absoluteDifference=float(delta[v])) for v in order]))
        groups=[[n-1,n,n+1] for n in range(33,shot['frames']-1,33)]+[[int(v) for v in order]]
        contact=Image.new('RGB',(900,180*len(groups)),'#10151c');draw=ImageDraw.Draw(contact)
        for row,indices in enumerate(groups):
            for col,index in enumerate(indices):
                for side,path,observations,frame_i in [(0,s[f'canvas{i}Path'],a,index),(1,s['finalPath'],b,index+shot['start'])]:
                    im=crop(path,frame_i,observations['observations'][index]['people'][person]['bbox'],150);x=col*300+side*150;contact.paste(im,(x,row*180+30));draw.text((x+3,row*180+8),('PRE' if side==0 else 'FINAL')+f' f{index}',fill='white')
        contact.save(FOLDER/f'qhd-joins-{name}-{role}.png')
        index=int(order[0]);worst=Image.new('RGB',(640,352),'#10151c');draw=ImageDraw.Draw(worst)
        for side,path,obs,frame_i in [(0,s[f'canvas{i}Path'],a,index),(1,s['finalPath'],b,index+shot['start'])]:
            worst.paste(crop(path,frame_i,obs['observations'][index]['people'][person]['bbox'],320),(side*320,32));draw.text((side*320+8,10),('BEFORE QHD' if side==0 else 'FINAL')+f' f{index}',fill='white')
        worst.save(FOLDER/f'qhd-worst-{name}-{role}.png')
write(FOLDER/'qhd-mouth-diagnostics.json',dict(status='Recorded',observations=diagnostics,scope='Same-frame normalized landmark geometry; inspect actual chunk joins33/66/99/132 and three largest differences. Not phoneme accuracy, identity or perceptual quality scores.'))
print(json.dumps(diagnostics,ensure_ascii=True))

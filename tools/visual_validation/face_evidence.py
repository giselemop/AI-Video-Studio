"""CPU-only crop evidence. Detection chooses display regions, never an identity/quality score."""
from run import *
from verify import frame
import cv2
import numpy as np

sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
from identity_foundation import import_runtime
_,_,_,FaceAnalysis=import_runtime()
app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),
    providers=['CPUExecutionProvider'],allowed_modules=['detection'])
app.prepare(ctx_id=-1,det_size=(640,640),det_thresh=.4)
run=Run('http://127.0.0.1:18081',FOLDER/'run.json');run.preserve();s=run.state
report=read(FOLDER/'media-verification.json')
folder=FOLDER/'comparisons';folder.mkdir(exist_ok=True)

def roi(image):
    pixels=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2BGR)
    faces=app.get(pixels)
    if not faces:raise RuntimeError('No face detected for display crop; preserve full-frame evidence')
    face=max(faces,key=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    x1,y1,x2,y2=map(float,face.bbox);cx=(x1+x2)/2;cy=(y1+y2)/2
    size=max(x2-x1,y2-y1)*1.35
    return [round(cx-size/2),round(cy-size/2),round(cx+size/2),round(cy+size/2)]

def pair(images,boxes,path,labels):
    out=Image.new('RGB',(800,442),'#10151c');from PIL import ImageDraw
    d=ImageDraw.Draw(out)
    for i,(image,box,label) in enumerate(zip(images,boxes,labels)):
        out.paste(image.crop(box).resize((400,400),Image.Resampling.LANCZOS),(i*400,42));d.text((i*400+10,10),label,fill='white')
    out.save(path)

source=Image.open(media(s['femaleReference'])).convert('RGB');new=Image.open(media(s['keyframe1Path'])).convert('RGB')
path=folder/'face-keyframe.png';pair([source,new],[roi(source),roi(new)],path,['OLD SOURCE REFERENCE','NEW KLEIN K01'])
rows=[]
for label,before,after in [('h3',s['h3BaselinePath'],s['h3ControlledPath']),
                         ('acting',s['actingOriginalComparePath'],s['actingNewComparePath']),
                         ('qhd',s['actingNewComparePath'],s['qhdPath'])]:
    for item in report['comparisons'][label]:
        i=item['frame'];a,b=frame(before,i),frame(after,i);box_a=roi(a)
        if label=='qhd':
            sx=b.width/a.width;sy=b.height/a.height;box_b=[round(v*(sx if j%2==0 else sy)) for j,v in enumerate(box_a)]
        else:box_b=roi(b)
        path=folder/f'face-{label}-{i:03}.png';pair([a,b],[box_a,box_b],path,[f'BEFORE | frame {i}',f'NEW | frame {i}'])
        item['faceCompare']=rel(path);rows.append(dict(group=label,frame=i,sourceRoi=box_a,newRoi=box_b,
            interpretation='Source-matched ROI for QHD; independent face-centered ROIs for different framings. No identity score.'))
write(FOLDER/'face-crop-evidence.json',dict(status='Passed',device='CPU',model='existing InsightFace detection only',crops=rows,
    keyframeComparison='VisualValidation20261024/comparisons/face-keyframe.png'))
write(FOLDER/'media-verification.json',report)
print('Face display crops created from actual frames; no identity/quality score assigned')

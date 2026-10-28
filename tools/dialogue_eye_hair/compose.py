"""Source-anchored female upper face/hair; bounded speaking-mouth update only.

This fixed side-profile fallback intentionally removes female head/eye animation.
The existing male performance and all source pixels outside supports are retained.
"""
from pathlib import Path
import importlib.util,json,sys,time,os,hashlib
ROOT=Path(__file__).resolve().parents[2];DATA=(ROOT.parent/'Data').resolve()
BASE=ROOT/'tools/dialogue_stable/compose.py';BASE_SHA='8e4b8ac0722e4a71edc3b99df720cb7512ca7e8be4e6fed50a2113d0be010f5f'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Frozen stable compositor changed')
spec=importlib.util.spec_from_file_location('eye_hair_frozen',BASE);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
PROFILE='dialogue-eye-hair-guard-v1';b.PROFILE=PROFILE;d=b.d
SOURCE_SHA='0cb3a96cfdd21235dd03be897e20b58ec1963a4848acd993efc828ea13d01c37'
def validate(q):
    m,f=b.validate(q)
    if m['files']['source']['sha256']!=SOURCE_SHA or m.get('femalePolicy')!='source-eyes-hair-mouth-only':raise ValueError('Fixed reviewed side-profile source/policy required')
    if m.get('mouthEllipse')!=[360,205,26,23] or m.get('speakingSeconds')!=[.158,2.237] or m.get('fadeSeconds')!=[.08,.16]:raise ValueError('Only reviewed fixed ROI and original female cue timing allowed')
    return m,f
def gate(i):
    t=i/25
    return max(0,min(1,(t-(.158-.08))/.08,(2.237+.16-t)/.16))
def main():
    import cv2,numpy as np
    cv2.setNumThreads(1);q=json.load(sys.stdin);m,f=validate(q)
    if q.get('validateOnly'):print(json.dumps(dict(status='Passed',phase='merge')));return
    out=d.path(q['output'],False)
    if out.exists():raise FileExistsError(out)
    source=cv2.imread(str(f['source']));mouth=np.zeros((576,1024),np.uint8)
    cv2.ellipse(mouth,(360,205),(26,23),0,0,360,255,-1);mouth=cv2.GaussianBlur(mouth,(9,9),1.6)
    left=cv2.imread(str(f['leftMask']),0).astype(np.float32)/255;right=cv2.imread(str(f['rightMask']),0).astype(np.float32)/255
    centres=[]
    for a in [left,right]:
        mass=a.sum(0);centres.append(float(np.dot(mass,np.arange(1024))/mass.sum()))
    if not 0<centres[0]<centres[1]<1024 or centres[1]-centres[0]<100:raise ValueError('Role masks not separated')
    split=round(sum(centres)/2);left[:,split:]=0;right[:,:split]=0
    mouth=mouth.astype(np.float32)/255;mouth=np.minimum(mouth,left)
    # Fixed source inspection established eyes/hair outside this tiny lip ROI.
    protected=np.zeros((576,1024),bool);protected[:,:split]=mouth[:,:split]==0
    eye_box=(slice(120,170),slice(325,390))
    if np.any(mouth[eye_box]) or np.count_nonzero(mouth)<100:raise RuntimeError('Mouth mask overlaps protected eyes or is empty')
    mask_path=Path(str(out)+'.mouth-support.png');cv2.imwrite(str(mask_path),np.rint(mouth*255).astype(np.uint8))
    caps=[cv2.VideoCapture(str(f[x])) for x in ['left','right']];writer=d.encoder(q,out,1024,576,25);rows=[];started=time.monotonic()
    try:
        for i in range(151):
            frames=[]
            for cap in caps:
                ok,x=cap.read()
                if not ok:raise RuntimeError('Role frame missing')
                frames.append(x)
            male=source.astype(np.float32)+right[:,:,None]*(frames[1].astype(np.float32)-source)
            alpha=mouth*gate(i);result=male+alpha[:,:,None]*(frames[0].astype(np.float32)-source)
            pixels=np.rint(np.clip(result,0,255)).astype(np.uint8);male_pixels=np.rint(np.clip(male,0,255)).astype(np.uint8)
            if not np.array_equal(pixels[protected],source[protected]) or not np.array_equal(pixels[:,split:],male_pixels[:,split:]):raise RuntimeError('Protected source or male composite changed')
            writer.stdin.write(pixels.tobytes());rows.append(dict(frame=i,mouthGate=gate(i),femaleOutsideMouthMaxChange=0,maleCompositeMaxChange=0))
    finally:
        for cap in caps:cap.release()
        writer.stdin.close();error=writer.stderr.read();code=writer.wait()
        if code:raise RuntimeError(error.decode(errors='replace')[-600:])
    for role,p in f.items():
        if d.sha(p)!=m['files'][role]['sha256']:raise RuntimeError('Bound input changed')
    receipt=dict(status='Passed',profile=PROFILE,phase='merge',manifestSha256=q['manifestSha256'],width=1024,height=576,fps=25,frameCount=151,durationSeconds=151/25,outputPath=str(out),outputSha256=d.sha(out),cpuOnly=True,cloudCalls=0,seconds=time.monotonic()-started,frames=rows,mouthSupportPath=str(mask_path),mouthSupportSha256=d.sha(mask_path),roleSplitX=split,sourceSha256=SOURCE_SHA,policy='Female source eyes/hair/head remain fixed; only original speaking-cue mouth update with fades. Existing male animation retained. Assertions apply before lossy encoding.',femaleSideProfileBlinkDisabled=True,femaleHeadMotionDisabled=True,contentStatus='NeedReview',publicationStatus='Blocked')
    Path(str(out)+'.dialogue.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print('Passed: source-anchored eye/hair merge')
if __name__=='__main__':
    import socket
    def offline(*a,**kw):raise RuntimeError('Network disabled for local eye/hair guard')
    socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline
    os.environ['CUDA_VISIBLE_DEVICES']='';main()

"""Offline CPU dual-person merge and source-frequency retention, fixed short-pilot geometry."""
from pathlib import Path
import sys,json,importlib.util,subprocess,os,time
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[2];DATA=(ROOT.parent/'Data').resolve()
spec=importlib.util.spec_from_file_location('validated_detail',ROOT/'tools/visual_targeted/detail.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
sha,path,band=d.sha,d.path,d.band
PROFILE='dialogue-sync-compose-v1'
def validate(q):
    if Path(q['dataRoot']).resolve()!=DATA:raise ValueError('Fixed Data root required')
    manifest=path(q['manifest'])
    if sha(manifest)!=q['manifestSha256']:raise ValueError('Manifest hash drift')
    m=json.loads(manifest.read_text(encoding='utf-8-sig'));files={}
    if m.get('profile')!=PROFILE:raise ValueError('Unknown composition profile')
    for role,item in m['files'].items():
        p=path(item['path'])
        if sha(p)!=item['sha256']:raise ValueError('Bound input changed: '+role)
        files[role]=p
    if m['phase']=='merge':
        if m.get('frames')!=57 or m.get('fps')!=25 or m.get('width')!=1024 or m.get('height')!=576:raise ValueError('Fixed dual-person native specification required')
        source=cv2.imread(str(files['source']))
        if source is None or source.shape[:2]!=(576,1024):raise ValueError('Dual-person source image differs')
        for role,direction in [('left','left-right'),('right','right-left')]:
            receipt=json.loads(files[role+'Receipt'].read_text(encoding='utf-8-sig'))
            if receipt['repairProfile']!='dialogue-blink-v1' or receipt['faceDirection']!=direction or receipt['sourceSha256']!=m['files']['source']['sha256'] or receipt['faceSupportMaskSha256']!=m['files'][role+'Mask']['sha256']:raise ValueError('Role/source/mask receipt mismatch')
            v,fps,duration=d.probe(files[role],q['ffprobe'])
            if (v['width'],v['height'],int(v['nb_read_frames']),fps)!=(1024,576,57,25):raise ValueError('Dual-person take specification differs')
            mask=cv2.imread(str(files[role+'Mask']),0)
            if mask is None or mask.shape!=(576,1024) or np.count_nonzero(mask)<500:raise ValueError('Invalid role support mask')
    elif m['phase']=='detail':
        if m.get('frames') not in [48,54] or m.get('fps')!=24 or m.get('width')!=2560 or m.get('height')!=1440 or m.get('expectedFaces') not in [1,2] or m.get('strength')!=.65:raise ValueError('Fixed dialogue detail specification required')
        if m.get('maskEngineSha256')!=sha(ROOT/'tools/skin_pilot/pilot.py'):raise ValueError('Skin-mask helper changed')
        for role,geometry in [('source',(1280,720)),('restored',(2560,1440))]:
            v,fps,duration=d.probe(files[role],q['ffprobe'])
            if (v['width'],v['height'])!=geometry or int(v['nb_read_frames'])!=m['frames'] or fps!=24 or abs(duration-m['frames']/24)>1/24:raise ValueError('Matched source/restored frame timeline differs')
    else:raise ValueError('Unknown composition phase')
    return m,files
def encoder(q,p,w,h,fps):
    return subprocess.Popen([q['ffmpeg'],'-nostdin','-v','error','-n','-f','rawvideo','-pixel_format','bgr24','-video_size',f'{w}x{h}','-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','12','-pix_fmt','yuv420p','-movflags','+faststart',str(p)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
def merge(q,m,f,output):
    source=cv2.imread(str(f['source']));alphas=[cv2.imread(str(f[role+'Mask']),0).astype(np.float32)/255 for role in ['left','right']]
    centres=[]
    for a in alphas:
        mass=a.sum(0);centres.append(float(np.dot(mass,np.arange(a.shape[1]))/mass.sum()))
    if not 0<centres[0]<centres[1]<1024 or centres[1]-centres[0]<100:raise ValueError('Person role supports not separated')
    split=round(sum(centres)/2);alphas[0][:,split:]=0;alphas[1][:,:split]=0
    if np.any((alphas[0]>0)&(alphas[1]>0)):raise RuntimeError('Person masks overlap')
    caps=[cv2.VideoCapture(str(f[role])) for role in ['left','right']];writer=encoder(q,output,1024,576,25);rows=[]
    try:
        for i in range(57):
            frames=[]
            for cap in caps:
                ok,frame=cap.read()
                if not ok:raise RuntimeError('Role frame missing')
                frames.append(frame)
            out=source.astype(np.float32)
            for a,frame in zip(alphas,frames):out+=a[:,:,None]*(frame.astype(np.float32)-source)
            out=np.rint(np.clip(out,0,255)).astype(np.uint8);outside=(alphas[0]==0)&(alphas[1]==0)
            if not np.array_equal(out[outside],source[outside]):raise RuntimeError('Background outside person supports changed')
            writer.stdin.write(out.tobytes());rows.append(dict(frame=i,outsidePersonSupportMaxChange=0,roleMasksDisjoint=True))
    finally:
        for cap in caps:cap.release()
        writer.stdin.close();error=writer.stderr.read();code=writer.wait()
        if code:raise RuntimeError(error.decode(errors='replace')[-600:])
    return dict(frames=rows,splitX=split,sourceSupportCentres=centres,algorithm='Separate directional face reenactments composited into the same still; disjoint person supports; no face mixing',background='Static new reference outside animated supports')
def detail(q,m,f,output):
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68']);app.prepare(ctx_id=-1,det_size=(640,640))
    sys.path.insert(0,str(ROOT/'tools/skin_pilot'));from pilot import skin_mask
    caps=[cv2.VideoCapture(str(f[role])) for role in ['source','restored']];writer=encoder(q,output,2560,1440,24);rows=[];prior=None
    try:
        for i in range(m['frames']):
            ok,a=caps[0].read();ok2,b=caps[1].read()
            if not ok or not ok2:raise RuntimeError('Detail frame missing')
            faces=sorted(app.get(a),key=lambda v:v.bbox[0])
            if len(faces)!=m['expectedFaces']:raise RuntimeError('Face count differs; do not mix people')
            mask=np.zeros((1440,2560),np.uint8);protected=np.zeros_like(mask)
            current=[face.landmark_3d_68[:,:2]*2 for face in faces]
            if prior is not None:current=[.7*p+.3*o for p,o in zip(current,prior)]
            prior=current
            for points in current:
                skin,protect=skin_mask(b,points);mask=np.maximum(mask,skin);protected=np.maximum(protected,protect)
            mask[protected>0]=0
            if np.count_nonzero(mask)<500:raise RuntimeError('Skin support empty')
            up=cv2.resize(a,(2560,1440),interpolation=cv2.INTER_LANCZOS4);yc=cv2.cvtColor(b,cv2.COLOR_BGR2YCrCb);y=yc[:,:,0].astype(np.float32)
            source_band=band(cv2.cvtColor(up,cv2.COLOR_BGR2YCrCb)[:,:,0].astype(np.float32));before_band=band(y)
            delta=np.clip((source_band-before_band)*.65,-6,6)*(mask.astype(np.float32)/255);yc[:,:,0]=np.rint(np.clip(y+delta,0,255)).astype(np.uint8)
            replacement=cv2.cvtColor(yc,cv2.COLOR_YCrCb2BGR);out=b.copy();out[mask>0]=replacement[mask>0]
            if not np.array_equal(out[protected>0],b[protected>0]) or not np.array_equal(out[mask==0],b[mask==0]):raise RuntimeError('Eye/lip or outside-skin pixels changed')
            support=mask>200
            if np.count_nonzero(support)<100:support=mask>0
            after_band=band(cv2.cvtColor(out,cv2.COLOR_BGR2YCrCb)[:,:,0].astype(np.float32))
            rows.append(dict(frame=i,faceCount=len(faces),protectedPixelMaxChange=0,outsideSkinMaxChange=0,
                sourceBandMseBefore=float(np.mean((before_band[support]-source_band[support])**2)),sourceBandMseAfter=float(np.mean((after_band[support]-source_band[support])**2))))
            writer.stdin.write(out.tobytes())
    finally:
        for cap in caps:cap.release()
        writer.stdin.close();error=writer.stderr.read();code=writer.wait()
        if code:raise RuntimeError(error.decode(errors='replace')[-600:])
    if sha(ROOT/'tools/skin_pilot/pilot.py')!=m['maskEngineSha256']:raise RuntimeError('Mask helper drifted')
    return dict(frames=rows,algorithm='Same-frame source luminance frequency residual, protected per-person skin masks, no generated noise',metricsMeaning='Source-band proximity, not perceptual/identity or true pore score')
def main():
    cv2.setNumThreads(4);q=json.load(sys.stdin);m,f=validate(q)
    if q.get('validateOnly'):print(json.dumps(dict(status='Passed',phase=m['phase'])));return
    output=path(q['output'],False)
    if output.exists():raise FileExistsError(output)
    started=time.monotonic();result=(merge if m['phase']=='merge' else detail)(q,m,f,output)
    for role,p in f.items():
        if sha(p)!=m['files'][role]['sha256']:raise RuntimeError('Input changed during composition')
    receipt=dict(status='Passed',profile=PROFILE,phase=m['phase'],manifestSha256=q['manifestSha256'],width=m['width'],height=m['height'],fps=m['fps'],frameCount=m['frames'],durationSeconds=m['frames']/m['fps'],
        outputPath=str(output),outputSha256=sha(output),cpuOnly=True,cloudCalls=0,seconds=time.monotonic()-started,contentStatus='NeedReview',publicationStatus='Blocked',**result)
    Path(str(output)+'.dialogue.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(status='Passed',phase=m['phase'],seconds=receipt['seconds'])),flush=True)
if __name__=='__main__':
    import socket,urllib.request
    def offline(*a,**kw):raise RuntimeError('Network disabled for local dialogue composition')
    socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline;urllib.request.urlopen=offline;urllib.request.urlretrieve=offline
    os.environ['CUDA_VISIBLE_DEVICES']='';main()

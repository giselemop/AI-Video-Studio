"""CPU-only source-frequency recovery on matched frames; no invented texture."""
from pathlib import Path
import json,sys,hashlib,subprocess,time,os
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[2];DATA=(ROOT.parent/'Data').resolve()
PROFILE='source-detail-residual-v1'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def path(value,exists=True):
    p=Path(value).resolve()
    if not p.is_relative_to(DATA) or p==DATA or exists and not p.is_file():raise ValueError('Governed Data file required')
    return p
def probe(p,ffprobe):
    v=json.loads(subprocess.check_output([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
    s=next(x for x in v['streams'] if x['codec_type']=='video')
    n,d=map(int,s['avg_frame_rate'].split('/'))
    return s,n/d,float(v['format']['duration'])
def validate(q):
    if Path(q['dataRoot']).resolve()!=DATA:raise ValueError('Fixed Data root required')
    manifest=path(q['manifest'])
    if sha(manifest)!=q['manifestSha256']:raise ValueError('Manifest hash changed')
    m=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if m.get('profile')!=PROFILE or m.get('strength') not in [.65,.35]:raise ValueError('Fixed profile and strength required')
    if m.get('maskEngineSha256')!=sha(ROOT/'tools/skin_pilot/pilot.py'):raise ValueError('Frozen skin-mask helper changed')
    files={}
    for role,size in [('source',(1280,720)),('restored',(2560,1440))]:
        p=path(m[role+'Path']);files[role]=p
        if p.suffix.lower()!='.mp4' or sha(p)!=m[role+'Sha256']:raise ValueError('Input path/hash mismatch')
        s,fps,duration=probe(p,q['ffprobe'])
        if (s['width'],s['height'])!=size or fps!=24 or int(s['nb_read_frames'])!=48 or abs(duration-2)>1/24:raise ValueError('Exact matched two-second pair required')
    return m,files
def encoder(ffmpeg,p):
    return subprocess.Popen([ffmpeg,'-nostdin','-v','error','-n','-f','rawvideo','-pixel_format','bgr24','-video_size','2560x1440','-framerate','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','12','-pix_fmt','yuv420p','-movflags','+faststart',str(p)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
def band(y):return y-cv2.GaussianBlur(y,(0,0),1.6)
def compose(q,m,files):
    started=time.monotonic();output=path(q['output'],False)
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True);work=output.with_suffix('.detail-work');work.mkdir(exist_ok=False)
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
    from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    detector=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68'])
    detector.prepare(ctx_id=-1,det_size=(640,640))
    sys.path.insert(0,str(ROOT/'tools/skin_pilot'))
    from pilot import skin_mask
    caps=[cv2.VideoCapture(str(files[x])) for x in ['source','restored']]
    baseline=Path(str(output)+'.baseline.mp4');writers=[encoder(q['ffmpeg'],p) for p in [output,baseline]]
    rows=[];points=None
    try:
        for i in range(48):
            ok,a=caps[0].read();ok2,b=caps[1].read()
            if not ok or not ok2:raise RuntimeError('Matched frame decode failed')
            faces=detector.get(a)
            if not faces:raise RuntimeError('Face mask cannot be validated')
            face=max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            current=face.landmark_3d_68[:,:2]*2
            points=current if points is None else .7*current+.3*points
            up=cv2.resize(a,(2560,1440),interpolation=cv2.INTER_LANCZOS4)
            mask,protected=skin_mask(b,points);alpha=mask.astype(np.float32)/255
            if np.count_nonzero(mask)<500:raise RuntimeError('Skin support unexpectedly empty')
            yc=cv2.cvtColor(b,cv2.COLOR_BGR2YCrCb);y=yc[:,:,0].astype(np.float32)
            source_y=cv2.cvtColor(up,cv2.COLOR_BGR2YCrCb)[:,:,0].astype(np.float32)
            source_band=band(source_y);restored_band=band(y)
            delta=np.clip((source_band-restored_band)*m['strength'],-6,6)*alpha
            yc[:,:,0]=np.rint(np.clip(y+delta,0,255)).astype(np.uint8)
            corrected=cv2.cvtColor(yc,cv2.COLOR_YCrCb2BGR);out=b.copy();out[mask>0]=corrected[mask>0]
            if not np.array_equal(out[mask==0],b[mask==0]) or not np.array_equal(out[protected>0],b[protected>0]):raise RuntimeError('Protected eye/mouth or outside skin pixels changed')
            actual_band=band(cv2.cvtColor(out,cv2.COLOR_BGR2YCrCb)[:,:,0].astype(np.float32));support=mask>200
            if np.count_nonzero(support)<100:support=mask>0
            rows.append(dict(frame=i,skinPixels=int(np.count_nonzero(mask)),outsideSkinMaxChange=0,protectedPixelMaxChange=0,
                sourceBandRms=float(np.sqrt(np.mean(source_band[support]**2))),beforeBandRms=float(np.sqrt(np.mean(restored_band[support]**2))),afterBandRms=float(np.sqrt(np.mean(actual_band[support]**2))),
                beforeSourceBandMse=float(np.mean((restored_band[support]-source_band[support])**2)),afterSourceBandMse=float(np.mean((actual_band[support]-source_band[support])**2)),meanAbsAddedLuma=float(np.abs(delta[support]).mean())))
            if i in [0,12,24,36,47]:
                for name,img in [('before',b),('after',out),('mask',mask)]:cv2.imwrite(str(work/f'{name}-{i:03}.png'),img)
            for process,img in zip(writers,[out,b]):process.stdin.write(img.tobytes())
    finally:
        for cap in caps:cap.release()
        for process in writers:
            process.stdin.close();error=process.stderr.read();code=process.wait()
            if code:raise RuntimeError('Video encoding failed: '+error.decode(errors='replace')[-500:])
    for role,p in files.items():
        if sha(p)!=m[role+'Sha256']:raise RuntimeError('Input changed during composition')
    if sha(ROOT/'tools/skin_pilot/pilot.py')!=m['maskEngineSha256']:raise RuntimeError('Mask helper changed during composition')
    receipt=dict(status='Passed',profile=PROFILE,manifestSha256=q['manifestSha256'],cpuOnly=True,cloudCalls=0,
        algorithm='Bounded luminance high-frequency difference from same-frame source, source-aligned skin mask, existing 68-point CPU landmarks',
        strength=m['strength'],sourceFiles={role:dict(path=str(p),sha256=sha(p)) for role,p in files.items()},
        frames=rows,width=2560,height=1440,fps=24,frameCount=48,durationSeconds=2,
        metricsMeaning='Frequency proximity to the source, not recovered real pores, identity, or perceptual quality score',
        protection='Eyes, mouth, nose centre and outside skin bit-identical to restored input before lossy encode; both outputs receive same encode',
        outputPath=str(output),outputSha256=sha(output),baselinePath=str(baseline),baselineSha256=sha(baseline),seconds=time.monotonic()-started,
        contentStatus='NeedReview',publicationStatus='Blocked')
    Path(str(output)+'.detail.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='Passed',frames=48,seconds=receipt['seconds'])),flush=True)
if __name__=='__main__':
    os.environ['CUDA_VISIBLE_DEVICES']='';cv2.setNumThreads(4)
    import socket,urllib.request
    def offline(*args,**kwargs):raise RuntimeError('Network disabled during local detail validation/inference')
    socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline
    urllib.request.urlopen=offline;urllib.request.urlretrieve=offline
    q=json.load(sys.stdin);m,files=validate(q)
    if q.get('validateOnly'):print(json.dumps(dict(status='Passed',frames=48,profile=PROFILE)))
    else:compose(q,m,files)

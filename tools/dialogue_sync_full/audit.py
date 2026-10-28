"""CPU geometry/audio timing diagnostics, never a phoneme or aesthetic score."""
from run import *
import cv2,numpy as np

def decode_wave(path):
    raw=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-ac','1','-ar','24000','-f','f32le','pipe:1'])
    return np.frombuffer(raw,dtype='<f4'),24000

def main(version):
    s=read(FOLDER/'run.json');sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    for name in ['det_10g.onnx','1k3d68.onnx']:
        if not (ROOT.parent/'Models/InsightFace/models/buffalo_l'/name).is_file():raise RuntimeError('Existing analysis weights required; no downloads')
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68']);app.prepare(ctx_id=-1,det_size=(640,640))
    if any(m.session.get_providers()!=['CPUExecutionProvider'] for m in app.models.values()):raise RuntimeError('CPU-only observation required')
    reports=[]
    for clip in SHOTS:
        name='shot'+str(clip['index']);path=s['inputs']['original'] if version=='baseline' else s['finalPath'] if version=='new' else s[f"canvas{clip['index']}Path"];cap=cv2.VideoCapture(str(media(path)));rows=[]
        if version!='canvas':cap.set(cv2.CAP_PROP_POS_FRAMES,clip['start'])
        audio={role:decode_wave(media(s['inputs'][role+'Audio'])) for role in clip['roles']}
        for i in range(clip['frames']):
            ok,image=cap.read()
            if not ok:raise RuntimeError('Missing decoded pilot frame')
            image=cv2.resize(image,(1280,720));faces=sorted(app.get(image),key=lambda x:x.bbox[0])
            if len(faces)!=len(clip['roles']):raise RuntimeError('Expected roles cannot be detected at '+name+':'+str(i))
            values=[]
            for role,face in zip(clip['roles'],faces):
                points=np.asarray(face.landmark_3d_68)[:,:2];width=max(float(np.linalg.norm(points[60]-points[64])),1e-5)
                gap=float(np.mean([np.linalg.norm(points[a]-points[b]) for a,b in [(61,67),(62,66),(63,65)]])/width)
                wave,sr=audio[role];offset=round((clip['start']+i)*sr/24);samples=wave[offset:round((clip['start']+i+1)*sr/24)]
                rms=float(np.sqrt(np.mean(samples**2)));values.append(dict(role=role,gap=gap,rms=rms,faceWidth=float(face.bbox[2]-face.bbox[0]),bbox=[float(x) for x in face.bbox],mouthCentre=[float(x) for x in points[48:68].mean(0)]))
            rows.append(dict(frame=i,globalFrame=clip['start']+i,seconds=i/24,people=values))
        cap.release();summaries=[]
        for person,role in enumerate(clip['roles']):
            gaps=np.array([row['people'][person]['gap'] for row in rows]);rms=np.array([row['people'][person]['rms'] for row in rows]);threshold=max(float(np.percentile(rms,95))*.08,.002)
            active=rms>threshold;active=np.convolve(active.astype(int),[1,1,1],mode='same')>0
            lag=[]
            for shift in range(-6,7):
                a=gaps[max(0,shift):len(gaps)+min(0,shift)];b=rms[max(0,-shift):len(rms)-max(0,shift)]
                corr=float(np.corrcoef(a,b)[0,1]) if np.std(a)>1e-6 and np.std(b)>1e-6 else None
                lag.append(dict(mouthDelayFrames=shift,correlation=corr))
            valid=[x for x in lag if x['correlation'] is not None];best=max(valid,key=lambda x:x['correlation']) if valid else None
            summaries.append(dict(role=role,activeFrames=int(active.sum()),inactiveFrames=int((~active).sum()),
                meanActiveGap=float(gaps[active].mean()) if active.any() else None,meanInactiveGap=float(gaps[~active].mean()) if (~active).any() else None,
                inactiveGapP95=float(np.percentile(gaps[~active],95)) if (~active).any() else None,
                meanAdjacentGapChange=float(np.abs(np.diff(gaps)).mean()),maxAdjacentGapChange=float(np.abs(np.diff(gaps)).max()),
                coarseBestEnvelopeLag=best,lagGrid=lag,rmsThreshold=threshold))
        reports.append(dict(clip=name,path=path,sha256=sha(media(path)),frames=clip['frames'],summary=summaries,observations=rows))
    write(FOLDER/f'audit-{version}.json',dict(status='Recorded',version=version,provider='CPUExecutionProvider',clips=reports,
        scope='Inner-lip landmark gap and separated original dry-voice RMS; energy lag is a coarse diagnostic, not phoneme synchronization or expression naturalness accuracy'))
    print(json.dumps({c['clip']:c['summary'] for c in reports},ensure_ascii=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',choices=['baseline','canvas','new'],required=True);main(p.parse_args().version)

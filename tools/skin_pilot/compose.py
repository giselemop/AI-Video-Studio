"""CPU-only, occlusion-aware transport of skin-detail residuals; never transports the face RGB."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def resolve(root,path):
    value=(root/path).resolve(strict=True)
    if not value.is_relative_to(root) or not value.is_file():raise ValueError('A manifest path leaves Data')
    return value


def validate(request):
    root=Path(request['dataRoot']).resolve(strict=True)
    path=resolve(root,request['manifest'])
    if path.suffix!='.json' or path.stat().st_size>150000:raise ValueError('Invalid manifest file')
    if sha(path)!=request['manifestSha256'].lower():raise ValueError('Manifest SHA256 changed')
    m=load(path)
    if m.get('schemaVersion')!=1 or m.get('purpose')!='LocalSkinPilot2s':raise ValueError('Unknown skin manifest')
    if [m.get(k) for k in ['startFrame','frameCount','fps','width','height']]!=[5,48,24,2560,1440]:
        raise ValueError('Only the approved 48-frame single-shot pilot is supported')
    if m.get('keyframes')!=[0,12,24,36,47] or m.get('attempt') not in [1,2,3]:raise ValueError('Keyframe/attempt bounds')
    if not isinstance(m.get('blend'),(float,int)) or not math.isfinite(m['blend']) or not .1<=m['blend']<=.85:
        raise ValueError('Skin blend outside finite .1-.85 bounds')
    roi=m.get('roi',[])
    if len(roi)!=4 or any(type(v)!=int for v in roi):raise ValueError('ROI must contain four integers')
    x,y,w,h=roi
    if min(x,y)<0 or w!=h or not 256<=w<=1024 or x+w>2560 or y+h>1440:raise ValueError('Invalid bounded face ROI')
    files=m.get('files',[])
    if not isinstance(files,list) or not 150<=len(files)<=170:raise ValueError('Incomplete bound input files')
    paths={}
    for item in files:
        name=item['path'];p=resolve(root,name)
        if name in paths or sha(p)!=item['sha256']:raise ValueError('Duplicate or changed input file: '+name)
        paths[name]=p
    for key in ['originalPath','qhdPath','landmarksPath']:
        if m[key] not in paths:raise ValueError('Source not included in frozen files')
    for record in m['frames']:
        if set(record)!=set(['image','mask','protected']) or any(p not in paths for p in record.values()):
            raise ValueError('Incomplete original frame/mask/eye-mouth protection')
    if len(m['frames'])!=48 or set(m['keys'])!=set(map(str,m['keyframes'])):raise ValueError('Frame manifest mismatch')
    for record in m['keys'].values():
        if any(record[k] not in paths for k in ['input','generated']):raise ValueError('Unbound local diffusion key')
    for key,width,height in [('originalPath',1280,720),('qhdPath',2560,1440)]:
        cap=cv2.VideoCapture(str(paths[m[key]]))
        spec=[int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
              cap.get(cv2.CAP_PROP_FPS),int(cap.get(cv2.CAP_PROP_FRAME_COUNT))]
        cap.release()
        if spec!=[width,height,24,240]:raise ValueError('Bound original source geometry changed')
    return root,m,paths


def warp(value,flow):
    h,w=flow.shape[:2]
    xx,yy=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32))
    return cv2.remap(value,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)


def encode(ffmpeg,frames,width,height,path):
    command=[ffmpeg,'-hide_banner','-loglevel','error','-n','-f','rawvideo','-pix_fmt','bgr24','-s',f'{width}x{height}',
             '-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','medium','-crf','12','-pix_fmt','yuv420p',
             '-threads','4','-movflags','+faststart',str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for frame in frames:process.stdin.write(np.ascontiguousarray(frame).tobytes())
        process.stdin.close()
        error=process.stderr.read().decode('utf-8',errors='replace')
        if process.wait(timeout=240)!=0:raise RuntimeError('Local video encode failed: '+error[-1200:])
    except BaseException:
        process.kill();process.wait();raise


def original_frames(path):
    cap=cv2.VideoCapture(str(path))
    try:
        for index in range(53):
            ok,frame=cap.read()
            if not ok:raise RuntimeError('Original clip decode failed')
            if index>=5:yield frame
    finally:cap.release()


def compose(request,root,m,paths):
    started=time.monotonic()
    output=Path(request['output']).resolve()
    if not output.is_relative_to(root) or output.exists():raise ValueError('New staged output within Data required')
    output.parent.mkdir(parents=True,exist_ok=True)
    work=output.parent/'skin-work'
    work.mkdir(exist_ok=False)
    x,y,size,_=m['roi']
    flow_size=448
    gray=[];masks=[];checks=[]
    source_cap=cv2.VideoCapture(str(paths[m['qhdPath']]))
    for _ in range(5):source_cap.read()
    for index,record in enumerate(m['frames']):
        frame=cv2.imread(str(paths[record['image']]))
        mask=cv2.imread(str(paths[record['mask']]),cv2.IMREAD_GRAYSCALE)
        protect=cv2.imread(str(paths[record['protected']]),cv2.IMREAD_GRAYSCALE)
        ok,actual=source_cap.read()
        if not ok or frame is None or frame.shape!=(1440,2560,3) or not np.array_equal(frame,actual):
            raise ValueError('Frame PNG is not the bound QHD source frame')
        if mask.shape!=(1440,2560) or protect.shape!=mask.shape or np.any(mask[protect>0]):
            raise ValueError('Skin mask overlaps protected eyes/lips')
        if np.count_nonzero(mask)<2000 or np.count_nonzero(mask)>size*size*.8:
            raise ValueError('Skin support is implausible')
        # Only the mask/ROI intersection is eligible. Peripheral mask pixels
        # outside the key patch remain source pixels, never stretched or filled.
        gray.append(cv2.resize(cv2.cvtColor(frame[y:y+size,x:x+size],cv2.COLOR_BGR2GRAY),
                               (flow_size,flow_size),interpolation=cv2.INTER_AREA))
        masks.append(mask[y:y+size,x:x+size].astype(np.float32)/255)
    source_cap.release()
    forward=[];backward=[]
    for i in range(47):
        kwargs=dict(pyr_scale=.5,levels=4,winsize=25,iterations=4,poly_n=7,poly_sigma=1.5,flags=0)
        forward.append(cv2.calcOpticalFlowFarneback(gray[i],gray[i+1],None,**kwargs))
        backward.append(cv2.calcOpticalFlowFarneback(gray[i+1],gray[i],None,**kwargs))
    key_residuals={}
    for index in m['keyframes']:
        record=m['keys'][str(index)]
        original=cv2.imread(str(paths[record['input']])).astype(np.float32)
        generated=cv2.imread(str(paths[record['generated']])).astype(np.float32)
        if original.shape!=(768,768,3) or generated.shape!=original.shape:raise ValueError('Unexpected key patch size')
        delta=generated-original
        low=cv2.GaussianBlur(delta,(0,0),5.0)
        # Keep texture while limiting diffusion-induced changes to tone and face shading.
        detail=np.clip(delta-low,-12,12)+np.clip(low,-2.0,2.0)*.25
        detail=cv2.resize(detail,(size,size),interpolation=cv2.INTER_CUBIC)
        detail*=masks[index][:,:,None]
        key_residuals[index]=detail
    def advance(residual,confidence,source,target):
        flow=backward[source] if target==source+1 else forward[target]
        reverse=forward[source] if target==source+1 else backward[target]
        error=np.linalg.norm(flow+warp(reverse,flow),axis=2)
        photo=np.abs(gray[target].astype(np.float32)-warp(gray[source],flow).astype(np.float32))
        reliability=np.exp(-error**2/3.0)*np.exp(-photo/20)
        full_flow=cv2.resize(flow,(size,size),interpolation=cv2.INTER_LINEAR)*(size/flow_size)
        result=warp(residual,full_flow)
        conf=warp(confidence,full_flow)*cv2.resize(reliability,(size,size),interpolation=cv2.INTER_LINEAR)
        # Stop at disocclusions and at the target's protected region.
        conf*=masks[target]
        return result,conf
    for left,right in zip(m['keyframes'][:-1],m['keyframes'][1:]):
        left_states={left:(key_residuals[left],masks[left].copy())}
        r,c=left_states[left]
        for i in range(left+1,right+1):
            r,c=advance(r,c,i-1,i)
            left_states[i]=(r,c)
        right_states={right:(key_residuals[right],masks[right].copy())}
        r,c=right_states[right]
        for i in range(right-1,left-1,-1):
            r,c=advance(r,c,i+1,i)
            right_states[i]=(r,c)
        for i in range(left,right+(1 if right==47 else 0)):
            u=(i-left)/(right-left)
            wl=.5+.5*math.cos(math.pi*u);wr=1-wl
            lr,lc=left_states[i];rr,rc=right_states[i]
            weight=wl*lc+wr*rc
            residual=(lr*(wl*lc)[:,:,None]+rr*(wr*rc)[:,:,None])/np.maximum(weight[:,:,None],1e-6)
            # Drop unreliable flow instead of stretching texture through an occlusion.
            coverage=np.clip(weight*1.6,0,1)*masks[i]
            residual*=coverage[:,:,None]*m['blend']
            np.save(work/f'residual-{i:03}.npy',residual.astype(np.float16))
        del left_states,right_states
    per_frame=[]
    def optimized_frames():
        for i,record in enumerate(m['frames']):
            frame=cv2.imread(str(paths[record['image']]))
            mask=cv2.imread(str(paths[record['mask']]),cv2.IMREAD_GRAYSCALE)
            protected=cv2.imread(str(paths[record['protected']]),cv2.IMREAD_GRAYSCALE)>0
            result=frame.copy()
            residual=np.load(work/f'residual-{i:03}.npy').astype(np.float32)
            patch=np.rint(np.clip(frame[y:y+size,x:x+size].astype(np.float32)+residual,0,255)).astype(np.uint8)
            result[y:y+size,x:x+size]=patch
            # These are hard compositing invariants, checked on all 48 actual frames.
            if not np.array_equal(result[mask==0],frame[mask==0]) or not np.array_equal(result[protected],frame[protected]):
                raise RuntimeError('Protected original pixels changed')
            delta=np.abs(result.astype(np.int16)-frame.astype(np.int16))
            per_frame.append(dict(frame=i,changedPixels=int(np.count_nonzero(np.any(delta,axis=2))),
                skinMeanAbsoluteChange=float(np.mean(delta[mask>0])),protectedPixelMaxChange=int(delta[protected].max()),
                outsideSkinMaxChange=int(delta[mask==0].max())))
            if i in [0,6,12,18,24,30,36,42,47]:cv2.imwrite(str(work/f'optimized-{i:03}.png'),result)
            yield result
    optimized_picture=work/'optimized-picture.mp4'
    encode(request['ffmpeg'],optimized_frames(),2560,1440,optimized_picture)
    qhd_picture=work/'qhd-picture.mp4'
    encode(request['ffmpeg'],(cv2.imread(str(paths[r['image']])) for r in m['frames']),2560,1440,qhd_picture)
    original_picture=work/'original-picture.mp4'
    encode(request['ffmpeg'],original_frames(paths[m['originalPath']]),1280,720,original_picture)
    source_probe=json.loads(subprocess.check_output([request['ffprobe'],'-v','error','-show_streams','-of','json',
        str(paths[m['originalPath']])],text=True))
    audio_stream=next(s for s in source_probe['streams'] if s['codec_type']=='audio')
    sample_rate=int(audio_stream['sample_rate'])
    if audio_stream['channels']!=1 or not 8000<=sample_rate<=48000:raise ValueError('Expected bounded mono original audio')
    start_sample=round(m['startFrame']/m['fps']*sample_rate)
    sample_count=2*sample_rate
    pcm=work/'original-voice.wav'
    subprocess.run([request['ffmpeg'],'-hide_banner','-loglevel','error','-n','-i',str(paths[m['originalPath']]),
        '-map','0:a:0','-af',f'atrim=start_sample={start_sample}:end_sample={start_sample+sample_count},asetpts=PTS-STARTPTS',
        '-c:a','pcm_s16le',str(pcm)],check=True,timeout=90)
    audio=work/'shared-audio.m4a'
    subprocess.run([request['ffmpeg'],'-hide_banner','-loglevel','error','-n','-i',str(pcm),'-c:a','aac','-b:a','192k',str(audio)],check=True,timeout=90)
    for picture,path in [(optimized_picture,output),(original_picture,Path(str(output)+'.original.mp4')),
                         (qhd_picture,Path(str(output)+'.qhd.mp4'))]:
        subprocess.run([request['ffmpeg'],'-hide_banner','-loglevel','error','-n','-i',str(picture),'-i',str(audio),
            '-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(path)],check=True,timeout=90)
        final_probe=json.loads(subprocess.check_output([request['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)],text=True))
        if abs(float(final_probe['format']['duration'])-2)>1/24 or any(abs(float(s['duration'])-2)>1/24 for s in final_probe['streams']):
            raise RuntimeError('Container or audio stream exceeds the exact two-second picture timeline')
    receipt=dict(status='Passed',contentReview='NeedReview',manifestSha256=request['manifestSha256'],
        algorithm='Masked SDXL original-conditioned keys; bidirectional optical-flow residual transport with occlusion confidence; cosine anchor blend',
        originalVoice='One sample-exact excerpt decoded at the original audio sample rate; one shared AAC encode packet-copied into all three variants',
        audioSampleRate=sample_rate,audioStartSample=start_sample,audioSampleCount=sample_count,
        audioStartRoundingSeconds=start_sample/sample_rate-m['startFrame']/m['fps'],
        generatedKeyframes=m['keyframes'],attempt=m['attempt'],blend=m['blend'],roi=m['roi'],frameCount=48,fps=24,
        protectedRegion='All unmasked pixels, eyebrows, eyes, nose centre, lips and teeth unchanged before delivery encoding',
        diffusionNotAppliedToMouth=True,encoding='One picture encode each, libx264 CRF12 yuv420p; lossy delivery may alter individual pixel values',
        cpuOnly=True,seconds=time.monotonic()-started,frames=per_frame,sourceFiles=m['files'],
        outputs=[dict(path=str(p.relative_to(root)),sha256=sha(p)) for p in [output,Path(str(output)+'.original.mp4'),Path(str(output)+'.qhd.mp4')]])
    Path(str(output)+'.skin.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='Passed',frames=48,seconds=receipt['seconds'])),flush=True)


def main():
    cv2.setNumThreads(4)
    request=json.load(sys.stdin)
    root,m,paths=validate(request)
    if request.get('validateOnly'):
        print(json.dumps(dict(status='Passed',boundFiles=len(paths),frames=48)),flush=True)
    else:compose(request,root,m,paths)


if __name__=='__main__':main()

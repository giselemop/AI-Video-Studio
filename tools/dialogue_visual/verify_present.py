"""Actual final decode, original voice equality, cut continuity and honest comparison."""
from run import *
import hashlib,cv2,numpy as np
from PIL import Image,ImageDraw
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe';FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'
def probe(p):return json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
def frame(p,i):
    cap=cv2.VideoCapture(str(media(p)));cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Missing actual comparison frame')
    return pixels
def inspect(p,w,h,fps,n,unique=False):
    path=media(p);result=subprocess.run([FFMPEG,'-nostdin','-v','error','-i',str(path),'-map','0:v:0','-f','null','-'],capture_output=True,text=True)
    if result.returncode or result.stderr.strip():raise RuntimeError('Complete video decode failed')
    info=probe(path);v=next(x for x in info['streams'] if x['codec_type']=='video');num,den=map(int,v['avg_frame_rate'].split('/'))
    if (v['width'],v['height'],int(v['nb_read_frames']))!=(w,h,n) or abs(num/den-fps)>.001 or abs(float(info['format']['duration'])-n/fps)>1/fps:raise RuntimeError('Actual output specification differs')
    value=dict(status='Passed',path=p,sha256=sha(path),width=w,height=h,fps=fps,frames=n,seconds=n/fps)
    if unique:
        cap=cv2.VideoCapture(str(path));hashes=[]
        while True:
            ok,pixels=cap.read()
            if not ok:break
            hashes.append(hashlib.sha256(pixels.tobytes()).hexdigest())
        cap.release()
        if len(hashes)!=n or len(set(hashes))!=n:raise RuntimeError('Final has duplicate or missing decoded frames')
        value['uniqueDecodedFrames']=len(set(hashes))
    return value
def audio(p,packets=True):
    args=['-c:a','copy','-f','data','pipe:1'] if packets else ['-f','s16le','-acodec','pcm_s16le','pipe:1']
    return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:a:0']+args)
def video_packets(p):return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:v:0','-c:v','copy','-f','data','pipe:1'])

def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.preserve();s=r.state;checks={}
    for i,n in [(1,53),(2,43),(3,144)]:
        for prefix,w,h in [('canvas',1280,720),('qhd',2560,1440),('detail',2560,1440)]:checks[f'{prefix}{i}']=inspect(s[f'{prefix}{i}Path'],w,h,24,n)
        receipt=read(media(s[f'detail{i}ReceiptPath']))
        if len(receipt['frames'])!=n or any(x['protectedPixelMaxChange'] or x['outsideSkinMaxChange'] or x['faceCount']!=(2 if i==3 else 1) for x in receipt['frames']):raise RuntimeError('Per-frame face/skin protection not verified')
    checks['final']=inspect(s['finalPath'],2560,1440,24,240,True)
    final_probe=probe(media(s['finalPath']))
    if not any(x['codec_type']=='audio' for x in final_probe['streams']) or any(abs(float(x['duration'])-10)>1/24 for x in final_probe['streams']):raise RuntimeError('Final audio/video duration differs')
    packet=audio(s['finalPath']);pcm=audio(s['finalPath'],False)
    if packet!=audio(s['inputs']['original']) or pcm!=audio(s['inputs']['original'],False):raise RuntimeError('Original audio packets or decoded PCM changed')
    image_packets=video_packets(s['finalPath'])
    if image_packets!=video_packets(s['picturePath']):raise RuntimeError('Final audio remux changed video packets')
    cuts=[]
    for global_i,index,local_i in [(51,1,51),(52,1,52),(53,2,0),(54,2,1),(94,2,41),(95,2,42),(96,3,0),(97,3,1)]:
        a=frame(s['finalPath'],global_i)[:1150].astype(np.float32);b=frame(s[f'detail{index}Path'],local_i)[:1150].astype(np.float32);mad=float(np.abs(a-b).mean())
        if mad>8:raise RuntimeError('Cut/source correspondence differs beyond encoding tolerance')
        cuts.append(dict(finalFrame=global_i,sourceShot=index,sourceFrame=local_i,meanAbsolutePixelDifference=mad))
    for role,n,direction in [('female',57,'large-small'),('male',46,'large-small'),('wideFemale',151,'left-right'),('wideMale',151,'right-left')]:
        receipt=read(media(s[role+'ReceiptPath']))
        if receipt['repairProfile']!='dialogue-blink-v1' or receipt['faceDirection']!=direction or len(receipt['eyeCorrectionFrames'])!=n or any(x['outsideEyeMaxChange'] for x in receipt['eyeCorrectionFrames']):raise RuntimeError('Selected acting trace differs')
    merge=read(media(s['wideMergeReceiptPath']))
    if len(merge['frames'])!=151 or any(not x['roleMasksDisjoint'] or x['outsidePersonSupportMaxChange'] for x in merge['frames']):raise RuntimeError('Two-person isolation differs')
    changed=[];inventory=read(FOLDER/'model-inventory.json')['files']
    for item in inventory:
        p=ROOT.parent/'Models'/item['path']
        if not p.exists() or p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:changed.append(item['path'])
    if changed:raise RuntimeError('Existing model directory metadata changed')
    history=read(FOLDER/'keyframe-live-history.json');provenance=[]
    for field in ['keyframe2TaskId','keyframe3TaskId','keyframe3RepairTaskId']:
        task=s[field];matches=[]
        for prompt_id,entry in history.items():
            outputs=[x for node in entry.get('outputs',{}).values() for x in node.get('images',[]) if f'task_{task}_' in x.get('filename','')]
            if outputs:matches.append((prompt_id,entry,outputs))
        if len(matches)!=1 or matches[0][1].get('status',{}).get('status_str')!='success':raise RuntimeError('New keyframe Comfy history not uniquely successful')
        expected=s['keyframe2Sha256'] if field=='keyframe2TaskId' else s['keyframe3Sha256'] if field=='keyframe3TaskId' else s['wideSelectedSha256']
        raw_hashes=[]
        for item in matches[0][2]:
            p=(ROOT.parent/'ComfyUI/output'/item.get('subfolder','')/item['filename']).resolve()
            if not p.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise RuntimeError('Raw Comfy path outside root')
            raw_hashes.append(sha(p))
        if expected not in raw_hashes:raise RuntimeError('Published keyframe differs from raw output')
        provenance.append(dict(taskId=task,promptId=matches[0][0],status='success',rawPublishedHashMatched=True))
    write(FOLDER/'final-verification.json',dict(status='Passed',videos=checks,cutFrames=[53,96],cutSourceMatches=cuts,audioPacketsEqual=True,audioPcmEqual=True,
        audioPacketSha256=hashlib.sha256(packet).hexdigest(),audioPcmSha256=hashlib.sha256(pcm).hexdigest(),sourceHashesPreserved=True,
        finalPictureVideoPacketsUnchanged=True,videoPacketSha256=hashlib.sha256(image_packets).hexdigest(),
        modelMetadataFilesUnchanged=len(inventory),modelScope='Size/mtime unchanged, not all old weights rehashed',keyframeProvenance=provenance,
        eyeAndSkinProtection='Passed before recorded pasteback/resampling/encoding stages; no final pixel-invariance claim',contentStatus='NeedReview',publicationStatus='Blocked'))
    # CPU face detection only positions the viewer and stills; it is not identity scoring.
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection']);app.prepare(ctx_id=-1,det_size=(640,640))
    paths=[s['inputs']['original'],s['finalPath']];origins=[]
    def faces_for(pixels):
        small=cv2.resize(pixels,(1280,720));faces=sorted(app.get(small),key=lambda f:f.bbox[0])
        if not faces:raise RuntimeError('Viewer face position not available')
        return small,faces
    for path in paths:
        values=[]
        for i,wide in [(19,False),(77,False),(127,True)]:
            image,faces=faces_for(frame(path,i))
            if wide and len(faces)!=2:raise RuntimeError('Two-person viewer positions not available')
            first=faces[0] if wide else max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            def centre(f):return [float((f.bbox[0]+f.bbox[2])/2/1280),float((f.bbox[1]+f.bbox[3])/2/720)]
            values.append(dict(primary=centre(first),male=centre(faces[-1]) if wide else centre(first)))
        origins.append(values)
    comparison=FOLDER/'comparisons';comparison.mkdir(exist_ok=True);moments=[]
    for i,label,role in [(9,'眨眼关键帧','female'),(19,'女方近景','female'),(53,'第一处切点','male'),(77,'男方回应','male'),(96,'第二处切点','female'),(127,'女方让步','female'),(168,'男方收尾','male'),(239,'末帧','female')]:
        out=Image.new('RGB',(800,436),'#10151c');draw=ImageDraw.Draw(out)
        for col,path in enumerate(paths):
            image,faces=faces_for(frame(path,i))
            if i>=96 and len(faces)!=2:raise RuntimeError('Two-person still cannot be safely localized')
            face=faces[-1] if i>=96 and role=='male' else faces[0] if i>=96 else max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            x1,y1,x2,y2=face.bbox;size=min(max(x2-x1,y2-y1)*1.35,720);x=min(max((x1+x2-size)/2,0),1280-size);y=min(max((y1+y2-size)/2,0),720-size)
            im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).crop((x,y,x+size,y+size)).resize((400,400),Image.Resampling.LANCZOS)
            out.paste(im,(400*col,36));draw.text((400*col+10,10),('PREVIOUS' if col==0 else 'NEW')+f' | frame{i} | {i/24:.3f}s',fill='white')
        p=comparison/f'compare-{i:03}.png';out.save(p);moments.append(dict(frame=i,label=label,compare=rel(p)))
    metadata=dict(technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',intro='十秒三镜头新版本已完成文件核验：原四句对白、完整原声、字幕及镜头切点保持。支持正常/半速、声音切换与逐帧前后对比。',paths=paths,seconds=10,frames=240,fps=24,cutFrames=[53,96],origins=origins,moments=moments)
    write(ROOT/'web/public/dialogue-visual.json',metadata)
    for name in ['dialogue-visual.html','dialogue-visual.json']:
        shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
        if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Published preview differs')
    write(FOLDER/'preview-publication.json',dict(status='Passed',url='http://127.0.0.1:18080/dialogue-visual.html',htmlSha256=sha(ROOT/'web/dist/dialogue-visual.html'),metadataSha256=sha(ROOT/'web/dist/dialogue-visual.json')))
    print('Passed: full decode,240unique frames,original AAC/PCM,cut correspondence,role/skin protection and source preservation; comparison published')
if __name__=='__main__':main()

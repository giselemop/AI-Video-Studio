"""Actual local decode/audio/clock/caption evidence and a reviewable comparison."""
from run import *
import hashlib,math,cv2,numpy as np,shutil
from PIL import Image,ImageDraw
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe';FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'
def probe(p):return json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(media(p))]))
def frame(p,i):
    cap=cv2.VideoCapture(str(media(p)));cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Missing decoded frame')
    return pixels
def inspect(p,w,h,fps,n,unique=False):
    info=probe(p);v=next(x for x in info['streams'] if x['codec_type']=='video');rate=tuple(map(int,v['avg_frame_rate'].split('/')))
    if (v['width'],v['height'],int(v['nb_read_frames']))!=(w,h,n) or abs(rate[0]/rate[1]-fps)>.001 or abs(float(v['duration'])-n/fps)>.001:raise RuntimeError('Video geometry/timeline differs')
    result=subprocess.run([FFMPEG,'-nostdin','-v','error','-i',str(media(p)),'-map','0:v:0','-f','null','-'],capture_output=True)
    if result.returncode or result.stderr.strip():raise RuntimeError('Complete decode failed')
    row=dict(path=p,sha256=sha(media(p)),width=w,height=h,fps=fps,frames=n,seconds=n/fps,status='Passed')
    if unique:
        cap=cv2.VideoCapture(str(media(p)));hashes=[]
        while True:
            ok,x=cap.read()
            if not ok:break
            hashes.append(hashlib.sha256(x.tobytes()).hexdigest())
        cap.release()
        if len(hashes)!=n or len(set(hashes))!=n:raise RuntimeError('Duplicated/missing decoded frames')
        row['uniqueDecodedFrames']=len(set(hashes))
    return row
def payload(p,stream='a:0',pcm=False):
    args=['-f','s16le','-acodec','pcm_s16le'] if pcm else ['-c','copy','-f','data']
    return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:'+stream]+args+['pipe:1'])
def audio_timeline(p):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-select_streams','a:0','-show_packets','-show_entries','packet=pts_time,dts_time,duration_time,flags:packet_side_data=side_data_type,skip_samples,discard_padding','-of','json',str(media(p))]))['packets']
def captions(s):
    def seconds(value):
        h,m,t=value.split(':');sec,ms=t.split(',');return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
    cues=[]
    for block in media(s['inputs']['subtitle']).read_text(encoding='utf-8-sig').strip().split('\n\n'):
        lines=block.splitlines();a,b=map(seconds,lines[1].split(' --> '));start=math.ceil(a*24);end=math.ceil(b*24)
        cues.append(dict(text='\n'.join(lines[2:]),start=a,end=b,samples=sorted(set([start,(start+end-1)//2,end-1]))))
    if len(cues)!=4:raise RuntimeError('Original four cues required')
    indices=sorted({i for c in cues for i in c['samples']});escaped=str(media(s['inputs']['subtitle'])).replace('\\','/').replace(':',r'\:').replace("'",r"\'");select='+'.join(rf'eq(n\,{i})' for i in indices)
    raw=subprocess.check_output([FFMPEG,'-nostdin','-v','error','-f','lavfi','-i','color=c=black:s=1366x768:r=24:d=10','-vf',f"subtitles='{escaped}',select='{select}'",'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','pipe:1'])
    masks=np.frombuffer(raw,dtype=np.uint8).reshape((-1,768,1366));rows=[]
    if len(masks)!=len(indices):raise RuntimeError('Caption renderer timeline differs')
    for i,mask in zip(indices,masks):
        core=mask>=max(int(mask.max())-3,220);gray=cv2.cvtColor(frame(s['finalPath'],i),cv2.COLOR_BGR2GRAY);ratio=float((gray[core]>190).mean())
        if core.sum()<40 or ratio<.9:raise RuntimeError('Caption glyph core missing')
        rows.append(dict(frame=i,expectedCorePixels=int(core.sum()),brightGlyphCoreFraction=ratio))
    write(FOLDER/'caption-render-checks.json',dict(status='Passed',subtitleSha256=sha(media(s['inputs']['subtitle'])),cues=cues,samples=rows,scope='Original SRT,12 first/middle/last cue samples at768; no OCR or pixel-invariance claim'))
def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state;videos={};controls=[]
    if read(FOLDER/'repeatability.json')['status']!='Passed':raise RuntimeError('Repetition check missing')
    for role,n in [('female_close',57),('male_close',46),('female_wide',151),('male_wide',151)]:
        key='v2_'+role;videos[key]=inspect(s[key+'Path'],1024,576,25,n);receipt=read(media(s[key+'ReceiptPath']));centre=receipt['blinkCentreFrame']
        if receipt['repairProfile']!='dialogue-stable-v2' or not receipt['deterministicAlgorithms'] or receipt['cudnnBenchmark'] or len(receipt['controlledMotionFrames'])!=n or len(receipt['eyeCorrectionFrames'])!=n:raise RuntimeError('Stable receipt mismatch')
        if any(x['poseFieldsMaxChange'] or x['eyeExpressionDeltaMax'] for x in receipt['controlledMotionFrames']) or any(x['outsideEyeMaxChange'] for x in receipt['eyeCorrectionFrames']):raise RuntimeError('Control supports changed')
        gate=[x['frame'] for x in receipt['eyeCorrectionFrames'] if x['gate']>0]
        if gate!=list(range(centre-2,centre+3)):raise RuntimeError('Unexpected blink interval')
        controls.append(dict(role=role,blinkCentreFrame=centre,blinkGateFrames=gate,peakEyeObservation=receipt['eyeCorrectionFrames'][centre],staticBodyOutsideSupport=True))
    for i,n in [(1,53),(2,43),(3,144)]:videos[f'canvas{i}']=inspect(s[f'canvas{i}Path'],1366,768,24,n)
    videos['picture']=inspect(s['picturePath'],1366,768,24,240);videos['final']=inspect(s['finalPath'],1366,768,24,240,True)
    if payload(s['finalPath'])!=payload(s['inputs']['original']) or payload(s['finalPath'],pcm=True)!=payload(s['inputs']['original'],pcm=True) or audio_timeline(s['finalPath'])!=audio_timeline(s['inputs']['original']):raise RuntimeError('Whole voice payload/clock changed')
    if payload(s['finalPath'],'v:0')!=payload(s['picturePath'],'v:0'):raise RuntimeError('Remux changed video payload')
    ts=json.loads(subprocess.check_output([FFPROBE,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(media(s['finalPath']))]))['frames']
    if len(ts)!=240 or any(abs(float(x['best_effort_timestamp_time'])-i/24)>.000002 for i,x in enumerate(ts)):raise RuntimeError('Video clock irregular')
    cuts=[]
    for global_i,index,local_i in [(0,1,0),(52,1,52),(53,2,0),(54,2,1),(94,2,41),(95,2,42),(96,3,0),(97,3,1),(239,3,143)]:
        mad=float(np.abs(frame(s['finalPath'],global_i)[:600].astype(np.float32)-frame(s[f'canvas{index}Path'],local_i)[:600].astype(np.float32)).mean())
        if mad>8:raise RuntimeError('Cut source correspondence differs')
        cuts.append(dict(finalFrame=global_i,shot=index,sourceFrame=local_i,meanAbsoluteDifference=mad))
    captions(s)
    inventory=read(FOLDER/'model-inventory.json')['files'];current={str(p.relative_to(ROOT.parent/'Models')).replace('\\','/') for p in (ROOT.parent/'Models').rglob('*') if p.is_file()}
    if current!={x['path'] for x in inventory}:raise RuntimeError('Model set changed')
    for item in inventory:
        p=ROOT.parent/'Models'/item['path']
        if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model metadata changed')
    write(FOLDER/'final-verification.json',dict(status='Passed',videos=videos,controls=controls,wholeAudioPacketsEqual=True,wholeAudioPcmEqual=True,audioTimelineAndPrimingEqual=True,audioPackets=len(audio_timeline(s['finalPath'])),videoFrameTimestampsExact=True,cutFrames=[53,96],cutSourceMatches=cuts,finalPictureVideoPacketsUnchanged=True,sourceHashesPreserved=True,modelMetadataFilesUnchanged=len(inventory),newDiffusionJobs=0,newNeuralUpscaleJobs=0,scope='Technical and control invariants; content continuity and blink appearance reviewed separately. No universal generation-stability claim.',contentStatus='NeedReview',publicationStatus='Blocked'))
    viewer(s)
    print('Passed: full decode, original whole audio, captions, clocks, control traces, preserved models/media')
def viewer(s):
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68']);app.prepare(ctx_id=-1,det_size=(640,640))
    paths=[s['inputs']['before'],s['finalPath']];origins=[]
    def faces_for(pixels):
        small=cv2.resize(pixels,(1280,720));faces=sorted(app.get(small),key=lambda f:f.bbox[0])
        if not faces:raise RuntimeError('Face localization failed')
        return small,faces
    for path in paths:
        values=[]
        for i,wide in [(19,False),(77,False),(127,True)]:
            image,faces=faces_for(frame(path,i))
            if wide and len(faces)!=2:raise RuntimeError('Dual roles missing')
            first=faces[0] if wide else max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            def centre(f):return [float((f.bbox[0]+f.bbox[2])/2/1280),float((f.bbox[1]+f.bbox[3])/2/720)]
            def mouth(f):return [float(v) for v in f.landmark_3d_68[48:68,:2].mean(0)/[1280,720]]
            values.append(dict(primary=centre(first),male=centre(faces[-1]) if wide else centre(first),primaryMouth=mouth(first),maleMouth=mouth(faces[-1]) if wide else mouth(first)))
        origins.append(values)
    comparisons=FOLDER/'comparisons';comparisons.mkdir(exist_ok=True);moments=[]
    for i,label,role in [(3,'开头眨眼', 'female'),(24,'固定眨眼','female'),(53,'第一切点','male'),(77,'男方回应','male'),(95,'4秒切镜前','male'),(96,'4秒切镜后','male'),(127,'女方让步','female'),(168,'男方收尾','male'),(239,'末帧','female')]:
        out=Image.new('RGB',(800,436),'#10151c');draw=ImageDraw.Draw(out)
        for col,path in enumerate(paths):
            image,faces=faces_for(frame(path,i))
            if i>=96 and len(faces)!=2:raise RuntimeError('Dual still role missing')
            face=faces[-1] if i>=96 and role=='male' else faces[0] if i>=96 else max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            x1,y1,x2,y2=face.bbox;size=min(max(x2-x1,y2-y1)*1.35,720);x=min(max((x1+x2-size)/2,0),1280-size);y=min(max((y1+y2-size)/2,0),720-size)
            im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).crop((x,y,x+size,y+size)).resize((400,400),Image.Resampling.LANCZOS);out.paste(im,(col*400,36));draw.text((col*400+10,10),('BEFORE QHD' if col==0 else 'STABLE 768p')+f' | frame{i}',fill='white')
        p=comparisons/f'compare-{i:03}.png';out.save(p);moments.append(dict(frame=i,label=label,compare=rel(p)))
    write(ROOT/'web/public/dialogue-stable.json',dict(technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',intro='稳定768p验证版：1366×768 / 24FPS / 10秒。固定眨眼时点、统一切镜姿态，保留原声、四句字幕和53/96帧切点。左侧为上一版2560×1440后期成片；右侧跳过神经超分。动作源仍为832×480，身体动作仍受静态参考图限制。',paths=paths,seconds=10,frames=240,fps=24,cutFrames=[53,96],origins=origins,moments=moments))
    html=(ROOT/'web/public/dialogue-sync-full.html').read_text(encoding='utf-8').replace('dialogue-sync-full.json','dialogue-stable.json').replace('DialogueSyncFull20261025/','DialogueStable20261025/').replace('十秒对白 · 口型与双人回应对比','十秒对白 · 稳定768p验证').replace('上一版 · 已保留的十秒画面','上一版 · 2560×1440后期成片').replace('项目40 · 原声、字幕与切点保持','项目42 · 旧版保留，原声、字幕与切点保持').replace('本轮优化 · 完整十秒','稳定版 · 1366×768成片').replace('按原声驱动嘴形，双人保留原有视线与姿态','固定眨眼 · 统一切镜姿态 · 受控口型').replace('新版采用已认可小样的口型方法；双人保留原有视线与姿态，面部之外使用原参考静态画面。精细口型、闭唇笑容和自然度仍需观看判断。2560×1440为后期输出。','稳定版使用确定性推理、独立姿态和固定眨眼时点，跳过神经超分；面部之外仍使用原参考静态画面。此版证明固定输入下的可复现性，精细口型和自然度仍需观看判断。768p为成片尺寸，动作源为832×480。')
    (ROOT/'web/public/dialogue-stable.html').write_text(html,encoding='utf-8')
    for name in ['dialogue-stable.html','dialogue-stable.json']:shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
if __name__=='__main__':main()

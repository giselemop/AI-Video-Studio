"""Verify real pilot files and equal paired voice, then publish local comparison."""
from run import *
import cv2,numpy as np,hashlib
from PIL import Image,ImageDraw
FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'
def probe(p):return json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(media(p))]))
def frame(p,i):
    cap=cv2.VideoCapture(str(media(p)));cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Actual frame missing')
    return pixels
def packets(p,kind,decode=False):
    tail=['-acodec','pcm_s16le','-f','s16le','pipe:1'] if decode else ['-c', 'copy','-f','data','pipe:1']
    return subprocess.check_output([FFMPEG,'-v','error','-i',str(media(p)),'-map','0:'+kind+':0']+tail)
def inspect(p,w,h,fps,n):
    result=subprocess.run([FFMPEG,'-nostdin','-v','error','-i',str(media(p)),'-map','0:v:0','-f','null','-'],capture_output=True,text=True)
    if result.returncode or result.stderr.strip():raise RuntimeError('Complete video decode failed')
    info=probe(p);v=next(x for x in info['streams'] if x['codec_type']=='video');a,b=map(int,v['avg_frame_rate'].split('/'))
    if (v['width'],v['height'],int(v['nb_read_frames']))!=(w,h,n) or abs(a/b-fps)>.001 or abs(float(info['format']['duration'])-n/fps)>1/fps:raise RuntimeError('Video specification mismatch')
    return dict(path=p,sha256=sha(media(p)),width=w,height=h,fps=fps,frames=n,seconds=n/fps,completeDecode='Passed')
def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():yield from walk(v)
    elif isinstance(value,list):
        for v in value:yield from walk(v)
def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state;videos={};audio=[];timeline=[]
    for clip in CLIPS:
        name=clip['name'];n=clip['frames'];native=clip['nativeFrames']
        for suffix,w,h,fps,count in [('Driver',832,480,25,native),('Baseline',1280,720,24,n),('Canvas',1280,720,24,n),('Qhd',2560,1440,24,n),('Detail',2560,1440,24,n),('Picture',2560,1440,24,n),('Final',2560,1440,24,n)]:
            videos[name+suffix]=inspect(s[name+suffix+'Path'],w,h,fps,count)
        for role in clip['roles']:
            key=name+role.title();videos[key]=inspect(s[key+'Path'],1024,576,25,native)
            receipt=read(media(s[key+'ReceiptPath']));direction='large-small' if name=='close' else 'left-right' if role=='female' else 'right-left'
            if receipt['faceDirection']!=direction or len(receipt['eyeCorrectionFrames'])!=native or any(x['outsideEyeMaxChange'] for x in receipt['eyeCorrectionFrames']):raise RuntimeError('Eye/role protection differs')
            if receipt['drivingSha256']!=s[name+'DriverSha256']:raise RuntimeError('Acting does not use newly generated audio driver')
            if name=='wide' and s.get('wideHybridSelected'):
                if receipt['repairProfile']!='dialogue-hybrid-v1' or receipt['poseSha256']!=s['widePoseSha256'] or receipt['sourceSha256']!=s['wideHybridSourceSha256'] or not receipt['sourceLipNormalized'] or len(receipt['hybridMotionFrames'])!=57 or any(x['poseFieldsMaxChange'] or x['nonLipExpressionMaxChange'] for x in receipt['hybridMotionFrames']):raise RuntimeError('Hybrid mouth/approved-pose separation differs')
        receipt=read(media(s[name+'DetailReceiptPath']))
        if len(receipt['frames'])!=n or any(x['faceCount']!=len(clip['roles']) or x['protectedPixelMaxChange'] or x['outsideSkinMaxChange'] for x in receipt['frames']):raise RuntimeError('Skin/eye/mouth protection failed')
        a=s[name+'BaselinePath'];b=s[name+'FinalPath'];raw=packets(a,'a');pcm=packets(a,'a',True)
        if raw!=packets(b,'a') or pcm!=packets(b,'a',True):raise RuntimeError('Paired original-excerpt voice differs')
        if packets(b,'v')!=packets(s[name+'PicturePath'],'v'):raise RuntimeError('Audio remux reencoded picture')
        for stream in probe(b)['streams']:
            if abs(float(stream['duration'])-n/24)>1/24:raise RuntimeError('Final audio/video duration mismatch')
        audio.append(dict(clip=name,audioPacketsEqual=True,audioPcmEqual=True,packetSha256=hashlib.sha256(raw).hexdigest(),pcmSha256=hashlib.sha256(pcm).hexdigest(),
            scope='Both sides share exact original-excerpt voice; excerpt AAC encoded once in baseline extraction then packet copied'))
        for i in [0,1,n-2,n-1]:
            original=cv2.resize(frame(s['inputs']['original'],clip['startFrame']+i),(1280,720),interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
            excerpt=frame(a,i).astype(np.float32);difference=float(np.abs(original-excerpt).mean())
            if difference>8:raise RuntimeError('Baseline source-frame alignment differs')
            timeline.append(dict(clip=name,excerptFrame=i,originalFrame=clip['startFrame']+i,meanPixelDifference=difference))
    merge=read(media(s['wideMergeReceiptPath']))
    if len(merge['frames'])!=57 or any(not x['roleMasksDisjoint'] or x['outsidePersonSupportMaxChange'] for x in merge['frames']):raise RuntimeError('Dual-person role separation failed')
    history=r.session.get('http://127.0.0.1:8188/history',timeout=30).json();bound={};provenance=[]
    for clip in CLIPS:
        task=s[clip['name']+'DriverTaskId'];matches=[]
        for prompt_id,entry in history.items():
            if any(isinstance(x.get('filename'),str) and ('task_'+str(task)+'_') in x['filename'] for x in walk(entry.get('outputs',{}))):matches.append((prompt_id,entry))
        if len(matches)!=1 or matches[0][1].get('status',{}).get('status_str')!='success':raise RuntimeError('Actual new Comfy history not uniquely successful')
        prompt_id,entry=matches[0];graph=entry['prompt'][2]
        if graph['7']['inputs']['audio_cfg_scale']!=2 or graph['7']['inputs']['num_frames']!=clip['nativeFrames'] or graph['19']['inputs']['length']!=clip['nativeFrames']:raise RuntimeError('Executed audio guidance/frame contract differs')
        submitted=s[clip['name']+'DriverTaskIdInput']['parameters']
        if 'positive' in submitted and graph['5']['inputs']['positive']!=submitted['positive']:raise RuntimeError('Directed performance prompt was not actually executed')
        if clip['name']=='wide' and abs(graph['4']['inputs']['split_ratio']-s['splitRatio'])>1e-8:raise RuntimeError('Executed speaker region differs')
        bindings=[('1','image',s['inputs'][clip['source']]),('2','audio',rel(FOLDER/(clip['name']+'-female-native.wav')))]
        if clip['name']=='wide':bindings.append(('3','audio',rel(FOLDER/'wide-male-native.wav')))
        input_root=(ROOT.parent/'ComfyUI/input').resolve()
        for node,field,expected in bindings:
            actual=(input_root/graph[node]['inputs'][field]).resolve()
            if not actual.is_relative_to(input_root) or sha(actual)!=sha(media(expected)):raise RuntimeError('Actual Comfy loaded input differs from frozen image/audio')
        output_root=(ROOT.parent/'ComfyUI/output').resolve();raws=[x for x in walk(entry.get('outputs',{})) if str(x.get('filename','')).endswith('.mp4')]
        if len(raws)!=1:raise RuntimeError('Raw generated video not uniquely bound')
        raw=(output_root/raws[0].get('subfolder','')/raws[0]['filename']).resolve()
        if not raw.is_relative_to(output_root) or sha(raw)!=s[clip['name']+'DriverSha256']:raise RuntimeError('Published driver differs from raw Comfy output')
        bound[prompt_id]=entry;provenance.append(dict(clip=clip['name'],taskId=task,promptId=prompt_id,status='success',audioGuidance=2,nativeFrames=clip['nativeFrames'],loadedInputHashesMatched=True,rawPublishedVideoHashMatched=True))
    write(FOLDER/'comfy-executed-history.json',bound)
    inventory=read(FOLDER/'model-inventory.json')['files'];current={str(p.relative_to(ROOT.parent/'Models')).replace('\\','/') for p in (ROOT.parent/'Models').rglob('*') if p.is_file()}
    if current!={x['path'] for x in inventory}:raise RuntimeError('Model file set changed')
    for item in inventory:
        p=ROOT.parent/'Models'/item['path']
        if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Existing model metadata changed')
    before=read(FOLDER/'workflow-contracts-before.json')['contracts'];after=read(ROOT/'config/workflow-contracts.json')['contracts']
    if any(item not in after for item in before):raise RuntimeError('Prior workflow contract changed')
    write(FOLDER/'final-verification.json',dict(status='Passed',videos=videos,audio=audio,timelineMatches=timeline,modelMetadataFilesUnchanged=len(inventory),priorContractsUnchanged=len(before),
        newDriverProvenance=provenance,sourceHashesPreserved=True,scope='Technical checks; no phoneme, identity or naturalness score',contentStatus='NeedReview',publicationStatus='Blocked'))
    # Existing CPU detector places actual face/mouth viewing regions, not identity scores.
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68']);app.prepare(ctx_id=-1,det_size=(640,640))
    values=[];out=FOLDER/'comparisons';out.mkdir(exist_ok=True)
    for clip in CLIPS:
        name=clip['name'];paths=[s[name+'BaselinePath'],s[name+'FinalPath']];origins=[];moments=[]
        for path in paths:
            im=cv2.resize(frame(path,16),(1280,720));faces=sorted(app.get(im),key=lambda f:f.bbox[0])
            if len(faces)!=len(clip['roles']):raise RuntimeError('Viewer cannot localize actual roles')
            def centre(f):return [float((f.bbox[0]+f.bbox[2])/2560),float((f.bbox[1]+f.bbox[3])/1440)]
            mouth=faces[-1] if name=='wide' else faces[0];points=mouth.landmark_3d_68[48:68,:2].mean(0)
            origins.append(dict(primary=centre(faces[0]),male=centre(faces[-1]),mouth=[float(points[0]/1280),float(points[1]/720)]))
        for index in [0,12,26,clip['frames']-1]:
            image=Image.new('RGB',(1280,394),'#10151c');draw=ImageDraw.Draw(image)
            for side,path in enumerate(paths):
                im=Image.fromarray(cv2.cvtColor(frame(path,index),cv2.COLOR_BGR2RGB)).resize((640,360),Image.Resampling.LANCZOS);image.paste(im,(640*side,34));draw.text((640*side+10,10),('PREVIOUS' if side==0 else 'NEW')+f' | {index/24:.3f}s | frame{index}',fill='white')
            p=out/f'{name}-{index:03}.png';image.save(p);moments.append(dict(frame=index,label=f'{index/24:.3f}秒定格',compare=rel(p)))
        values.append(dict(name=name,label='女方完整一句 · 2.000秒' if name=='close' else '男方回应与女方聆听 · 2.250秒',paths=paths,driver=s[name+'DriverPath'],seconds=clip['frames']/24,frames=clip['frames'],startSeconds=clip['startFrame']/24,origins=origins,moments=moments))
    metadata=dict(technicalStatus='Passed',contentStatus='NeedReview',intro='两段小样已完成文件核验。女方按原声重做嘴形；双人保留原来的视线表演，替换嘴部驱动。可切换片段，用正常、半速和逐帧比较。',clips=values)
    write(ROOT/'web/public/dialogue-sync.json',metadata)
    for name in ['dialogue-sync.html','dialogue-sync.json']:
        shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
        if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Published viewer differs')
    write(FOLDER/'preview-publication.json',dict(status='Passed',url='http://127.0.0.1:18080/dialogue-sync.html',htmlSha256=sha(ROOT/'web/dist/dialogue-sync.html'),metadataSha256=sha(ROOT/'web/dist/dialogue-sync.json')))
    print('Passed: real media, equal paired original voice, source alignment, role masks, protected detail, old models/contracts; comparison published')
if __name__=='__main__':main()

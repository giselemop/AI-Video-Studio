"""Real full decode, voice/cut/role invariants and executed Comfy input provenance."""
from verify_helpers import *

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():yield from walk(v)
    elif isinstance(value,list):
        for v in value:yield from walk(v)

def audio_timeline(path):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-select_streams','a:0','-show_packets','-show_entries','packet=pts_time,dts_time,duration_time,flags:packet_side_data=side_data_type,skip_samples,discard_padding','-of','json',str(media(path))]))['packets']

def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state;checks={}
    for shot in SHOTS:
        i=shot['index'];n=shot['frames'];native=shot['native']
        checks[f'driver{i}']=inspect(s[f'driver{i}Path'],832,480,25,native)
        for prefix,w,h in [('canvas',1280,720),('qhd',2560,1440),('detail',2560,1440)]:checks[f'{prefix}{i}']=inspect(s[f'{prefix}{i}Path'],w,h,24,n)
        detail=read(media(s[f'detail{i}ReceiptPath']))
        if len(detail['frames'])!=n or any(x['protectedPixelMaxChange'] or x['outsideSkinMaxChange'] or x['faceCount']!=len(shot['roles']) for x in detail['frames']):raise RuntimeError('Skin/eye/mouth support changed')
        for role in shot['roles']:
            key=f'actor{i}'+role.title();checks[key]=inspect(s[key+'Path'],1024,576,25,native);receipt=read(media(s[key+'ReceiptPath']))
            direction='large-small' if i!=3 else 'left-right' if role=='female' else 'right-left'
            if receipt['faceDirection']!=direction or len(receipt['eyeCorrectionFrames'])!=native or any(x['outsideEyeMaxChange'] for x in receipt['eyeCorrectionFrames']) or receipt['drivingSha256']!=s[f'driver{i}Sha256']:raise RuntimeError('New-driver/eye/role trace differs')
            if i==3:
                if receipt['repairProfile']!='dialogue-hybrid-full-v1' or receipt['poseSha256']!=sha(media(s['inputs']['pose'])) or not receipt['sourceLipNormalized'] or len(receipt['hybridMotionFrames'])!=151 or any(x['poseFieldsMaxChange'] or x['nonLipExpressionMaxChange'] for x in receipt['hybridMotionFrames']):raise RuntimeError('Approved full pose and fresh mouth not isolated')
            elif receipt['repairProfile']!='dialogue-blink-v1':raise RuntimeError('Old accepted portrait profile differs')
    merge=read(media(s['wideMergeReceiptPath']))
    if len(merge['frames'])!=151 or any(not x['roleMasksDisjoint'] or x['outsidePersonSupportMaxChange'] for x in merge['frames']):raise RuntimeError('Person supports mixed')
    checks['picture']=inspect(s['picturePath'],2560,1440,24,240)
    checks['final']=inspect(s['finalPath'],2560,1440,24,240,True)
    final_probe=probe(media(s['finalPath']))
    if not any(x['codec_type']=='audio' for x in final_probe['streams']) or any(abs(float(x['duration'])-10)>1/24 for x in final_probe['streams']):raise RuntimeError('Final stream durations differ')
    packet=audio(s['finalPath']);pcm=audio(s['finalPath'],False)
    if packet!=audio(s['inputs']['original']) or pcm!=audio(s['inputs']['original'],False):raise RuntimeError('Original whole AAC/PCM changed')
    original_audio_timeline=audio_timeline(s['inputs']['original']);final_audio_timeline=audio_timeline(s['finalPath'])
    if original_audio_timeline!=final_audio_timeline:raise RuntimeError('Original audio timestamps/priming changed')
    timestamps=json.loads(subprocess.check_output([FFPROBE,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(media(s['finalPath']))]))['frames']
    if len(timestamps)!=240 or any(abs(float(x['best_effort_timestamp_time'])-i/24)>.000002 for i,x in enumerate(timestamps)):raise RuntimeError('Final video frame timestamps shifted or irregular')
    picture=video_packets(s['picturePath'])
    if video_packets(s['finalPath'])!=picture:raise RuntimeError('Remux changed picture')
    cuts=[]
    for global_i,index,local_i in [(0,1,0),(51,1,51),(52,1,52),(53,2,0),(54,2,1),(94,2,41),(95,2,42),(96,3,0),(97,3,1),(239,3,143)]:
        a=frame(s['finalPath'],global_i)[:1150].astype(np.float32);b=frame(s[f'detail{index}Path'],local_i)[:1150].astype(np.float32);mad=float(np.abs(a-b).mean())
        if mad>8:raise RuntimeError('Cut/source correspondence differs')
        cuts.append(dict(finalFrame=global_i,sourceShot=index,sourceFrame=local_i,meanAbsolutePixelDifference=mad))
    voice=read(FOLDER/'voice-window-checks.json')
    if voice['status']!='Passed' or voice['subtitleSha256']!=sha(media(s['inputs']['subtitle'])) or s['pictureTaskIdInput']['parameters']['subtitlePath']!=s['inputs']['subtitle']:raise RuntimeError('Original subtitles or voice windows changed')
    inventory=read(FOLDER/'model-inventory.json')['files'];current={str(p.relative_to(ROOT.parent/'Models')).replace('\\','/') for p in (ROOT.parent/'Models').rglob('*') if p.is_file()}
    if current!={x['path'] for x in inventory}:raise RuntimeError('Model set changed')
    for item in inventory:
        p=ROOT.parent/'Models'/item['path']
        if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model metadata changed')
    before=read(FOLDER/'backups/config/workflow-contracts.json')['contracts'];after=read(ROOT/'config/workflow-contracts.json')['contracts']
    if any(c not in after for c in before):raise RuntimeError('Old workflow contract changed')
    history=r.session.get('http://127.0.0.1:8188/history',timeout=30).json();bound={};provenance=[]
    for shot in SHOTS:
        i=shot['index'];task=s[f'driver{i}TaskId'];matches=[]
        for prompt_id,entry in history.items():
            if any(isinstance(x.get('filename'),str) and f'task_{task}_' in x['filename'] for x in walk(entry.get('outputs',{}))):matches.append((prompt_id,entry))
        if len(matches)!=1 or matches[0][1].get('status',{}).get('status_str')!='success':raise RuntimeError('Fresh Comfy success not uniquely recorded')
        prompt_id,entry=matches[0];graph=entry['prompt'][2]
        if graph['7']['inputs']['audio_cfg_scale']!=2 or graph['7']['inputs']['num_frames']!=shot['native'] or graph['19']['inputs']['length']!=shot['native'] or graph['15']['inputs']['steps']!=8:raise RuntimeError('Executed audio guidance/frame/step differs')
        if i==3 and abs(graph['4']['inputs']['split_ratio']-s['splitRatio'])>1e-8:raise RuntimeError('Actual speaker region differs')
        bindings=[('1','image',s['inputs'][shot['source']]),('2','audio',rel(FOLDER/f"shot-{i}-{'female' if i in [1,3] else 'male'}.wav"))]
        if i==3:bindings.append(('3','audio',rel(FOLDER/'shot-3-male.wav')))
        input_root=(ROOT.parent/'ComfyUI/input').resolve()
        for node,field,expected in bindings:
            actual=(input_root/graph[node]['inputs'][field]).resolve()
            if not actual.is_relative_to(input_root) or sha(actual)!=sha(media(expected)):raise RuntimeError('Executed Comfy input differs')
        output_root=(ROOT.parent/'ComfyUI/output').resolve();raws=[x for x in walk(entry.get('outputs',{})) if str(x.get('filename','')).endswith('.mp4')]
        if len(raws)!=1:raise RuntimeError('Raw generated driver not unique')
        raw=(output_root/raws[0].get('subfolder','')/raws[0]['filename']).resolve()
        if not raw.is_relative_to(output_root):raise RuntimeError('Raw output outside controlled Comfy root')
        exact_file=sha(raw)==s[f'driver{i}Sha256'];recovery=None
        if i==3 and s.get('driver3Recovered'):
            recovery=read(FOLDER/'driver-recovery.json')
            if recovery['status']!='Passed' or recovery['promptId']!=prompt_id or recovery['failedTaskId']!=task or recovery['rawSha256']!=sha(raw) or recovery['importedSha256']!=sha(media(recovery['importedPath'])) or recovery['publishedSha256']!=s['driver3Sha256'] or video_packets(s['driver3Path'])!=video_packets(recovery['importedPath']):raise RuntimeError('Same-prompt stream-copy recovery provenance differs')
        elif not exact_file:raise RuntimeError('Published driver differs from raw Comfy output')
        bound[prompt_id]=entry;provenance.append(dict(index=i,taskId=task,promptId=prompt_id,status='success',audioGuidance=2,nativeFrames=shot['native'],loadedInputHashesMatched=True,rawPublishedVideoHashMatched=exact_file,recoveryTaskId=recovery['recoveryTaskId'] if recovery else None,rawPublishedVideoPacketsEqual=True))
    write(FOLDER/'comfy-executed-history.json',bound)
    write(FOLDER/'final-verification.json',dict(status='Passed',videos=checks,cutFrames=[53,96],cutSourceMatches=cuts,audioPacketsEqual=True,audioPcmEqual=True,audioTimelineAndPrimingEqual=True,audioTimelinePacketCount=len(final_audio_timeline),videoFrameTimestampsExact=True,audioPacketSha256=hashlib.sha256(packet).hexdigest(),audioPcmSha256=hashlib.sha256(pcm).hexdigest(),finalPictureVideoPacketsUnchanged=True,subtitleSha256=voice['subtitleSha256'],originalSubtitleInputUnchanged=True,sourceHashesPreserved=True,modelMetadataFilesUnchanged=len(inventory),priorContractsUnchanged=len(before),newDriverProvenance=provenance,scope='Technical trace and geometry checks; no invented phoneme/identity/naturalness score',contentStatus='NeedReview',publicationStatus='Blocked'))
    # The viewer block below derives face positions and comparisons from these actual final files.

    # CPU face detection only positions the viewer and stills; it is not identity scoring.
    sys.path.insert(0,str(ROOT/'tools/identity_foundation'));from identity_foundation import import_runtime
    *_,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(ROOT.parent/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68']);app.prepare(ctx_id=-1,det_size=(640,640))
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
            def mouth(f):
                p=f.landmark_3d_68[48:68,:2].mean(0);return [float(p[0]/1280),float(p[1]/720)]
            values.append(dict(primary=centre(first),male=centre(faces[-1]) if wide else centre(first),primaryMouth=mouth(first),maleMouth=mouth(faces[-1]) if wide else mouth(first)))
        origins.append(values)
    comparison=FOLDER/'comparisons';comparison.mkdir(exist_ok=True);moments=[]
    for i,label,role in [(9,'女方起句','female'),(19,'女方近景','female'),(53,'第一处切点','male'),(77,'男方回应','male'),(96,'第二处切点','female'),(127,'女方让步','female'),(168,'男方收尾','male'),(239,'末帧','female')]:
        out=Image.new('RGB',(800,436),'#10151c');draw=ImageDraw.Draw(out)
        for col,path in enumerate(paths):
            image,faces=faces_for(frame(path,i))
            if i>=96 and len(faces)!=2:raise RuntimeError('Two-person still cannot be safely localized')
            face=faces[-1] if i>=96 and role=='male' else faces[0] if i>=96 else max(faces,key=lambda f:np.prod(f.bbox[2:]-f.bbox[:2]))
            x1,y1,x2,y2=face.bbox;size=min(max(x2-x1,y2-y1)*1.35,720);x=min(max((x1+x2-size)/2,0),1280-size);y=min(max((y1+y2-size)/2,0),720-size)
            im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).crop((x,y,x+size,y+size)).resize((400,400),Image.Resampling.LANCZOS)
            out.paste(im,(400*col,36));draw.text((400*col+10,10),('PREVIOUS' if col==0 else 'NEW')+f' | frame{i} | {i/24:.3f}s',fill='white')
        p=comparison/f'compare-{i:03}.png';out.save(p);moments.append(dict(frame=i,label=label,compare=rel(p)))
    metadata=dict(technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',intro='完整十秒口型版已完成文件核验：按原声驱动嘴形，双人保留原有视线与姿态；四句对白、完整声轨、字幕和三镜头切点保持。支持正常/半速及逐帧前后对比。',paths=paths,seconds=10,frames=240,fps=24,cutFrames=[53,96],origins=origins,moments=moments)
    write(ROOT/'web/public/dialogue-sync-full.json',metadata)
    for name in ['dialogue-sync-full.html','dialogue-sync-full.json']:
        shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
        if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Published preview differs')
    write(FOLDER/'preview-publication.json',dict(status='Passed',url='http://127.0.0.1:18080/dialogue-sync-full.html',htmlSha256=sha(ROOT/'web/dist/dialogue-sync-full.html'),metadataSha256=sha(ROOT/'web/dist/dialogue-sync-full.json')))
    print('Passed: full decode,240unique frames,original AAC/PCM,cut correspondence,role/skin protection and source preservation; comparison published')

if __name__=='__main__':main()

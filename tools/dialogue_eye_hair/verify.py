"""Decode the delivered revision and inspect protected female/male regions."""
from run import *
import cv2,numpy as np,hashlib,re
from PIL import Image,ImageDraw
spec=importlib.util.spec_from_file_location('eye_hair_technical_helpers',ROOT/'tools/dialogue_stable/verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
    checks=dict(native=v.inspect(s['wideMergePath'],1024,576,25,151),sample=v.inspect(s['wideCanvasPath'],1366,768,24,144),picture=v.inspect(s['picturePath'],1366,768,24,240),final=v.inspect(s['finalPath'],1366,768,24,240,True))
    before=s['inputs']['before'];after=s['finalPath']
    if v.payload(before)!=v.payload(after) or v.payload(before,pcm=True)!=v.payload(after,pcm=True) or v.audio_timeline(before)!=v.audio_timeline(after):raise RuntimeError('Original whole audio/clock changed')
    if v.payload(s['picturePath'],'v:0')!=v.payload(after,'v:0'):raise RuntimeError('Remux changed picture packets')
    timestamps=json.loads(subprocess.check_output([v.FFPROBE,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(media(after))]))['frames']
    if len(timestamps)!=240 or any(abs(float(x['best_effort_timestamp_time'])-i/24)>.000002 for i,x in enumerate(timestamps)):raise RuntimeError('Frame clock shifted')
    cuts=[]
    for i,key,n in [(52,'canvas1',52),(53,'canvas2',0),(95,'canvas2',42),(96,'wide',0),(97,'wide',1),(239,'wide',143)]:
        p=s['wideCanvasPath'] if key=='wide' else s['inputs'][key];mad=float(np.abs(v.frame(after,i)[:600].astype(np.float32)-v.frame(p,n)[:600].astype(np.float32)).mean())
        if mad>8:raise RuntimeError('Shot cut/source correspondence differs')
        cuts.append(dict(frame=i,sourceFrame=n,meanAbsoluteDifference=mad))
    a=cv2.VideoCapture(str(media(before)));bcap=cv2.VideoCapture(str(media(after)));retained=[]
    for i in range(240):
        ok,x=a.read();ok2,y=bcap.read()
        if not ok or not ok2:raise RuntimeError('Missing whole-frame comparison')
        roi=(slice(None),slice(None)) if i<96 else (slice(None),slice(683,None))
        mad=float(np.abs(x[roi].astype(np.float32)-y[roi].astype(np.float32)).mean())
        if mad>3:raise RuntimeError('Unrelated retained shot/male image differs excessively')
        retained.append(dict(frame=i,retainedRegion='whole-frame' if i<96 else 'right-half-male',meanAbsoluteDifference=mad))
    a.release();bcap.release();v.captions(s)
    inventory=read(FOLDER/'model-inventory.json')['files'];current={str(p.relative_to(ROOT.parent/'Models')).replace('\\','/') for p in (ROOT.parent/'Models').rglob('*') if p.is_file()}
    if current!={x['path'] for x in inventory}:raise RuntimeError('Model set changed')
    for item in inventory:
        p=ROOT.parent/'Models'/item['path']
        if p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:raise RuntimeError('Model metadata changed')
    receipt=read(media(s['wideMergeReceiptPath']))
    if receipt['sourceSha256']!=sha(media(s['inputs']['source'])) or not receipt['femaleSideProfileBlinkDisabled'] or len(receipt['frames'])!=151 or any(x['femaleOutsideMouthMaxChange'] or x['maleCompositeMaxChange'] for x in receipt['frames']):raise RuntimeError('Protection trace failed')
    write(FOLDER/'final-verification.json',dict(status='Passed',videos=checks,wholeAudioPacketsEqual=True,wholeAudioPcmEqual=True,audioTimelineAndPrimingEqual=True,audioPacketCount=len(v.audio_timeline(after)),picturePacketsUnchanged=True,videoClockExact=True,cutFrames=[53,96],cutSourceMatches=cuts,retainedShotAndMaleComparisons=retained,preservedFileHashes=len(s['preserved']),modelMetadataFilesUnchanged=len(inventory),nativeProtectedFrameCount=151,femaleOutsideMouthMaxChangeBeforeEncoding=0,maleCompositeMaxChangeBeforeEncoding=0,newGpuTasks=0,newModels=0,cloudCalls=0,scope='Technical invariants and explicit source-anchor behavior. Fixed female eyes/head in wide; no claim of natural blink or complete acting quality.',contentStatus='NeedReview',publicationStatus='Blocked'))
    viewer(s);print('Passed:240-frame decode, original whole audio/subtitles/cuts, retained male/close shots, source eye/hair guard')
def viewer(s):
    old=read(ROOT/'web/public/dialogue-stable.json');origins=[old['origins'][1],old['origins'][1]]
    moments=[];comparison=FOLDER/'comparisons';comparison.mkdir(exist_ok=True)
    for i,label in [(100,'女方起句'),(132,'女方说话'),(188,'异常前'),(190,'7.917秒'),(191,'7.958秒'),(192,'8.000秒'),(193,'8.042秒'),(194,'8.083秒'),(196,'异常后'),(239,'末帧')]:
        out=Image.new('RGB',(800,436),'#10151c');draw=ImageDraw.Draw(out)
        for col,p in enumerate([s['inputs']['before'],s['finalPath']]):
            x=v.frame(p,i);h,w=x.shape[:2];crop=x[round(h*.055):round(h*.48),round(w*.17):round(w*.44)];im=Image.fromarray(cv2.cvtColor(crop,cv2.COLOR_BGR2RGB));im.thumbnail((400,400));out.paste(im,(col*400+(400-im.width)//2,36));draw.text((col*400+10,10),('BEFORE' if col==0 else 'EYE/HAIR GUARD')+f' | {i/24:.3f}s',fill='white')
        p=comparison/f'compare-{i:03}.png';out.save(p);moments.append(dict(frame=i,label=label,compare=rel(p)))
    html=(ROOT/'web/public/dialogue-stable.html').read_text(encoding='utf-8').replace('dialogue-stable.json','dialogue-eye-hair.json').replace('DialogueStable20261025/','DialogueEyeHair20261025/').replace('十秒对白 · 稳定768p验证','侧脸眼睛与头发 · 修复对比').replace('上一版 · 2560×1440后期成片','修复前 · 768p').replace('项目42 · 旧版保留，原声、字幕与切点保持','项目43 · 用户指出的侧脸眼部与头发问题').replace('稳定版 · 1366×768成片','局部修复 · 1366×768').replace('固定眨眼 · 统一切镜姿态 · 受控口型','女方侧脸眼睛与头发固定 · 保留说话嘴部')
    html=re.sub(r'<p class="note">.*?</p>','<p class="note">重点检查7.9–8.1秒。修复版在4–10秒双人镜头锁定女方参考图的眼睛、头发和头部，仅在原女方对白时段更新嘴部；该镜头不再生成女方眨眼或头部动作。男方动作、原声、四句字幕、53/96帧切点和旧版保留。此版是保守局部修复，不能当作完整自然表演验收。</p>',html,flags=re.S)
    (ROOT/'web/public/dialogue-eye-hair.html').write_text(html,encoding='utf-8')
    write(ROOT/'web/public/dialogue-eye-hair.json',dict(technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',intro='修复用户指出的女方侧脸眼睛发白、头发重影。两版均1366×768 / 24FPS /10秒；原声、四句字幕和53/96帧切点保持。新版双人镜头固定女方眼睛/头发/头部，只保留说话嘴部；自然度仍有取舍。',paths=[s['inputs']['before'],s['finalPath']],seconds=10,frames=240,fps=24,cutFrames=[53,96],origins=origins,moments=moments))
    for name in ['dialogue-eye-hair.html','dialogue-eye-hair.json']:shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
if __name__=='__main__':main()

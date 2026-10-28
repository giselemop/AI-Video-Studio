"""Decode, protect and publish the three independent before/after groups."""
from run import *
from PIL import Image,ImageDraw
import cv2,numpy as np,shutil,importlib.util
spec=importlib.util.spec_from_file_location('prior_verification',ROOT/'tools/visual_validation/verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.preserve();s=r.state
videos={}
for name,path,w,h,fps,n in [
    ('h3Before',s['inputs']['h3ControlledPath'],864,480,24,124),('h3After',s['h3RepairPath'],864,480,24,124),
    ('blinkNative',s['blinkPath'],1024,576,25,50),('blinkBefore',s['inputs']['actingNewComparePath'],1280,720,24,48),
    ('blinkAfter',s['blinkComparePath'],1280,720,24,48),('detailBefore',s['detailBaselinePath'],2560,1440,24,48),('detailAfter',s['detailPath'],2560,1440,24,48)]:
    videos[name]=v.inspect(path,w,h,fps,n)
changes=[];inventory=read(FOLDER/'model-inventory.json')['files']
for item in inventory:
    p=ROOT.parent/'Models'/item['path']
    if not p.exists() or p.stat().st_size!=item['size'] or p.stat().st_mtime_ns!=item['mtimeNs']:changes.append(item['path'])
if changes:raise RuntimeError('Model inventory metadata changed: '+str(changes))
blink=read(media(s['blinkReceipt']));detail=read(media(s['detailReceipt']))
if any(x['outsideEyeMaxChange'] for x in blink['eyeCorrectionFrames']) or not any(x['changed'] for x in blink['eyeCorrectionFrames']):raise RuntimeError('Eye protection/correction not verified')
if len(detail['frames'])!=48 or any(x['protectedPixelMaxChange'] or x['outsideSkinMaxChange'] for x in detail['frames']):raise RuntimeError('Skin protection not verified')
history=read(FOLDER/'h3-live-history.json');matches=[]
for prompt,entry in history.items():
    files=[f for node in entry.get('outputs',{}).values() for name in ['images','gifs','videos','audio'] for f in node.get(name,[]) if isinstance(f,dict)]
    selected=[f for f in files if f'task_{s["h3RepairTaskId"]}_' in f.get('filename','')]
    if selected:matches.append((prompt,entry,selected))
if len(matches)!=1 or matches[0][1].get('status',{}).get('status_str')!='success':raise RuntimeError('Actual H3 history not uniquely successful')
raws=[]
for f in matches[0][2]:
    p=(ROOT.parent/'ComfyUI/output'/f.get('subfolder','')/f['filename']).resolve()
    if not p.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise RuntimeError('Raw output path outside root')
    if p.is_file():raws.append(dict(path=str(p),sha256=sha(p)))
if not any(x['sha256']==s['h3RepairSha256'] for x in raws):raise RuntimeError('H3 raw/published SHA mismatch')
write(FOLDER/'h3-source-verification.json',dict(status='Passed',promptId=matches[0][0],historyStatus='success',rawOutputs=raws,publishedHashMatched=True))
folder=FOLDER/'comparisons';folder.mkdir(exist_ok=True)
def moments(key,before,after,indexes,roi,fps):
    rows=[]
    for i in indexes:
        images=[v.frame(p,i).crop(roi).resize((400,400),Image.Resampling.LANCZOS) for p in [before,after]]
        out=Image.new('RGB',(800,436),'#10151c');draw=ImageDraw.Draw(out)
        for col,im in enumerate(images):
            out.paste(im,(400*col,36));draw.text((400*col+10,10),('BEFORE' if col==0 else 'TARGETED REPAIR')+f' | frame{i}',fill='white')
        path=folder/f'{key}-{i:03}.png';out.save(path);rows.append(dict(label=f'{i/fps:.3f} 秒',frame=i,compare=rel(path)))
    return rows
groups=[]
for key,title,before,after,fps,frames,roi,indexes,note,before_title,after_title,specification in [
    ('blink','眨眼闭合',s['inputs']['actingNewComparePath'],s['blinkComparePath'],24,48,(465,70,1015,620),[0,7,9,12,24],
     '同一新关键帧与旧自有生成驱动。新增学习式眼部残差，仅在驱动眨眼时合成眼部；嘴部和头部沿用原运动。两版统一24FPS展示，静音。不是新真人表演，眨眼节奏与自然度仍需观看判断。',
     '上一轮 · 眨眼闭合不完整','本轮 · 局部眼部修复','1280×720 · 24FPS · 48帧 · 2秒'),
    ('h3','H3中段表情',s['inputs']['h3ControlledPath'],s['h3RepairPath'],24,124,(210,0,690,480),[0,30,61,92,123],
     '同模型、种子、首尾帧、20步与原生规格；只改分时段闭口提示。请看中段是否露齿、是否提前大笑，以及收尾与构图。首尾约束不能保证所有帧严格遵循语义。',
     '上一轮 · 首尾帧实验','本轮 · 分时段闭口约束','H3原生864×480 · 24FPS · 124帧 · 5.167秒'),
    ('detail','皮肤细节保留',s['detailBaselinePath'],s['detailPath'],24,48,(950,110,2050,1210),[0,12,24,36,47],
     '左侧为上一轮QHD的同编码对照；右侧从同帧精修前素材回补已有亮度频段。只作用于受保护的皮肤掩膜，眼口及掩膜外编码前保持；收益较轻，不等于新增真实毛孔。',
     '上一轮QHD · 同编码对照','本轮 · 源细节回补','2560×1440 · 24FPS · 48帧 · 2秒')]:
    groups.append(dict(key=key,title=title,seconds=frames/fps,frames=frames,fps=fps,note=note,
        before=dict(title=before_title,path=before,spec=specification),after=dict(title=after_title,path=after,spec=specification),
        moments=moments(key,before,after,indexes,roi,fps)))
write(FOLDER/'media-verification.json',dict(status='Passed',videos=videos,modelInventoryFilesUnchanged=len(inventory),frozenInputHashesUnchanged=len(s['preserved']),
    eyeProtection='Decoded face crop outside eye masks unchanged; followed by pasteback/resampling/encoding',skinProtection='All48 frames outside skin and protected eyes/lips unchanged before encoding',
    contentStatus='NeedReview',publicationStatus='Blocked'))
metadata=dict(intro='三项定向修复均已生成并完成文件与保护区域核验。支持前后同步、半速、逐帧与局部对比；画面自然度仍需人工复核。',groups=groups,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked')
write(ROOT/'web/public/visual-targeted.json',metadata)
for name in ['visual-targeted.html','visual-targeted.json']:shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
write(FOLDER/'preview-publication.json',dict(status='Passed',url='http://127.0.0.1:18080/visual-targeted.html',htmlSha256=sha(ROOT/'web/dist/visual-targeted.html'),metadataSha256=sha(ROOT/'web/dist/visual-targeted.json')))
print('Passed: decoded media, frozen models/inputs, actual H3 history, eye/skin protection; new comparison published')

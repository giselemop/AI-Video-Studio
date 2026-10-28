"""Decode every delivered frame, verify frozen inputs, and build honest A/B evidence."""
from run import ROOT,DATA,FOLDER,Run,read,write,media,rel,sha
from PIL import Image,ImageDraw,ImageOps
import cv2
import hashlib
import numpy as np
import subprocess
import requests
import re

FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'

def inspect(path,width,height,fps,frames):
    path=media(path)
    result=subprocess.run([FFMPEG,'-nostdin','-v','error','-i',str(path),'-map','0:v:0','-f','null','-'],capture_output=True,text=True)
    if result.returncode or result.stderr.strip():raise RuntimeError('Complete decode failed: '+result.stderr[-900:])
    probe=read_probe(path);stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    n,d=map(int,stream['avg_frame_rate'].split('/'));actual_fps=n/d
    cap=cv2.VideoCapture(str(path));count=0;hashes=set();changes=[];previous=None
    while True:
        ok,image=cap.read()
        if not ok:break
        count+=1;hashes.add(hashlib.sha256(image.tobytes()).hexdigest())
        small=cv2.resize(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),(160,90)).astype(np.float32)
        if previous is not None:changes.append(float(np.abs(small-previous).mean()))
        previous=small
    cap.release()
    duration=float(probe['format']['duration'])
    if (stream['width'],stream['height'])!=(width,height) or abs(actual_fps-fps)>.001 or count!=frames or abs(duration-frames/fps)>1/fps:
        raise RuntimeError('Delivery specification differs: '+str(path))
    if len(hashes)<2:raise RuntimeError('Static/empty output cannot count as a motion sample')
    return dict(status='Passed',path=rel(path),sha256=sha(path),width=width,height=height,fps=fps,frames=count,
        durationSeconds=duration,uniqueDecodedFrames=len(hashes),meanFrameDifference=float(np.mean(changes)),
        metricMeaning='File/dynamic-pixel observations only; not semantic motion, identity or artistic quality scores')

def read_probe(path):
    value=subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)])
    import json
    return json.loads(value)

def frame(path,index):
    cap=cv2.VideoCapture(str(media(path)));cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Cannot read actual comparison frame '+str(index))
    return Image.fromarray(cv2.cvtColor(pixels,cv2.COLOR_BGR2RGB))

def comparison(before,after,index,label):
    images=[frame(before,index),frame(after,index)];canvas=Image.new('RGB',(1280,390),'#10151c');draw=ImageDraw.Draw(canvas)
    for column,image in enumerate(images):
        draw.text((column*640+10,8),('BASELINE' if column==0 else 'NEW')+f' | frame {index}',fill='white')
        canvas.paste(ImageOps.contain(image,(640,360)),(column*640,30))
    folder=FOLDER/'comparisons';folder.mkdir(exist_ok=True);path=folder/f'{label}-{index:03}.png';canvas.save(path)
    return rel(path)

def main():
    run=Run('http://127.0.0.1:18081',FOLDER/'run.json');run.preserve();s=run.state
    checks={}
    for key in ['h3BaselinePath','h3ControlledPath']:
        checks[key]=inspect(s[key],864,480,24,124)
    checks['actingPath']=inspect(s['actingPath'],1024,576,25,50)
    for key in ['actingOriginalComparePath','actingNewComparePath']:
        checks[key]=inspect(s[key],1280,720,24,48)
    checks['qhdPath']=inspect(s['qhdPath'],2560,1440,24,48)
    frames=[]
    for i in range(1,7):
        path=media(s[f'keyframe{i}Path']);image=Image.open(path);image.verify()
        if Image.open(path).size!=(1024,576) or sha(path)!=s[f'keyframe{i}Sha256']:raise RuntimeError('Keyframe specification/hash changed')
        frames.append(dict(index=i,path=rel(path),sha256=sha(path),width=1024,height=576))
    pairs=[('h3',s['h3BaselinePath'],s['h3ControlledPath'],[0,30,61,92,123]),
        ('acting',s['actingOriginalComparePath'],s['actingNewComparePath'],[0,12,24,36,47]),
        ('qhd',s['actingNewComparePath'],s['qhdPath'],[0,12,24,36,47])]
    comparisons={label:[dict(frame=i,path=comparison(a,b,i,label)) for i in moments] for label,a,b,moments in pairs}
    baseline=read(FOLDER/'existing-model-inventory.json');changed=[];cache_changes=[];model_count=0
    for item in baseline['files']:
        path=ROOT.parent/'Models'/item['path']
        differs=not path.exists() or path.stat().st_size!=item['size'] or path.stat().st_mtime_ns!=item['mtimeNs']
        # Download recovery chunks are not loadable model weights. Keep their
        # differences visible without claiming the complete cache is unchanged.
        if re.search(r'\.range\d{3}\.recovered$',item['path']):
            if differs:cache_changes.append(dict(path=item['path'],state='missing' if not path.exists() else 'metadata-changed',cause='Unverified'))
        else:
            model_count+=1
            if differs:changed.append(item['path'])
    if changed:raise RuntimeError('Existing model file metadata changed: '+str(changed))
    session=requests.Session();session.trust_env=False
    response=session.get('http://127.0.0.1:8188/history',params={'max_items':60},timeout=30);response.raise_for_status()
    history=response.json();receipts=[];history_folder=FOLDER/'comfy-history';history_folder.mkdir(exist_ok=True)
    for field in [f'keyframe{i}TaskId' for i in range(1,7)]+['h3BaselineTaskId','h3ControlledTaskId']:
        task_id=s[field];matches=[]
        for prompt_id,entry in history.items():
            files=[v for node in entry.get('outputs',{}).values() for k in ['images','gifs','videos','audio']
                for v in node.get(k,[]) if isinstance(v,dict)]
            selected=[v for v in files if f'task_{task_id}_' in v.get('filename','')]
            if selected:matches.append((prompt_id,entry,selected))
        if not matches:
            # Comfy history is memory-only and was cleared by the recorded idle
            # restarts. Never recreate a success history entry from other data.
            task=read(FOLDER/f'task-{task_id}.json')['task']
            if task['status']!='Succeeded':raise RuntimeError('Business task did not succeed')
            prefix=field[:-len('TaskId')]
            expected=s[prefix+'Sha256']
            raw_files=list((ROOT.parent/'ComfyUI/output/video_studio').glob(f'task_{task_id}_*'))
            rows=[dict(filename=p.name,sourceSha256=sha(p),bytes=p.stat().st_size) for p in raw_files if p.is_file()]
            if not any(row['sourceSha256']==expected for row in rows):raise RuntimeError('Published asset differs from retained Comfy raw output')
            metadata_nodes=None
            if field.startswith('keyframe'):
                prompt=__import__('json').loads(Image.open(media(s[prefix+'Path'])).info['prompt'])
                metadata_nodes=len(prompt)
                if not any(n.get('class_type')=='SaveImage' and f'task_{task_id}_' in n.get('inputs',{}).get('filename_prefix','') for n in prompt.values()):
                    raise RuntimeError('PNG embedded workflow not bound to task')
            receipts.append(dict(taskId=task_id,rawOutputs=rows,historyStatus='Unverified',
                historyReason='Memory-only Comfy history cleared by recorded idle restarts; no history reconstructed',
                businessTaskStatus=task['status'],publishedRawSha256Matched=True,embeddedWorkflowNodes=metadata_nodes))
            continue
        if len(matches)!=1:raise RuntimeError('Ambiguous actual Comfy history records for task '+str(task_id))
        prompt_id,entry,files=matches[0]
        if not entry.get('status',{}).get('completed') or entry.get('status',{}).get('status_str')!='success':
            raise RuntimeError('Comfy history did not complete successfully')
        write(history_folder/f'task-{task_id}.json',entry)
        rows=[]
        for value in files:
            raw=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve()
            if not raw.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()) or not raw.is_file():continue
            rows.append(dict(filename=value['filename'],sourceSha256=sha(raw),bytes=raw.stat().st_size))
        if not rows:raise RuntimeError('Comfy raw outputs missing')
        if field.startswith('keyframe'):
            index=int(field[len('keyframe'):-len('TaskId')])
            if not any(row['sourceSha256']==s[f'keyframe{index}Sha256'] for row in rows):raise RuntimeError('Published PNG differs from actual Comfy output')
        receipts.append(dict(taskId=task_id,promptId=prompt_id,rawOutputs=rows,historyStatus='success'))
    write(FOLDER/'comfy-source-verification.json',dict(status='Passed',receipts=receipts,
        pngPublicationHashesMatched=True,nativeVideosAlsoFullyDecoded=True,
        liveHistoryStatus='Passed' if all(r['historyStatus']=='success' for r in receipts) else 'Unverified'))
    write(FOLDER/'media-verification.json',dict(status='Passed',videos=checks,keyframes=frames,comparisons=comparisons,
        preservedSourceHashes=len(s['preserved']),existingModelMetadataUnchanged=model_count,
        modelPreservationScope='Loadable model files size/mtime unchanged; not a new full-content hash of every old model. Download-recovery cache chunks reported separately.',
        cacheArtifactChanges=cache_changes,baselineInventoryFileCount=len(baseline['files']),
        comfyTaskReceipts=receipts,contentStatus='NeedReview',publicationStatus='Blocked'))
    print('Passed: all frames decoded, exact specifications, frozen sources and existing model metadata preserved')

if __name__=='__main__':main()

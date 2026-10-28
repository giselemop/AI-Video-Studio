"""Read-only verification of registered REAL outputs; extracts inspection frames.

Does not approve content, create media tasks, or replace original outputs.
"""
from pathlib import Path
import sys,json,requests,subprocess,math
from PIL import Image,ImageDraw
import numpy as np
sys.path.insert(0,str(Path(__file__).parent))
from common import ROOT,DATA,OUT,sha,write,mysql

FFMPEG='C:/install/FFmpeg/bin/ffmpeg.exe'
FFPROBE='C:/install/FFmpeg/bin/ffprobe.exe'

def run():
    pilot=json.loads((OUT/'run.json').read_text(encoding='utf-8'));checks=[];outputs=[];pending=[]
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        if not passed:raise AssertionError(name)
    for slot,item in pilot['slots'].items():
      for kind in ['Keyframe','Video']:
       for entry in item.get(kind+'History',[])+([item[kind]] if item.get(kind,{}).get('id') else []):
        tid=entry['id'];detail=requests.get(f'http://127.0.0.1:18080/api/tasks/{tid}',timeout=30).json()
        if detail['task']['status']!='Succeeded':pending.append(dict(taskId=tid,status=detail['task']['status']));continue
        suffix='.png' if kind=='Keyframe' else '.mp4'
        asset=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith(suffix));path=(DATA/asset['assetPath']).resolve(strict=True)
        check(f'{tid} controlled published asset',path.is_relative_to(DATA.resolve()))
        outputSha=sha(path)
        if entry.get('sha256'):check(f'{tid} checkpoint output hash unchanged',outputSha==entry['sha256'])
        receipt=json.loads((DATA/f'CharacterStoryTrace/task_{tid}/submission.json').read_text(encoding='utf-8'))
        tracePath=DATA/f'CharacterStoryTrace/task_{tid}/attempt_{detail["task"]["attempts"]}'
        history=json.loads((tracePath/'comfy-history.json').read_text(encoding='utf-8'));native=history.get(receipt['promptId'],history)
        check(f'{tid} real Comfy receipt success',native['status']['status_str']=='success' and native['status']['completed'])
        graph=json.loads((tracePath/'applied-workflow.json').read_text(encoding='utf-8'))
        check(f'{tid} actual executed graph matches trace',graph==native['prompt'][2])
        original=json.loads((tracePath/'requested-input.json').read_text(encoding='utf-8'));marker=original['parameters']['storyPipeline']
        check(f'{tid} exact original Shot plan',marker['planId']==entry['body']['planId'] and marker['shotId']==item['shotId'] and marker['episodeId']==pilot['episodeId'])
        expected=json.loads((OUT/(slot+'-'+kind+('-repair'+str(entry['repairAttempt']) if entry.get('repairAttempt') else '')+'-resolved.json')).read_text(encoding='utf-8'))
        check(f'{tid} frozen workflow hash',marker['workflowSha256']==expected['task']['parameters']['storyPipeline']['workflowSha256'])
        for source,digest in marker['inputHashes'].items():check(f'{tid} source bytes {digest[:12]}',sha(DATA/source)==digest)
        row=dict(taskId=tid,slot=slot,kind=kind,repairAttempt=entry.get('repairAttempt',0),assetPath=asset['assetPath'],sha256=outputSha,comfyPromptId=receipt['promptId'],executionTrace=str(tracePath),inputHashes=marker['inputHashes'],planId=marker['planId'],contentReview='NeedReview',publication='Blocked')
        if kind=='Keyframe':
            with Image.open(path) as img:
                check(f'{tid} established keyframe dimensions',img.size==(1536,864));actual=np.asarray(img.convert('RGB')).astype(np.int16)
            scene=original['parameters']['sceneLock']['payload'];source=scene['source'];check(f'{tid} frozen scene source hash',sha(DATA/source['path'])==source['sha256'])
            check(f'{tid} actual scene LoadImage bytes',sha(ROOT.parent/'ComfyUI/input'/graph['50']['inputs']['image'])==source['sha256'])
            check(f'{tid} compositor saved as final output',graph['18']['inputs']['images'][0]=='67' and graph['67']['inputs']['destination'][0]=='50')
            with Image.open(DATA/source['path']) as img:baseline=np.asarray(img.convert('RGB')).astype(np.int16)
            protected=np.ones((864,1536),dtype=bool)
            for region in scene['regions']:protected[region['y']:region['y']+region['height'],region['x']:region['x']+region['width']]=False
            delta=np.abs(actual-baseline)[protected];maxDelta=int(delta.max());changed=int(np.count_nonzero(np.max(delta,axis=1)))
            check(f'{tid} protected background retained within 8bit rounding',maxDelta<=1)
            row.update(sceneVersionId=original['parameters']['sceneLock']['versionId'],sceneSourceSha256=source['sha256'],protectedPixelCount=int(protected.sum()),changedProtectedPixels=changed,maxProtectedChannelDelta=maxDelta,meanProtectedAbsoluteDelta=float(delta.mean()),measurementMeaning='Pixel comparison outside the two declared actor regions; not an identity score or semantic content approval')
        else:
            actualFrame=Path(graph['5']['inputs']['image']);actualFrame=actualFrame if actualFrame.is_absolute() else ROOT.parent/'ComfyUI/input'/actualFrame
            check(f'{tid} actual H3 first-frame bytes',sha(actualFrame)==marker['inputSha256']==item['Keyframe']['sha256'])
            check(f'{tid} actual H3 parameter contract',graph['6']['inputs']['width']==864 and graph['6']['inputs']['height']==480 and graph['6']['inputs']['length']==124 and graph['14']['inputs']['fps']==24)
            check(f'{tid} actual H3 seed steps and action prompt',graph['7']['inputs']['noise_seed']==entry['body']['seed'] and graph['10']['inputs']['steps']==20 and graph['6']['inputs']['prompt']==original['parameters']['prompt'])
            probe=json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(OUT/f'{tid}-ffprobe.json',probe);video=next(s for s in probe['streams'] if s['codec_type']=='video')
            check(f'{tid} actual media 864x480 24fps 124frames',video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1' and int(video['nb_read_frames'])==124)
            check(f'{tid} exact valid duration',abs(float(probe['format']['duration'])-124/24)<.15)
            decoded=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120);check(f'{tid} full audio/video decode',decoded.returncode==0 and not decoded.stderr)
            response=requests.get('http://127.0.0.1:18080/api/media',params=dict(assetPath=asset['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30);check(f'{tid} browser Range media route',response.status_code==206 and len(response.content)==1024)
            frames=[round(i*123/11) for i in range(12)];folder=OUT/'frames'/str(tid);folder.mkdir(parents=True,exist_ok=True)
            if not (folder/'frame-12.png').exists():
                expression='+'.join('eq(n,'+str(n)+')' for n in frames)
                extracted=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-vf','select='+expression.replace(',','\\,'),'-fps_mode','passthrough',str(folder/'frame-%02d.png')],capture_output=True,timeout=120)
                if extracted.returncode:raise RuntimeError(extracted.stderr.decode('utf-8','replace'))
            sheet=Image.new('RGB',(432*4,266*3),'#101827');draw=ImageDraw.Draw(sheet)
            for i,n in enumerate(frames):
                with Image.open(folder/f'frame-{i+1:02d}.png') as image:sheet.paste(image.resize((432,240)),((i%4)*432,(i//4)*266))
                draw.text(((i%4)*432+8,(i//4)*266+244),f'Task {tid} | frame {n} | {n/24:.3f}s',fill='white')
            sheet.save(OUT/f'{tid}-contact-sheet.jpg',quality=95)
            row.update(width=video['width'],height=video['height'],fps=24,frames=124,duration=float(probe['format']['duration']),rawNativeAudioPresent=any(s['codec_type']=='audio' for s in probe['streams']),audioStrategy='PostDubbing',inspectionFrames=frames,contactSheet=str(OUT/f'{tid}-contact-sheet.jpg'))
        outputs.append(row)
    write(OUT/'pilot-media-checks.json',dict(status='Passed' if not pending else 'Running',checks=checks,outputs=outputs,pending=pending,humanApprovals=0))
    print(f'{len(checks)} media/provenance checks Passed; {len(outputs)} actual outputs checked, {len(pending)} tasks still incomplete. Content remains NeedReview.')

if __name__=='__main__':run()

"""Verify real story/Comfy provenance and extract actual frames for review."""
from pathlib import Path
import json, subprocess, uuid
from PIL import Image, ImageDraw
from character_plot_preview import Plot, ROOT, DATA, OUT, sha, write, mysql


def native_files(value, suffix):
    if isinstance(value,dict):
        if str(value.get('filename','')).lower().endswith(suffix) and value.get('type','output')=='output':
            base=(ROOT.parent/'ComfyUI/output').resolve(); path=(base/value.get('subfolder','')/value['filename']).resolve(strict=True)
            if not path.is_relative_to(base):raise RuntimeError('Comfy output escapes its directory')
            yield path
        else:
            for v in value.values():yield from native_files(v,suffix)
    elif isinstance(value,list):
        for v in value:yield from native_files(v,suffix)


def stored_task(task_id):
    row=mysql("SELECT JSON_OBJECT('id',id,'status',status,'dependency',dependency_task_id,'project',project_id,'workflow',workflow_id,'input',CAST(input_json AS JSON)) FROM generation_tasks WHERE id="+str(int(task_id)))
    return json.loads(row)


def verify():
    p=Plot();s=p.state;p.preserve();frame=s['Keyframe'];video=s['Video']
    assert frame['status']=='Succeeded' and video['status']=='Succeeded'
    output=OUT/('video-'+str(video['id']));output.mkdir(exist_ok=True)
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:
            write(output/'media-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    def trace(entry):
        directory=DATA/'CharacterStoryTrace'/('task_'+str(entry['id']))/'attempt_1'
        return (json.loads((directory/'requested-input.json').read_text(encoding='utf-8-sig')),
                json.loads((directory/'comfy-history.json').read_text(encoding='utf-8-sig')))
    fi,fh=trace(frame);vi,vh=trace(video);ft=stored_task(frame['id']);vt=stored_task(video['id'])
    fg=fh['prompt'][2];vg=vh['prompt'][2];fm=fi['parameters']['storyPipeline'];vm=vi['parameters']['storyPipeline']
    check('real business tasks succeeded and video depends on inspected keyframe',ft['status']==vt['status']=='Succeeded' and vt['dependency']==frame['id'] and ft['project']==vt['project']==s['projectId'])
    check('actual Comfy executions succeeded',fh['status']['completed'] and fh['status']['status_str']=='success' and vh['status']['completed'] and vh['status']['status_str']=='success')
    check('Comfy prompt IDs match recorded receipts',fh['prompt'][1]==frame['comfyPromptId'] and vh['prompt'][1]==video['comfyPromptId'])
    check('frozen shot and actor provenance',fm['planId']==vm['planId']==s['planId'] and fm['planSha256']==vm['planSha256']==s['planSha256'] and fm['shotId']==vm['shotId']==s['shotId'])
    first=ROOT.parent/'ComfyUI/input'/fg['4']['inputs']['image']
    check('actual Klein input equals explicitly approved legacy reference36',sha(first)==fm['inputSha256']==s['sourceReference']['assetSha256'])
    check('actual still prompt uses start and excludes future action','calm neutral closed mouth' in fg['7']['inputs']['text'] and 'As she recognizes the friend' not in fg['7']['inputs']['text'])
    check('actual keyframe output hash matches Comfy output',sha(DATA/frame['assetPath'])==frame['sha256'] and any(sha(path)==frame['sha256'] for path in native_files(fh['outputs'],'.png')))
    h3first=ROOT.parent/'ComfyUI/input'/vg['5']['inputs']['image']
    check('actual H3 first-frame bytes match inspected keyframe',sha(h3first)==vm['inputSha256']==frame['sha256']==frame['inspection']['payload']['sha256'])
    check('H3 graph uses verified 864x480 24fps 124frames 20steps',vg['6']['inputs']['width']==864 and vg['6']['inputs']['height']==480 and vg['6']['inputs']['length']==124 and vg['14']['inputs']['fps']==24 and vg['10']['inputs']['steps']==20)
    check('actual H3 prompt and seed match frozen request',vg['6']['inputs']['prompt']==vi['parameters']['prompt'] and vg['7']['inputs']['noise_seed']==video['body']['seed'] and 'As she recognizes the friend' in vg['6']['inputs']['prompt'])
    check('post dubbing strategy recorded',vi['parameters']['audioStrategy']=='PostDubbing')
    path=DATA/video['assetPath'];check('video matches actual native Comfy result',sha(path)==video['sha256'] and any(sha(f)==video['sha256'] for f in native_files(vh['outputs'],'.mp4')))
    current=next(x for x in p.api('/api/characters/19/references') if x['id']==36)
    check('selected reference remains approved and unchanged',current['reviewStatus']=='Approved' and current['available'] and current['assetSha256']==s['sourceReference']['assetSha256'])
    check('previous task and two-person hold checkpoints unchanged',all(sha(Path(f['path']))==f['sha256'] for f in s['protectedFiles']))
    ffprobe=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe';ffmpeg=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe'
    probe=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(output/'ffprobe.json',probe)
    stream=next(x for x in probe['streams'] if x['codec_type']=='video')
    check('FFprobe verifies width height fps and decoded frame count',stream['width']==864 and stream['height']==480 and stream['avg_frame_rate']=='24/1' and int(stream['nb_read_frames'])==124)
    check('duration follows frame contract',abs(float(probe['format']['duration'])-124/24)<.15)
    dec=subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120)
    check('complete video and audio decode without errors',dec.returncode==0 and not dec.stderr)
    response=p.s.get(p.base+'/api/media',params=dict(assetPath=video['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30)
    check('local media HTTP range works',response.status_code==206 and len(response.content)==1024)
    frames=output/'frames';indices=[round(i*123/24) for i in range(25)]
    if frames.exists() and len(list(frames.glob('frame-*.png'))) not in [0,25]:frames=output/('frames-recovery-'+uuid.uuid4().hex[:8])
    frames.mkdir(exist_ok=True)
    if not list(frames.glob('frame-*.png')):
        select='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',','\\,')
        subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-vf','select='+select,'-fps_mode','passthrough',str(frames/'frame-%02d.png')],check=True,timeout=120)
    check('25 actual decoded sampling frames retained',len(list(frames.glob('frame-*.png')))==25)
    sheet=Image.new('RGB',(2160,1330),'#101827');draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(indices):
        with Image.open(frames/f'frame-{i+1:02d}.png') as image:sheet.paste(image.resize((432,240)),((i%5)*432,(i//5)*266))
        draw.text(((i%5)*432+8,(i//5)*266+244),f'Task {video["id"]} | frame {n} | {n/24:.3f}s',fill='white')
    sheet.save(output/'contact-sheet.jpg',quality=95)
    write(output/'media-checks.json',dict(status='Passed',checks=checks,keyframeTask=frame['id'],videoTask=video['id'],frameSha256=frame['sha256'],videoSha256=video['sha256'],dimensions=[stream['width'],stream['height']],fps=stream['avg_frame_rate'],frames=124,duration=probe['format']['duration'],nativeAudioPresent=any(x['codec_type']=='audio' for x in probe['streams']),sampleIndices=indices,contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' technical checks Passed; decoded frames require separate visual inspection.')


if __name__=='__main__':verify()

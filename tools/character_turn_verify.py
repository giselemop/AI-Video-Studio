"""Verify and extract frames from a registered, actually completed repair."""
from pathlib import Path
import json,subprocess,sys,uuid
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).parent))
from character_turn_repair import Repair,ROOT,DATA,OUT,sha,write,mysql

def run(number):
    r=Repair();a=r.state['attempts'][number-1];folder=OUT/f'attempt-{number}'
    if a.get('status')!='Succeeded':raise RuntimeError('Actual video task must succeed before verification')
    trace=json.loads((folder/'task-trace.json').read_text(encoding='utf-8'));history=json.loads((folder/'comfy-history.json').read_text(encoding='utf-8'));native=history[trace['comfyPromptId']];graph=native['prompt'][2]
    binding=trace['input']['parameters']['characterLibrary'];execution=trace['input']['minimaxLocalExecution'];checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:
            write(folder/'media-checks.json',dict(status='Failed',checks=checks,taskId=a['taskId']));raise AssertionError(name)
    check('real business task and parent lineage retained',trace['id']==a['taskId'] and trace['dependencyTaskId']==a['parentTaskId'] and trace['status']=='Succeeded')
    check('actual Comfy task completed successfully',native['status']['completed'] and native['status']['status_str']=='success')
    check('same frozen character version and approved source',binding['characterId']==19 and binding['versionId']==3 and binding['referenceId']==36 and binding['versionSha256']==r.state['versionSnapshot']['sha256'])
    first=Path(graph['5']['inputs']['image']);first=first if first.is_absolute() else ROOT.parent/'ComfyUI/input'/first
    check('actual H3 first frame hash equals reference36',sha(first)==binding['referenceSha256']==execution['firstFrame']['sha256']==r.state['source']['sha256'])
    check('same registered local workflow hash',execution['workflowSha256']==binding['workflowSha256']==r.state['versionSnapshot']['payload']['workflow']['sha256'])
    check('H3 verified profile unchanged',graph['6']['inputs']['width']==864 and graph['6']['inputs']['height']==480 and graph['6']['inputs']['length']==124 and graph['14']['inputs']['fps']==24 and graph['10']['inputs']['steps']==20)
    check('actual prompt and seed match targeted request',graph['6']['inputs']['prompt']==trace['input']['parameters']['prompt'] and graph['7']['inputs']['noise_seed']==a['request']['seed'])
    check('targeted prompt differs from failed original',a['request']['prompt']!=json.loads((DATA/'CharacterSinglePreview20261027/run.json').read_text(encoding='utf-8'))['request']['prompt'])
    def native_files(value):
        if isinstance(value,dict):
            if str(value.get('filename','')).lower().endswith('.mp4') and value.get('type','output')=='output':
                file=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve(strict=True)
                if not file.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise RuntimeError('Native output outside ComfyUI')
                yield file
            else:
                for x in value.values():yield from native_files(x)
        elif isinstance(value,list):
            for x in value:yield from native_files(x)
    check('published file matches actual native Comfy result',any(sha(f)==a['sha256'] for f in native_files(native['outputs'])))
    path=DATA/a['assetPath'];check('generated output SHA256',sha(path)==a['sha256'])
    ffprobe=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe';ffmpeg=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe'
    probe=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(folder/'ffprobe.json',probe);v=next(s for s in probe['streams'] if s['codec_type']=='video')
    check('real dimensions and frame count',v['width']==864 and v['height']==480 and v['avg_frame_rate']=='24/1' and int(v['nb_read_frames'])==124)
    check('media duration within actual contract',abs(float(probe['format']['duration'])-124/24)<.15)
    decoded=subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120);check('full decode of all streams',decoded.returncode==0 and not decoded.stderr)
    response=r.s.get(r.base+'/api/media',params=dict(assetPath=a['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30);check('browser range support',response.status_code==206 and len(response.content)==1024)
    check('previous actual video and checkpoint unchanged',sha(DATA/r.state['baseVideoPath'])==r.state['baseVideoSha256'] and sha(DATA/'CharacterSinglePreview20261027/run.json')==r.state['baseRunSha256'])
    check('separate scene review hold unchanged',sha(DATA/'CharacterScene20261027/run.json')==r.state['sceneCheckpointSha256'])
    ids=sorted(int(v) for v in mysql('SELECT id FROM generation_tasks WHERE project_id='+str(r.state['projectId'])+' ORDER BY id;').splitlines() if v)
    check('only registered targeted attempts exist in project',ids==sorted(x['taskId'] for x in r.state['attempts'] if x.get('taskId')) and len(ids)<=2)
    current=next(x for x in r.api('/api/characters/19/references') if x['id']==36);check('source reference remains approved and available',current['reviewStatus']=='Approved' and current['available'] and current['assetSha256']==r.state['source']['sha256'])
    frames=folder/'frames';indices=[round(i*123/24) for i in range(25)]
    if frames.exists() and len(list(frames.glob('frame-*.png'))) not in [0,25]:frames=folder/('frames-recovery-'+uuid.uuid4().hex[:8])
    frames.mkdir(exist_ok=True)
    if len(list(frames.glob('frame-*.png')))==0:
        select='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',','\\,')
        subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-vf','select='+select,'-fps_mode','passthrough',str(frames/'frame-%02d.png')],check=True,timeout=120)
    check('25 actual decoded frames retained',len(list(frames.glob('frame-*.png')))==25)
    sheet=Image.new('RGB',(2160,1330),'#101827');draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(indices):
        with Image.open(frames/f'frame-{i+1:02d}.png') as frame:sheet.paste(frame.resize((432,240)),((i%5)*432,(i//5)*266))
        draw.text(((i%5)*432+8,(i//5)*266+244),f'Task {a["taskId"]} | frame {n} | {n/24:.3f}s',fill='white')
    sheet.save(folder/'contact-sheet.jpg',quality=95)
    write(folder/'media-checks.json',dict(status='Passed',checks=checks,taskId=a['taskId'],sourceReferenceSha256=binding['referenceSha256'],outputSha256=a['sha256'],frames=124,fps=24,width=864,height=480,duration=probe['format']['duration'],nativeAudioPresent=any(s['codec_type']=='audio' for s in probe['streams']),frameIndices=indices,frameFolder=str(frames),contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' actual video, source, integrity and media checks Passed; content inspection remains separate.')
if __name__=='__main__':run(int(sys.argv[1]) if len(sys.argv)>1 else 1)

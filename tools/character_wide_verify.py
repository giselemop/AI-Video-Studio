"""Verify real Comfy provenance and actual cutaway media."""
import argparse,json,subprocess,sys
from PIL import Image,ImageDraw
from character_wide_cutaway import Cutaway,ROOT,DATA,OUT,sha,write,mysql

FFMPEG=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe';FFPROBE=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe'
def native_files(value,ext):
    if isinstance(value,dict):
        if str(value.get('filename','')).lower().endswith(ext) and value.get('type','output')=='output':
            base=(ROOT.parent/'ComfyUI/output').resolve();path=(base/value.get('subfolder','')/value['filename']).resolve(strict=True)
            if not path.is_relative_to(base):raise RuntimeError('Comfy output is outside its root')
            yield path
        else:
            for item in value.values():yield from native_files(item,ext)
    elif isinstance(value,list):
        for item in value:yield from native_files(item,ext)
def task(tid):
    result=mysql("SELECT JSON_OBJECT('id',id,'status',status,'comfyPromptId',comfy_prompt_id,'dependency',dependency_task_id,'input',CAST(input_json AS JSON)) FROM generation_tasks WHERE id="+str(int(tid)))
    return json.loads(result)

def main(kind):
    p=Cutaway();s=p.state;p.preserve();e=s['images'][-1] if kind=='image' else s['video'];assert e['status']=='Succeeded'
    out=OUT/('image-'+str(e['id']) if kind=='image' else 'video-'+str(e['id']));out.mkdir(exist_ok=True);t=task(e['id']);response=p.s.get('http://127.0.0.1:8188/history/'+t['comfyPromptId'],timeout=30);response.raise_for_status();allHistory=response.json();history=allHistory[t['comfyPromptId']];write(out/'comfy-history.json',history);write(out/'task-trace.json',t);g=history['prompt'][2];checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(OUT/(kind+'-checks.json'),dict(status='Failed',checks=checks,taskId=e['id']));raise AssertionError(name)
    check('real business task and Comfy history succeeded',t['status']=='Succeeded' and history['status']['completed'] and history['status']['status_str']=='success')
    check('actual output matches Comfy and stored hash',sha(DATA/e['assetPath'])==e['sha256'] and any(sha(x)==e['sha256'] for x in native_files(history['outputs'],'.png' if kind=='image' else '.mp4')))
    if kind=='image':
        source=ROOT.parent/'ComfyUI/input'/g['4']['inputs']['image'];check('actual location-reference input matches preserved frame',sha(source)==s['locationFrameSha256'])
        check('registered Klein graph matches requested frame spec',g['13']['inputs']['width']==1536 and g['13']['inputs']['height']==864 and g['13']['inputs']['steps']==4 and g['14']['inputs']['noise_seed']==e['body']['parameters']['seed'])
        with Image.open(DATA/e['assetPath']) as im:check('actual output image size',im.size==(1536,864))
        check('actual prompt requests person-free establishing view',g['7']['inputs']['text']==e['body']['parameters']['positive'] and 'unoccupied' in g['7']['inputs']['text'])
    else:
        frame=s['images'][-1];source=ROOT.parent/'ComfyUI/input'/g['5']['inputs']['image'];check('H3 actual first frame matches reviewed environment image',sha(source)==frame['sha256'] and t['dependency']==frame['id'])
        check('H3 actual graph retains validated profile',g['6']['inputs']['width']==864 and g['6']['inputs']['height']==480 and g['6']['inputs']['length']==124 and g['14']['inputs']['fps']==24 and g['10']['inputs']['steps']==20)
        check('actual prompt and seed match request',g['6']['inputs']['prompt']==e['body']['parameters']['prompt'] and g['7']['inputs']['noise_seed']==e['body']['parameters']['seed'])
        probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(DATA/e['assetPath'])],encoding='utf-8'));write(out/'ffprobe.json',probe);v=next(x for x in probe['streams'] if x['codec_type']=='video')
        check('actual 864x480 24fps 124 frames',v['width']==864 and v['height']==480 and v['avg_frame_rate']=='24/1' and int(v['nb_read_frames'])==124)
        result=subprocess.run([str(FFMPEG),'-v','error','-i',str(DATA/e['assetPath']),'-f','null','-'],capture_output=True,timeout=120);check('full native audio and video decode',result.returncode==0 and not result.stderr)
        frames=out/'frames';frames.mkdir(exist_ok=True);indices=[0,12,24,36,48,60,72,84,96,108,116,123]
        if not list(frames.glob('frame-*.png')):
            select='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',',r'\,')
            subprocess.run([str(FFMPEG),'-v','error','-i',str(DATA/e['assetPath']),'-vf','select='+select,'-fps_mode','passthrough','-n',str(frames/'frame-%02d.png')],check=True,timeout=120)
        check('12 actual frames extracted',len(list(frames.glob('frame-*.png')))==12)
        sheet=Image.new('RGB',(1728,798),'#101827');draw=ImageDraw.Draw(sheet)
        for i,n in enumerate(indices):
            with Image.open(frames/f'frame-{i+1:02d}.png') as frame:sheet.paste(frame.resize((432,240)),((i%4)*432,(i//4)*266))
            draw.text(((i%4)*432+8,(i//4)*266+244),f'frame {n} | {n/24:.3f}s',fill='white')
        sheet.save(out/'contact-sheet.jpg',quality=95)
    p.preserve();write(OUT/(kind+'-checks.json'),dict(status='Passed',checks=checks,taskId=e['id'],sha256=e['sha256'],comfyPromptId=t['comfyPromptId'],contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' real '+kind+' provenance/media checks Passed; visual inspection remains separate.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['image','video']);main(parser.parse_args().kind)

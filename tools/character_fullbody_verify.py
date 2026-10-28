"""Verify actual single-reference Klein and H3 executions for the preview."""
import argparse
import json
import subprocess
from PIL import Image, ImageDraw
from character_fullbody_scene import Run, ROOT, DATA, OUT, sha, write
from character_wide_verify import FFMPEG, FFPROBE, native_files, task

def main(kind):
    p=Run(); p.preserve(); p.require_reference()
    e=p.state['images' if kind=='image' else 'videos'][-1]
    if e.get('status')!='Succeeded': raise RuntimeError('The real task has not succeeded')
    folder=OUT/(kind+'-'+str(e['id'])); folder.mkdir(exist_ok=True)
    trace=task(e['id'])
    response=p.s.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30)
    response.raise_for_status()
    h=response.json()[trace['comfyPromptId']]
    write(folder/'comfy-history.json',h)
    write(folder/'task-trace.json',trace)
    graph=h['prompt'][2]
    result=dict(taskId=e['id'],sha256=e['sha256'],status='Running',checks=[],
                contentReview='NeedReview',publication='Blocked')
    def check(name,ok):
        result['checks'].append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:
            result['status']='Failed'; write(folder/'checks.json',result); write(OUT/(kind+'-checks.json'),result)
            raise AssertionError(name)
    check('business task and actual Comfy history completed',
          trace['status']=='Succeeded' and h['status']['completed'] and h['status']['status_str']=='success')
    check('real stored output matches the native Comfy output',
          sha(DATA/e['assetPath'])==e['sha256']
          and any(sha(x)==e['sha256'] for x in native_files(h['outputs'],'.png' if kind=='image' else '.mp4')))
    if kind=='image':
        source=ROOT.parent/'ComfyUI/input'/graph['4']['inputs']['image']
        check('actual single image input matches frozen story frame',sha(source)==e['sourceSha256'])
        check('request input and task dependency match the selected source',
              e['body']['inputImagePath']==e['sourcePath'] and trace['dependency']==e['body']['dependencyTaskId'])
        check('actual requested prompt and seed were executed',
              graph['7']['inputs']['text']==e['body']['parameters']['positive']
              and graph['14']['inputs']['noise_seed']==e['body']['parameters']['seed'])
        check('Klein execution is 1536x864 with four steps',
              graph['13']['inputs']['width']==1536 and graph['13']['inputs']['height']==864
              and graph['13']['inputs']['steps']==4)
        with Image.open(DATA/e['assetPath']) as im:
            check('real output image has requested dimensions',im.size==(1536,864))
    else:
        frame=p.state['images'][-1]
        source=ROOT.parent/'ComfyUI/input'/graph['5']['inputs']['image']
        check('actual H3 first frame matches the inspected candidate',
              sha(source)==frame['sha256'] and trace['dependency']==frame['id'])
        check('H3 graph keeps the established 864x480 24fps 124-frame 20-step profile',
              graph['6']['inputs']['width']==864 and graph['6']['inputs']['height']==480
              and graph['6']['inputs']['length']==124 and graph['14']['inputs']['fps']==24
              and graph['10']['inputs']['steps']==20)
        check('actual H3 prompt and seed match the request',
              graph['6']['inputs']['prompt']==e['body']['parameters']['prompt']
              and graph['7']['inputs']['noise_seed']==e['body']['parameters']['seed'])
        probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-count_frames',
            '-show_streams','-show_format','-of','json',str(DATA/e['assetPath'])],encoding='utf-8'))
        write(folder/'ffprobe.json',probe)
        video=next(x for x in probe['streams'] if x['codec_type']=='video')
        check('actual output has 124 frames at 24fps and 864x480',
              video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1'
              and int(video['nb_read_frames'])==124)
        decoded=subprocess.run([str(FFMPEG),'-v','error','-i',str(DATA/e['assetPath']),
            '-f','null','-'],capture_output=True,timeout=120)
        check('full native audio and video decode',decoded.returncode==0 and not decoded.stderr)
        frames=folder/'frames'; frames.mkdir(exist_ok=True)
        indices=[0,12,24,36,48,60,72,84,96,108,116,123]
        files=[frames/f'frame-{i+1:02d}.png' for i in range(len(indices))]
        if any(x.exists() for x in files) and not all(x.exists() for x in files):
            raise RuntimeError('Partial frame evidence will not be overwritten')
        if not files[0].exists():
            selection='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',',r'\,')
            subprocess.run([str(FFMPEG),'-v','error','-i',str(DATA/e['assetPath']),
                '-vf','select='+selection,'-fps_mode','passthrough','-an','-n',str(frames/'frame-%02d.png')],
                check=True,timeout=120)
        check('12 actual frames extracted',all(x.exists() for x in files))
        sheet=Image.new('RGB',(1728,798),'#101827'); draw=ImageDraw.Draw(sheet)
        for i,n in enumerate(indices):
            with Image.open(files[i]) as im: sheet.paste(im.resize((432,240)),((i%4)*432,(i//4)*266))
            draw.text(((i%4)*432+8,(i//4)*266+244),f'frame {n} | {n/24:.3f}s',fill='white')
        sheet.save(folder/'contact-sheet.jpg',quality=95)
    p.preserve()
    result.update(status='Passed',comfyPromptId=trace['comfyPromptId'])
    write(folder/'checks.json',result)
    write(OUT/(kind+'-checks.json'),result)
    print(str(len(result['checks']))+' actual '+kind+' checks Passed; visual and user review remain separate.')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('kind',choices=['image','video'])
    main(a.parse_args().kind)

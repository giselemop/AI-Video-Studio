"""Verify a completed continuation and extract its actual frames and tail."""
import argparse,json,msvcrt,subprocess,uuid
from PIL import Image,ImageDraw
from character_continuation import Continuation,ROOT,DATA,OUT,sha,write
from character_plot_verify import native_files,stored_task

FFMPEG=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe';FFPROBE=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe'
def main(number):
 with (OUT/'controller.lock').open('a+b') as lock:
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    p=Continuation();s=p.state;p.preserve();entry=next(x for x in s['shots'] if x['number']==number);assert entry['status']=='Succeeded'
    folder=OUT/('shot-'+str(number)+'-task-'+str(entry['videoTaskId']));folder.mkdir(exist_ok=True);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(folder/'technical-checks.json',dict(status='Failed',checks=checks,videoTaskId=entry['videoTaskId']));raise AssertionError(name)
    raw=DATA/entry['assetPath'];tid=entry['videoTaskId'];trace=DATA/('CharacterStoryTrace/task_'+str(tid))/'attempt_1'
    requested=json.loads((trace/'requested-input.json').read_text(encoding='utf-8-sig'));history=json.loads((trace/'comfy-history.json').read_text(encoding='utf-8-sig'));graph=history['prompt'][2];task=stored_task(tid)
    marker=requested['parameters']['storyPipeline'];source=marker['continuation'];body=entry['videoBody']
    check('real task completed and depends on previous video',task['status']=='Succeeded' and task['dependency']==body['continuationSourceTaskId'] and task['project']==s['projectId'])
    check('actual Comfy execution completed',history['status']['completed'] and history['status']['status_str']=='success' and history['prompt'][1]==entry['comfyPromptId'])
    check('same episode and frozen shot plan',marker['episodeId']==s['episodeId'] and marker['shotId']==entry['shotId'] and marker['planId']==entry['planId'] and marker['planSha256']==entry['planSha256'])
    check('source video, review and tail provenance frozen',source['sourceTaskId']==body['continuationSourceTaskId'] and source['sourceReviewId']==body['continuationReviewId'] and source['frameIndex']==123 and source['frameSha256']==body['continuationFrameSha256'])
    check('source video file and actual tail file hashes match',sha(DATA/source['sourceVideoPath'])==source['sourceVideoSha256'] and sha(DATA/source['framePath'])==source['frameSha256'])
    copied=ROOT.parent/'ComfyUI/input'/graph['5']['inputs']['image'];check('actual H3 first image matches inspected tail',sha(copied)==source['frameSha256']==marker['inputSha256'])
    check('actual H3 graph retains 864x480 24fps 124frames 20steps',graph['6']['inputs']['width']==864 and graph['6']['inputs']['height']==480 and graph['6']['inputs']['length']==124 and graph['14']['inputs']['fps']==24 and graph['10']['inputs']['steps']==20)
    check('actual prompt and seed match frozen request',graph['6']['inputs']['prompt']==requested['parameters']['prompt'] and graph['7']['inputs']['noise_seed']==body['seed'])
    check('asset matches native Comfy output',sha(raw)==entry['sha256'] and any(sha(x)==entry['sha256'] for x in native_files(history['outputs'],'.mp4')))
    probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(raw)],encoding='utf-8'));write(folder/'ffprobe.json',probe)
    video=next(x for x in probe['streams'] if x['codec_type']=='video')
    check('actual video size rate frames duration',video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1' and int(video['nb_read_frames'])==124 and abs(float(probe['format']['duration'])-124/24)<.15)
    decode=subprocess.run([str(FFMPEG),'-v','error','-i',str(raw),'-f','null','-'],capture_output=True,timeout=120);check('full video and native audio decode',decode.returncode==0 and not decode.stderr)
    response=p.session.get(p.base+'/api/media',params={'assetPath':entry['assetPath']},headers={'Range':'bytes=0-1023'},timeout=30);check('browser media range works',response.status_code==206 and len(response.content)==1024)
    frames=folder/'frames';frames.mkdir(exist_ok=True);indices=[round(i*123/24) for i in range(25)]
    if len(list(frames.glob('frame-*.png')))==0:
        expression='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',','\\,')
        subprocess.run([str(FFMPEG),'-v','error','-i',str(raw),'-vf','select='+expression,'-fps_mode','passthrough','-n',str(frames/'frame-%02d.png')],check=True,timeout=120)
    check('25 actual decoded frames retained',len(list(frames.glob('frame-*.png')))==25)
    with Image.open(DATA/source['framePath']) as last,Image.open(frames/'frame-01.png') as first:
        comparison=Image.new('RGB',(1728,510),'#101827');comparison.paste(last.convert('RGB'),(0,0));comparison.paste(first.convert('RGB'),(864,0))
        label=ImageDraw.Draw(comparison);label.text((8,486),'Previous actual final frame',fill='white');label.text((872,486),'New actual first frame',fill='white');comparison.save(folder/'boundary-comparison.jpg',quality=95)
    tail=folder/'tail-123.png'
    if not tail.exists():subprocess.run([str(FFMPEG),'-v','error','-i',str(raw),'-vf','select=eq(n\\,123)','-frames:v','1','-pix_fmt','rgb24','-n',str(tail)],check=True,timeout=120)
    check('extracted final frame matches final decoded sample',sha(tail)==sha(frames/'frame-25.png'))
    sheet=Image.new('RGB',(2160,1330),'#101827');draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(indices):
        with Image.open(frames/f'frame-{i+1:02d}.png') as image:sheet.paste(image.resize((432,240)),((i%5)*432,(i//5)*266))
        draw.text(((i%5)*432+8,(i//5)*266+244),f'Task {tid} | frame {n} | {n/24:.3f}s',fill='white')
    sheet.save(folder/'contact-sheet.jpg',quality=95)
    entry.update(tailPath=tail.relative_to(DATA).as_posix(),tailSha256=sha(tail),technicalCheckPath=(folder/'technical-checks.json').relative_to(DATA).as_posix());p.save();p.preserve()
    write(folder/'technical-checks.json',dict(status='Passed',checks=checks,videoTaskId=tid,sha256=entry['sha256'],tailPath=entry['tailPath'],tailSha256=entry['tailSha256'],sampleIndices=indices,contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' technical checks Passed; visually inspect contact sheet and tail before continuation.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('number',type=int,choices=[2,3]);main(parser.parse_args().number)

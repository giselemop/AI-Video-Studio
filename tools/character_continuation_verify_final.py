"""Verify the actual edited clip, its sources, audio timing and decoded frames."""
import json,msvcrt,subprocess,uuid
import numpy as np
from scipy.signal import fftconvolve
from PIL import Image,ImageDraw
from character_continuation import Continuation,ROOT,DATA,OUT,sha,write
from character_plot_verify import stored_task

FFMPEG=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe';FFPROBE=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe';RATE=24000
def pcm(path):
    data=subprocess.check_output([str(FFMPEG),'-v','error','-i',str(path),'-vn','-ac','1','-ar',str(RATE),'-f','f32le','-'],timeout=120)
    return np.frombuffer(data,dtype='<f4').astype(np.float64)
def locate(signal,source,start):
    margin=int(.08*RATE);at=int(round(start*RATE));begin=max(0,at-margin);end=min(len(signal),at+len(source)+margin);part=signal[begin:end]
    if len(part)<len(source):raise RuntimeError('Audio segment too short')
    correlation=fftconvolve(part,source[::-1],mode='valid');energy=np.cumsum(np.r_[0,part*part]);window=energy[len(source):]-energy[:-len(source)]
    scores=correlation/np.maximum(np.sqrt(window*np.sum(source*source)),1e-12);index=int(np.argmax(scores))
    return dict(correlation=float(scores[index]),offsetSeconds=(begin+index-at)/RATE)

def main():
 with (OUT/'controller.lock').open('a+b') as lock:
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    p=Continuation();s=p.state;p.preserve();final=s['finalVideo'];silent=s['silentPreview'];assert final['status']==silent['status']=='Succeeded'
    folder=OUT/'final';folder.mkdir(exist_ok=True);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(OUT/'final-technical-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    silentTask=stored_task(silent['taskId']);finalTask=stored_task(final['taskId']);story=silentTask['input']['parameters']['storyPreview'];args=finalTask['input']['parameters']
    clips=story['clips'];expected=[s['sourceVideoTaskId']]+[x['videoTaskId'] for x in s['shots']]
    check('reviewed multi-shot preview contains actual videos in order',[x['taskId'] for x in clips]==expected and all(sha(DATA/x['path'])==x['sha256'] for x in clips))
    check('silent preview removes native H3 audio and retains PostDubbing',story['audioStrategy']=='PostDubbing' and silentTask['status']=='Succeeded')
    check('final queued task depends on checked preview',finalTask['status']=='Succeeded' and finalTask['dependency']==silent['taskId'] and args['files']==[silent['assetPath']])
    checksources=args['sourceChecks'];check('final video, audio and subtitle inputs match frozen SHA256',len(checksources)==6 and all(sha(DATA/x['path'])==x['sha256'] for x in checksources))
    check('three narration tracks and original music remain separate',len(args['audioTracks'])==4 and [x['path'] for x in args['audioTracks']]==[x['assetPath'] for x in s['narration']]+[s['music']['assetPath']])
    check('music fades before the 15 second end',args['audioTracks'][-1]['fadeOutStartSeconds']==13.8 and args['audioTracks'][-1]['fadeOutDurationSeconds']==1.2 and args['originalAudioVolume']==0)
    raw=DATA/final['assetPath'];check('delivered artifact hash matches task',sha(raw)==final['sha256'])
    probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(raw)],encoding='utf-8'));write(folder/'ffprobe.json',probe)
    video=next(x for x in probe['streams'] if x['codec_type']=='video');audio=next((x for x in probe['streams'] if x['codec_type']=='audio'),None)
    check('15s video is 864x480 24fps 360 decoded frames',video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1' and int(video['nb_read_frames'])==360 and abs(float(probe['format']['duration'])-15)<.08)
    check('actual AAC audio stream is present',audio is not None and audio['codec_name']=='aac')
    decoded=subprocess.run([str(FFMPEG),'-v','error','-i',str(raw),'-f','null','-'],capture_output=True,timeout=180);check('complete final audio and video decode',decoded.returncode==0 and not decoded.stderr)
    response=p.session.get(p.base+'/api/media',params={'assetPath':final['assetPath']},headers={'Range':'bytes=0-1023'},timeout=30);check('browser HTTP range',response.status_code==206 and len(response.content)==1024)
    mix=pcm(raw);voice=[]
    for e in s['narration']:
        match=locate(mix,pcm(DATA/e['assetPath']),e['startSeconds']);voice.append(dict(taskId=e['taskId'],**match))
    check('all narration sources appear near their planned times',all(x['correlation']>.55 and abs(x['offsetSeconds'])<.08 for x in voice))
    music=pcm(DATA/s['music']['assetPath']);gaps=[]
    for a,b in [(4.7,5.3),(9.0,10.6)]:
        start=int(a*RATE);end=int(b*RATE);m=music[start:end];f=mix[start:end];score=float(np.dot(m,f)/(max(np.linalg.norm(m)*np.linalg.norm(f),1e-12)));gaps.append(dict(start=a,end=b,correlation=score,rms=float(np.sqrt(np.mean(f*f)))))
    check('music is present between the narration lines',all(x['correlation']>.5 and x['rms']>.001 for x in gaps))
    peak=float(np.max(np.abs(mix)));clipped=float(np.mean(np.abs(mix)>=.999));check('audio does not show sustained digital clipping',peak>0.01 and clipped<.001)
    frames=folder/'frames';frames.mkdir(exist_ok=True);indices=[0,24,110,123,124,125,240,247,248,249,320,359]
    if not list(frames.glob('frame-*.png')):
        expression='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',','\\,')
        subprocess.run([str(FFMPEG),'-v','error','-i',str(raw),'-vf','select='+expression,'-fps_mode','passthrough','-n',str(frames/'frame-%02d.png')],check=True,timeout=120)
    check('boundary and subtitle samples decoded',len(list(frames.glob('frame-*.png')))==len(indices))
    sheet=Image.new('RGB',(1728,798),'#101827');draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(indices):
        with Image.open(frames/f'frame-{i+1:02d}.png') as image:sheet.paste(image.resize((432,240)),((i%4)*432,(i//4)*266))
        draw.text(((i%4)*432+8,(i//4)*266+244),f'frame {n} | {n/24:.3f}s',fill='white')
    sheet.save(folder/'contact-sheet.jpg',quality=95);p.preserve()
    write(OUT/'final-technical-checks.json',dict(status='Passed',checks=checks,finalTaskId=final['taskId'],outputSha256=final['sha256'],durationSeconds=15,frames=360,fps=24,voice=voice,musicGaps=gaps,peak=peak,clippedSampleFraction=clipped,contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' real final media, timeline, audio and provenance checks Passed; visual and listening review remain separate.')

if __name__=='__main__':main()

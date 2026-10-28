"""Measure the actual 16.5-second edit, source frames and re-timed narration."""
import io
import json
import subprocess
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageStat
from character_fullbody_scene import Run, DATA, OUT, sha, write
from character_wide_verify import FFMPEG, FFPROBE, task

EVIDENCE=OUT/'final'
REPORT=OUT/'final-checks.json'

def run(args):
    r=subprocess.run([str(x) for x in args],capture_output=True,timeout=180)
    if r.returncode: raise RuntimeError(r.stderr.decode('utf-8',errors='replace')[:2500])
    return r.stdout

def extract(path,indices,name):
    directory=EVIDENCE/name; directory.mkdir(parents=True,exist_ok=True)
    files=[directory/f'frame-{i+1:02d}.png' for i in range(len(indices))]
    if any(x.exists() for x in files) and not all(x.exists() for x in files):
        raise RuntimeError('Partial frame evidence will not be overwritten')
    if not files[0].exists():
        selection='+'.join('eq(n,'+str(n)+')' for n in indices).replace(',',r'\,')
        run([FFMPEG,'-v','error','-i',path,'-vf','select='+selection,'-fps_mode',
             'passthrough','-an','-n',directory/'frame-%02d.png'])
    return dict(zip(indices,files))

def mae(a,b):
    with Image.open(a) as x, Image.open(b) as y:
        return round(sum(ImageStat.Stat(ImageChops.difference(x.convert('RGB'),y.convert('RGB'))).mean)/3,3)

def pcm(path):
    data=run([FFMPEG,'-v','error','-i',path,'-map','0:a:0','-ac','1','-ar','16000',
              '-f','s16le','-acodec','pcm_s16le','-'])
    return np.frombuffer(data,dtype='<i2').astype(np.float64)/32768.0

def music_pcm(path,tempo):
    data=run([FFMPEG,'-v','error','-i',path,'-map','0:a:0','-af',f'atempo={tempo},asetpts=PTS-STARTPTS',
              '-ac','1','-ar','16000','-f','s16le','-acodec','pcm_s16le','-'])
    return np.frombuffer(data,dtype='<i2').astype(np.float64)/32768.0

def correlation(audio,voice,start):
    x=voice-voice.mean()
    norm=np.linalg.norm(x)
    scores=[]
    for shift in range(-1600,1601,160):
        offset=round(start*16000)+shift
        if offset<0 or offset+len(x)>len(audio):continue
        y=audio[offset:offset+len(x)]
        y=y-y.mean()
        denom=norm*np.linalg.norm(y)
        if denom: scores.append((float(np.dot(x,y)/denom),shift/16000))
    return max(scores) if scores else (0,0)

def main():
    p=Run();s=p.state;p.preserve();p.require_reference()
    EVIDENCE.mkdir(exist_ok=True)
    e=s['editTasks']['final'];final=DATA/e['assetPath'];base=DATA/s['basePath'];wide=DATA/s['videos'][-1]['assetPath']
    report=dict(status='Running',taskId=e['id'],checks=[],contentReview='NeedReview',publication='Blocked')
    def check(name,ok,detail=None):
        item=dict(name=name,status='Passed' if ok else 'Failed')
        if detail is not None:item['detail']=detail
        report['checks'].append(item)
        if not ok:
            report['status']='Failed';write(REPORT,report);raise AssertionError(name+': '+str(detail))
    check('all five business edit tasks and their real files match',
          set(s['editTasks'])=={'head','insert','tail','picture','final'}
          and all(x.get('status')=='Succeeded' and sha(DATA/x['assetPath'])==x['sha256']
                  and task(x['id'])['status']=='Succeeded' for x in s['editTasks'].values()))
    check('image and video actual provenance passed',
          all(json.loads((OUT/(name+'-checks.json')).read_text(encoding='utf-8'))['status']=='Passed'
              for name in ['image','video']))
    check('image and selected range were inspected; full source video remains failed',
          s['images'][-1]['inspection']['decision']=='Passed'
          and s['videos'][-1]['inspection']['decision']=='Failed'
          and s['videos'][-1]['rangeInspection']['decision']=='Passed'
          and s['videos'][-1]['rangeInspection']['startFrame']==0
          and s['videos'][-1]['rangeInspection']['endFrame']==36)
    probe=json.loads(run([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',final]))
    write(EVIDENCE/'ffprobe.json',probe)
    v=next(x for x in probe['streams'] if x['codec_type']=='video')
    a=next(x for x in probe['streams'] if x['codec_type']=='audio')
    info=dict(width=v['width'],height=v['height'],fps=v['avg_frame_rate'],
              frames=int(v['nb_read_frames']),audio=a['codec_name'],duration=float(probe['format']['duration']))
    report['media']=info
    check('16.5s at 864x480 24fps 396 frames with AAC',
          info['width']==864 and info['height']==480 and info['fps']=='24/1' and info['frames']==396
          and info['audio']=='aac' and abs(info['duration']-16.5)<0.05,info)
    run([FFMPEG,'-v','error','-i',final,'-f','null','-'])
    check('full audio and video decode',True)
    final_ix=[0,24,160,209,210,225,245,246,268,281,282,348,395]
    base_ix=[0,24,160,209,210,232,245,246,312,359]
    new_ix=[0,15,35]
    ff=extract(final,final_ix,'final-frames');bf=extract(base,base_ix,'base-frames');wf=extract(wide,new_ix,'fullbody-frames')
    before={str(n):mae(ff[n],bf[n]) for n in [0,24,160,209]}
    insert={str(n):mae(ff[n],wf[n-210]) for n in [210,225,245]}
    after={str(n):mae(ff[n],bf[n-36]) for n in [246,268,281,282,348,395]}
    diffs=dict(before=before,insert=insert,after=after)
    report['sampledRgbMeanAbsoluteDifferences']=diffs
    check('decoded frames match source before, within and after insertion',
          max([*before.values(),*insert.values(),*after.values()])<8,diffs)
    tracks=e['body']['parameters']['audioTracks']
    check('audio mix references the same three narration sources and retimes the third',
          len(tracks)==4 and [t['path'] for t in tracks]==[t['path'] for t in s['musicAndNarration']]
          and [t['startSeconds'] for t in tracks[:3]]==[0.4,5.5,12.3]
          and tracks[3]['tempo']==0.94)
    audio=pcm(final)
    matches=[]
    for track in tracks[:3]:
        voice=pcm(DATA/track['path'])
        score,shift=correlation(audio,voice,track['startSeconds'])
        matches.append(dict(path=track['path'],start=track['startSeconds'],
                            normalizedCorrelation=round(score,4),offsetSeconds=shift))
    report['narrationAlignment']=matches
    check('all three actual narration waveforms align with their intended positions',
          all(x['normalizedCorrelation']>0.60 for x in matches),matches)
    music=music_pcm(DATA/tracks[3]['path'],tracks[3]['tempo'])
    music_sample=music[9*16000:10*16000]
    music_score,music_shift=correlation(audio,music_sample,9)
    report['musicAlignment']=dict(normalizedCorrelation=round(music_score,4),offsetSeconds=music_shift,
                                  comparisonIntervalSeconds=[9,10],tempo=tracks[3]['tempo'])
    check('background music is present during the inserted shot',
          music_score>0.60,report['musicAlignment'])
    media=p.s.get(p.base+'/api/media',params={'assetPath':e['assetPath']},
                  headers={'Range':'bytes=0-1023'},timeout=30)
    with final.open('rb') as f: prefix=f.read(1024)
    check('seekable media range returns correct bytes',media.status_code==206 and media.content==prefix,media.status_code)
    sheet=Image.new('RGB',(1728,1064),'#101827');d=ImageDraw.Draw(sheet)
    for i,n in enumerate(final_ix):
        with Image.open(ff[n]) as im:sheet.paste(im.resize((432,240)),((i%4)*432,(i//4)*266))
        d.text(((i%4)*432+8,(i//4)*266+244),f'frame {n} | {n/24:.3f}s',fill='white')
    sheet.save(EVIDENCE/'contact-sheet.jpg',quality=95)
    p.preserve()
    report.update(status='Passed',sha256=e['sha256'],baseSha256=s['baseSha256'],
                  fullbodySha256=s['videos'][-1]['sha256'])
    write(REPORT,report)
    print(str(len(report['checks']))+' final technical checks Passed; content and listening remain pending review.')

if __name__=='__main__':main()

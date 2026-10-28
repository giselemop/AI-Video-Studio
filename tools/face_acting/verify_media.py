"""Real decode, voice-packet equality and same-time comparison crops."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
from PIL import Image,ImageDraw
from run import DATA,FOLDER,API,Run,read,write,sha,media,preserve,FFMPEG

def probe(path):return json.loads(subprocess.check_output([r'C:\install\FFmpeg\bin\ffprobe.exe','-v','error','-show_streams','-show_format','-of','json',str(path)],text=True))
def audio(path,copy=True):
    return subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-map','0:a:0']+
        (['-c:a','copy','-f','data','pipe:1'] if copy else ['-f','s16le','-acodec','pcm_s16le','pipe:1']))
def frame_at(path,index):
    cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,frame=cap.read();cap.release()
    if not ok:raise RuntimeError('Same-time frame decode failed')
    return frame

def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['pilot','pilot-qhd','final']);args=parser.parse_args()
    run=Run(API,FOLDER/'run.json');preserve(run)
    is_pilot=args.kind!='final'
    key='pilotPath' if args.kind=='pilot' else 'pilotQhdPath' if args.kind=='pilot-qhd' else 'finalPath'
    target=media(run.state[key]);expected_count=48 if is_pilot else 240
    seconds=expected_count/24;spec=probe(target);v=next(s for s in spec['streams'] if s['codec_type']=='video')
    dims=[1280,720] if args.kind=='pilot' else [2560,1440]
    if [v['width'],v['height'],v['r_frame_rate'],int(v['nb_frames'])]!=dims+['24/1',expected_count]:raise RuntimeError('Actual output specification differs')
    if abs(float(spec['format']['duration'])-seconds)>1/24 or any(abs(float(s['duration'])-seconds)>1/24 for s in spec['streams']):
        raise RuntimeError('Container/video/audio duration mismatch')
    cap=cv2.VideoCapture(str(target));hashes=[]
    while True:
        ok,frame=cap.read()
        if not ok:break
        hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
    cap.release()
    if len(hashes)!=expected_count or len(set(hashes))!=expected_count:raise RuntimeError('Duplicate/missing actual video frames')
    old_skin=read(DATA/'SkinPilot20261024/run.json')
    original=media(old_skin['outputs']['original']) if is_pilot else media(run.state['originalPath'])
    if audio(original)!=audio(target) or audio(original,False)!=audio(target,False):raise RuntimeError('Original audio packets or PCM changed')
    folder=FOLDER/(args.kind+'-comparison');folder.mkdir(exist_ok=True)
    sample=[0,6,12,18,24,30,36,42,47] if is_pilot else [5,19,36,52,53,77,95,96,127,168,223,239]
    old_qhd=media(old_skin['outputs']['qhd']) if is_pilot else media(run.state['previousQhdPath'])
    tiles=[]
    for i in sample:
        tile=Image.new('RGB',(1440,300),'#101923');draw=ImageDraw.Draw(tile)
        for j,(name,path) in enumerate([('ORIGINAL',original),('PREVIOUS QHD',old_qhd),('NEW ACTING',target)]):
            frame=frame_at(path,i);image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            image.resize((480,270),Image.Resampling.LANCZOS).save(folder/f'full-{i:03}-{j}.png')
            tile.paste(image.resize((480,270),Image.Resampling.LANCZOS),(j*480,30));draw.text((j*480+8,8),f'{name} | frame {i} | {i/24:.3f}s',fill='white')
        tile.save(folder/f'compare-{i:03}.png');tiles.append(tile.resize((1152,240)))
    sheet=Image.new('RGB',(1152,240*len(tiles)),'#101923')
    for i,tile in enumerate(tiles):sheet.paste(tile,(0,i*240))
    sheet.save(folder/'contact.jpg',quality=95)
    result=dict(status='Passed',contentReview='NeedReview',scope='Actual technical decode/specification and original audio integrity, not artistic or phoneme accuracy',
        path=run.state[key],sha256=sha(target),frames=len(hashes),uniqueFrames=len(set(hashes)),fps=24,width=dims[0],height=dims[1],seconds=seconds,
        audioPacketsEqual=True,audioPcmEqual=True,sourceHashesPreserved=True,sampledFrames=sample,
        audioPacketSha256=hashlib.sha256(audio(target)).hexdigest())
    write(FOLDER/(args.kind+'-verification.json'),result)
    print({k:result[k] for k in ['status','frames','seconds','audioPacketsEqual','audioPcmEqual']},flush=True)

if __name__=='__main__':main()

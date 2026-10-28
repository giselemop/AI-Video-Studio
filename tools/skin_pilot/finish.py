"""Inspect, submit CPU finishing, verify and present the original/QHD/skin pilot."""
import argparse
import json
from pathlib import Path
import subprocess
import wave

import cv2
import numpy as np
from PIL import Image,ImageDraw

from pilot import ROOT,DATA,FOLDER,API,Run,read,write,sha,media,preserve,once,result


def key_sheet(run,attempt):
    rows=[]
    for index in run.state['keyframes']:
        input=FOLDER/'keys'/f'{index:03}'/'input.png'
        output=media(run.state[f'key{index:03}Attempt{attempt}Path'])
        tile=Image.new('RGB',(1536,804),'#101923')
        draw=ImageDraw.Draw(tile)
        draw.text((10,10),f'frame {index:02} | QHD input',fill='white')
        draw.text((778,10),f'frame {index:02} | raw local skin patch A{attempt}',fill='white')
        tile.paste(Image.open(input),(0,36));tile.paste(Image.open(output),(768,36))
        tile.save(FOLDER/f'key-{index:03}-attempt-{attempt}-compare.png')
        rows.append(tile.resize((768,402)))
    sheet=Image.new('RGB',(768,402*len(rows)),'#101923')
    for i,tile in enumerate(rows):sheet.paste(tile,(0,402*i))
    sheet.save(FOLDER/f'keys-attempt-{attempt}.jpg',quality=95)
    print(FOLDER/f'keys-attempt-{attempt}.jpg',flush=True)


def manifest(run,attempt):
    preserve(run)
    review=read(FOLDER/f'key-review-attempt-{attempt}.json')
    if review['decision']!='SelectedForComposite':raise RuntimeError('Actual key inspection required')
    files={}
    def bind(path):
        p=media(path)
        relative=str(p.relative_to(DATA))
        files[relative]=dict(path=relative,sha256=sha(p))
        return relative
    frames=[]
    for index in range(48):
        frames.append(dict(image=bind(str((FOLDER/'source-frames'/f'{index:03}.png').relative_to(DATA))),
                           mask=bind(str((FOLDER/'masks'/f'{index:03}.png').relative_to(DATA))),
                           protected=bind(str((FOLDER/'masks'/f'{index:03}-protected.png').relative_to(DATA)))))
    keys={}
    for index in run.state['keyframes']:
        path=run.state[f'key{index:03}Attempt{attempt}Path']
        if review['keys'][str(index)]!=sha(media(path)):raise RuntimeError('Reviewed key changed')
        keys[str(index)]=dict(input=bind(str((FOLDER/'keys'/f'{index:03}'/'input.png').relative_to(DATA))),generated=bind(path))
    m=dict(schemaVersion=1,purpose='LocalSkinPilot2s',startFrame=5,frameCount=48,fps=24,width=2560,height=1440,
           keyframes=run.state['keyframes'],roi=run.state['roi'],attempt=attempt,blend=.7,
           originalPath=bind(run.state['originalPath']),qhdPath=bind(run.state['qhdPath']),
           landmarksPath=bind(str((FOLDER/'landmarks.json').relative_to(DATA))),frames=frames,keys=keys)
    m['files']=list(files.values())
    path=FOLDER/f'attempt-{attempt}-manifest.json'
    if path.exists() and read(path)!=m:raise RuntimeError('Frozen composite manifest differs')
    write(path,m)
    run.save(**{f'compositeAttempt{attempt}Manifest':str(path.relative_to(DATA)),
                f'compositeAttempt{attempt}ManifestSha256':sha(path)})
    return path


def compose(run,attempt,revision):
    run.access()
    path=manifest(run,attempt)
    body=dict(projectId=run.state['projectId'],taskType='SkinComposite',resourceClass='CPU',maxRetries=0,
              stage=f'Skin-Pilot-Residual-Flow-Composite-Attempt-{attempt}',
              parameters=dict(manifest=str(path.relative_to(DATA)),manifestSha256=sha(path),
                              engineVersion=sha(ROOT/'tools/skin_pilot/compose.py').upper()))
    field=f'compositeAttempt{attempt}TaskId' if revision==1 else f'compositeAttempt{attempt}Revision{revision}TaskId'
    detail=once(run,field,body)
    paths={}
    for item in detail['results']:
        if not item.get('available'):continue
        p=item['assetPath']
        for name,fragment in [('optimized','skin_optimized_2k_2s'),('original','skin_original_720p_2s'),
                              ('qhd','skin_current_2k_2s'),('receipt','skin_composite_receipt')]:
            if fragment in p:paths[name]=p
    if set(paths)!=set(['optimized','original','qhd','receipt']):raise RuntimeError('Missing published variant')
    run.save('AwaitingFinalInspection',selectedAttempt=attempt,selectedCompositeTaskId=run.state[field],outputs=paths)
    print(paths,flush=True)


def ffprobe(path):
    return json.loads(subprocess.check_output([r'C:\install\FFmpeg\bin\ffprobe.exe','-v','error','-show_streams',
        '-show_format','-of','json',str(path)],text=True))


def pcm(path):
    return subprocess.check_output([r'C:\install\FFmpeg\bin\ffmpeg.exe','-v','error','-i',str(path),
        '-map','0:a:0','-f','s16le','-acodec','pcm_s16le','pipe:1'])


def verify(run):
    preserve(run)
    report=dict(status='Passed',contentReview='NeedReview',variants={},samples=[],checks={})
    frames={}
    audio=[]
    for name in ['original','qhd','optimized']:
        path=media(run.state['outputs'][name]);probe=ffprobe(path)
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        width,height=(1280,720) if name=='original' else (2560,1440)
        if [video['width'],video['height'],video['r_frame_rate'],int(video['nb_frames'])]!=[width,height,'24/1',48]:
            raise RuntimeError('Delivery geometry mismatch')
        if abs(float(probe['format']['duration'])-2)>1/24:raise RuntimeError('Duration mismatch')
        cap=cv2.VideoCapture(str(path));decoded=[]
        for i in range(48):
            ok,f=cap.read()
            if not ok:raise RuntimeError('Actual full decode failed')
            decoded.append(f)
        ok,_=cap.read();cap.release()
        if ok:raise RuntimeError('Unexpected extra video frame')
        frames[name]=decoded
        audio.append(pcm(path))
        report['variants'][name]=dict(path=run.state['outputs'][name],sha256=sha(path),
            width=width,height=height,fps=24,frames=48,seconds=float(probe['format']['duration']),
            decodedUniqueFrames=len(set(hashlib_frame(f) for f in decoded)))
    if not audio[0]==audio[1]==audio[2]:raise RuntimeError('Three-way delivered audio differs')
    original_audio=pcm(media(run.state['originalPath']))
    # The decoded excerpt before AAC must be sample-exact to the source.
    receipt=read(media(run.state['outputs']['receipt']))
    start=receipt['audioStartSample'];count=receipt['audioSampleCount'];rate=receipt['audioSampleRate']
    expected=original_audio[start*2:(start+count)*2]
    task=run.api(f"/api/tasks/{run.state['selectedCompositeTaskId']}")['task']
    # Find the queue's actual original-voice WAV by the recorded receipt output location.
    staged_output=DATA/receipt['outputs'][0]['path']
    with wave.open(str(staged_output.parent/'skin-work/original-voice.wav'),'rb') as stream:
        excerpt=stream.readframes(stream.getnframes())
        if stream.getframerate()!=rate or stream.getnframes()!=count or count!=2*rate or excerpt!=expected:
            raise RuntimeError('Voice excerpt is not sample-exact')
    if any(r['protectedPixelMaxChange'] or r['outsideSkinMaxChange'] for r in receipt['frames']):
        raise RuntimeError('Protected pixels changed before encoding')
    samples=[0,6,12,18,24,30,36,42,47]
    x,y,size,_=run.state['roi']
    tiles=[]
    for i in samples:
        tile=Image.new('RGB',(1536,550),'#101923');draw=ImageDraw.Draw(tile)
        for j,name in enumerate(['original','qhd','optimized']):
            frame=frames[name][i]
            if name=='original':frame=cv2.resize(frame,(2560,1440),interpolation=cv2.INTER_LANCZOS4)
            crop=frame[y:y+size,x:x+size]
            crop=cv2.resize(crop,(512,512),interpolation=cv2.INTER_AREA)
            tile.paste(Image.fromarray(cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)),(j*512,38))
            draw.text((j*512+8,10),f'{name.upper()} | {i/24:.3f}s | frame {i}',fill='white')
        tile.save(FOLDER/f'compare-face-{i:03}.png')
        tiles.append(tile.resize((1152,412)))
    sheet=Image.new('RGB',(1152,412*len(tiles)),'#101923')
    for i,tile in enumerate(tiles):sheet.paste(tile,(0,i*412))
    sheet.save(FOLDER/'faces-three-way.jpg',quality=95)
    report['checks']=dict(fullDecode=True,frames48=True,audioSameAcrossThree=True,
        excerptOriginalRateTwoSecondsExactBeforeAAC=True,protectedEyesMouthAndUnmaskedPixelsExactBeforeEncoding=True,
        sourceHashesPreserved=True)
    report['samples']=samples
    report['skinChange']=dict(meanAbsoluteChange=float(np.mean([r['skinMeanAbsoluteChange'] for r in receipt['frames']])),
        maxProtectedChange=0,maxOutsideSkinChange=0)
    write(FOLDER/'verification.json',report)
    run.save(verificationPath=str((FOLDER/'verification.json').relative_to(DATA)))
    print(dict(status='Passed',checks=report['checks'],skinChange=report['skinChange']),flush=True)


def hashlib_frame(frame):
    import hashlib
    return hashlib.sha256(frame.tobytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',required=True,choices=['key-sheet','compose','verify'])
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--revision',type=int,default=1,choices=[1,2,3])
    args=parser.parse_args()
    run=Run(API,FOLDER/'run.json')
    if run.state.get('stage')=='ReadyForUserPreview' and args.stage!='verify':
        preserve(run);print('Complete; no new task',flush=True);return
    if args.stage=='key-sheet':key_sheet(run,args.attempt)
    elif args.stage=='compose':compose(run,args.attempt,args.revision)
    else:verify(run)


if __name__=='__main__':main()

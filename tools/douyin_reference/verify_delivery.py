"""Check actual source graphs, full decoded video and every complete Qwen line."""
import json
import subprocess
import numpy as np
from PIL import Image,ImageDraw
from run import DATA,FOLDER,FFMPEG,sha,probe,REFERENCE_SHA


def pcm(path):
    return np.frombuffer(subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-vn',
        '-ar','24000','-ac','1','-f','f32le','-']),dtype='<f4').copy()


def main():
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    if state['stage'] not in ['AwaitingPlaybackInspection','ReadyForUserPreview']:
        raise RuntimeError('A real completed assembly is required')
    if sha(FOLDER/'reference-7699361421842789233.mp4')!=REFERENCE_SHA:
        raise RuntimeError('Original reference changed')
    sources=[]
    for number in range(1,7):
        path=DATA/state[f'shot{number}VideoPath']
        if sha(path)!=state[f'shot{number}VideoSha256']:raise RuntimeError('Source changed')
        metadata=probe(path);video=next(s for s in metadata['streams'] if s['codec_type']=='video')
        if (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))!=(1376,768,'24/1',124):
            raise RuntimeError('Actual source geometry differs')
        graph=json.loads(metadata['format']['tags']['prompt'])
        if (graph['6']['inputs']['width'],graph['6']['inputs']['height'],graph['6']['inputs']['length'],graph['10']['inputs']['steps'])!=(1376,768,124,20):
            raise RuntimeError('Actual generation geometry differs')
        if graph['5']['is_changed']!=[state[f'shot{number}InputFrameSha256']]:
            raise RuntimeError('Actual source reference differs')
        if number>1 and state[f'shot{number}InputFrameSha256']!=sha(FOLDER/f'shot-{number-1:02}/frame-123.png'):
            raise RuntimeError('Continuation did not use the actual preceding tail')
        sources.append(dict(shot=number,taskId=state[f'shot{number}TaskId'],sha256=sha(path),
            durationMs=state[f'shot{number}TaskMetrics']['durationMs']))
    final=DATA/state['finalVideoPath']
    if sha(final)!=state['finalVideoSha256']:raise RuntimeError('Final changed')
    metadata=probe(final);video=next(s for s in metadata['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))!=(1280,720,'24/1',744):
        raise RuntimeError('Actual final geometry differs')
    if abs(float(video['duration'])-31)>.02 or not any(s['codec_type']=='audio' for s in metadata['streams']):
        raise RuntimeError('Final duration or audio missing')
    hashes=subprocess.check_output([FFMPEG,'-v','error','-i',str(final),'-map','0:v:0','-f','framemd5','-'],encoding='utf-8')
    (FOLDER/'final-framemd5.txt').write_text(hashes,encoding='utf-8')
    frames=[line.rsplit(',',1)[-1].strip() for line in hashes.splitlines() if line and not line.startswith('#')]
    if len(frames)!=744:raise RuntimeError('Complete decode frame count differs')
    actual=pcm(final)
    if len(actual)<744000 or not np.isfinite(actual).all():raise RuntimeError('Final audio too short or invalid')
    actual=actual[:744000];expected=np.zeros(744000,dtype=np.float32);lines=[]
    for index,track in enumerate(state['dialogueTracks'],1):
        if track['tempo']!=1:raise RuntimeError('Verify the fitted signal if a new tempo is introduced')
        path=DATA/track['path']
        if sha(path)!=state[f'dialogue{index}Sha256']:raise RuntimeError('Qwen line changed')
        signal=pcm(path);start=round(track['startSeconds']*24000);end=start+len(signal)
        if end>len(expected):raise RuntimeError('A complete line is truncated')
        expected[start:end]+=signal*track['volume']
        correlation=float(np.corrcoef(actual[start:end],signal)[0,1])
        if not np.isfinite(correlation) or correlation<.97:raise RuntimeError(f'Qwen line {index} does not match')
        lines.append(dict(line=index,taskId=state[f'dialogue{index}TaskId'],completeSamples=len(signal),
            startSeconds=track['startSeconds'],endSeconds=end/24000,correlation=correlation,samplesTruncated=0))
    correlation=float(np.corrcoef(actual,expected)[0,1])
    if not np.isfinite(correlation) or correlation<.97:raise RuntimeError('Complete final mix differs')
    contact=Image.new('RGB',(1440,810),'#111')
    for i,seconds in enumerate([0,3,7,11,14,18,22,26,30]):
        path=FOLDER/f'final-{seconds:02}.png'
        if not path.exists():subprocess.run([FFMPEG,'-v','error','-ss',str(seconds),'-i',str(final),'-frames:v','1','-n',str(path)],check=True)
        image=Image.open(path).convert('RGB');image.thumbnail((480,270));x,y=(i%3)*480,(i//3)*270
        contact.paste(image,(x,y));ImageDraw.Draw(contact).text((x+8,y+8),f'{seconds}s',fill='white')
    contact.save(FOLDER/'final-contact.jpg',quality=92)
    report=dict(status='Passed',decodedFrames=len(frames),uniqueDecodedFrameHashes=len(set(frames)),sources=sources,
        finalVideoSha256=sha(final),originalReferencePreserved=True,sourceInference='H3 native1376x768/24FPS/20steps',
        audio=dict(status='Passed',samples=744000,sampleRate=24000,completeMixCorrelation=correlation,lines=lines,
            originalH3AudioVolume=0,allQwenLinesComplete=True,allQwenLinesOriginalSpeed=True),
        contentStatus='NeedReview',publicationStatus='Blocked',referenceParity='Not automatically certified')
    (FOLDER/'delivery-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

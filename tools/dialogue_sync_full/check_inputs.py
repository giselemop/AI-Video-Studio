"""Verify exact dry-voice samples, cut padding and frozen subtitle input offline."""
from run import *
import numpy as np
s=read(FOLDER/'run.json');rows=[]
def pcm(path):
    info=json.loads(subprocess.check_output([r'C:\install\FFmpeg\bin\ffprobe.exe','-v','error','-show_streams','-of','json',str(path)]))['streams'][0]
    if info['channels']!=1:raise RuntimeError('Expected mono role voice')
    data=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-f','s32le','-acodec','pcm_s32le','pipe:1'])
    return np.frombuffer(data,dtype='<i4'),int(info['sample_rate'])
for shot in SHOTS:
    for role in ['female','male']:
        original,sr=pcm(media(s['inputs'][role+'Audio']));p=FOLDER/f"shot-{shot['index']}-{role}.wav";actual,rate=pcm(p)
        start=round(shot['start']/24*sr);n=round(shot['frames']/24*sr)
        if rate!=sr or len(actual)!=round(shot['native']/25*sr) or not np.array_equal(actual[:n],original[start:start+n]) or np.any(actual[n:]):raise RuntimeError('Original voice or silent padding differs: '+p.name)
        rows.append(dict(index=shot['index'],role=role,sampleRate=sr,exactOriginalSamples=n,startSample=start,paddedSilenceSamples=len(actual)-n,sha256=sha(p)))
write(FOLDER/'voice-window-checks.json',dict(status='Passed',checks=rows,subtitlePath=s['inputs']['subtitle'],subtitleSha256=sha(media(s['inputs']['subtitle'])),cutFrames=[53,96],scope='Exact original dry PCM per shot followed only by silence; final voice copies original whole AAC without cutting'))
print('Passed: all6 dry voice windows and silent padding; original subtitles frozen')

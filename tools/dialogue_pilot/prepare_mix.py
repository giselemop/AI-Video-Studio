"""Deterministic local room tone, subtle early reflections and timed subtitles."""
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import butter,sosfilt

FOLDER=Path(r'C:\install\AI\Data\DialoguePilot20261023')
def stamp(seconds):
    ms=round(seconds*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

if __name__=='__main__':
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    audio,sr=sf.read(FOLDER/'dialogue-9.64s.wav',dtype='float32')
    count=round(9.5*sr)
    if np.max(np.abs(audio[count:]))>1e-4:raise RuntimeError('Delivery trim would remove audible speech')
    dry=audio[:count].copy()
    levels=[]
    # Match listening levels while retaining the intentionally softer third line.
    for line,target_db in zip(state['timeline'],[-20,-22,-23,-21]):
        start=round(line['startSeconds']*sr);end=round(line['endSeconds']*sr)
        segment=dry[start:end]
        active=segment[np.abs(segment)>.01]
        rms=float(np.sqrt(np.mean(active**2)))
        source_db=float(20*np.log10(max(rms,1e-9)))
        gain=10**((target_db-source_db)/20)
        dry[start:end]*=gain
        levels.append(dict(index=line['index'],role=line['role'],sourceActiveRmsDbFS=source_db,targetActiveRmsDbFS=target_db,gain=gain))
    output=dry.copy()
    for seconds,gain in [(.013,.018),(.027,.012),(.043,.007)]:
        offset=round(seconds*sr);output[offset:]+=gain*dry[:-offset]
    room=sosfilt(butter(2,[90,2400],btype='bandpass',fs=sr,output='sos'),np.random.default_rng(20261023).normal(size=count)).astype('float32')
    room*=.0005/max(np.sqrt(np.mean(room**2)),1e-9)
    output+=room
    if np.max(np.abs(output))>=.98:raise RuntimeError('Audio would clip; review gain')
    sf.write(FOLDER/'dialogue-room-9.5s.wav',output,sr,subtype='PCM_24')
    sf.write(FOLDER/'room-tone-9.5s.wav',room,sr,subtype='PCM_24')
    captions=[]
    for line in state['timeline']:
        label='女' if line['role']=='female' else '男'
        captions.append(f'{line["index"]}\n{stamp(line["startSeconds"])} --> {stamp(line["endSeconds"])}\n{label}：{line["text"]}\n')
    (FOLDER/'dialogue.srt').write_text('\n'.join(captions),encoding='utf-8')
    def sha(p):
        with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    report=dict(status='Passed',kind='Deterministic audio preparation, no model inference',durationSeconds=9.5,sampleRate=sr,peak=float(np.max(np.abs(output))),trimmedTailSeconds=.14,removedTailMaxAbs=float(np.max(np.abs(audio[count:]))),voiceTempo=1,levels=levels,roomRmsDbFS=float(20*np.log10(np.sqrt(np.mean(room**2)))),earlyReflections=[dict(delaySeconds=s,gain=g) for s,g in [(.013,.018),(.027,.012),(.043,.007)]],mixSha256=sha(FOLDER/'dialogue-room-9.5s.wav'),subtitleSha256=sha(FOLDER/'dialogue.srt'))
    (FOLDER/'mix-preparation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

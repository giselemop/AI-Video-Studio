"""Decode, original dialogue correlation and preservation checks on the real export."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf

DATA=Path(r'C:\install\AI\Data')
FOLDER=DATA/'DialoguePilot20261023'
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

if __name__=='__main__':
    run=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    path=DATA/run['finalPath']
    if sha(path)!=run['finalSha256']:raise RuntimeError('Final changed')
    probe=json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'))
    v=next(s for s in probe['streams'] if s['codec_type']=='video')
    a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))==(1280,720,'24/1',228)
    assert abs(float(probe['format']['duration'])-9.5)<.1
    hashes=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-'],encoding='utf-8')
    (FOLDER/'final-framemd5.txt').write_text(hashes,encoding='utf-8')
    frames=[x for x in hashes.splitlines() if x and not x.startswith('#')]
    assert len(frames)==228
    raw=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-map','0:a:0','-ac','1','-ar','24000','-f','f32le','-'])
    decoded=np.frombuffer(raw,dtype='<f4')
    expected,sr=sf.read(FOLDER/'dialogue-room-9.5s.wav',dtype='float32')
    n=min(len(decoded),len(expected));whole=float(np.corrcoef(decoded[:n],expected[:n])[0,1])
    assert whole>.995
    lines=[]
    for item in run['timeline']:
        start=round(item['startSeconds']*sr);end=round(item['endSeconds']*sr)
        correlation=float(np.corrcoef(decoded[start:end],expected[start:end])[0,1])
        assert correlation>.985
        lines.append(dict(index=item['index'],role=item['role'],text=item['text'],correlation=correlation,missingSpeechSamples=max(0,end-len(decoded))))
    preserved=json.loads((FOLDER/'preserved-before.json').read_text(encoding='utf-8'))
    assert all(sha(x['path'])==x['sha256'] for x in preserved)
    report=dict(status='Passed',scope='Technical export, audio integrity and previous-media preservation only',finalPath=str(path),finalSha256=sha(path),width=1280,height=720,fps=24,frames=228,durationSeconds=9.5,decodedFrames=len(frames),uniqueDecodedHashes=len({x.split(',')[-1].strip() for x in frames}),audio=dict(codec=a['codec_name'],completeMixCorrelation=whole,lines=lines),preservedFiles=len(preserved),contentStatus='NeedReview',publicationStatus='Blocked')
    (FOLDER/'delivery-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (FOLDER/'final-probe.json').write_text(json.dumps(probe,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

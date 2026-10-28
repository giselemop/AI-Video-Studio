"""Check rendered subtitle glyph cores at each original cue's first/middle/last frame."""
from verify_helpers import *
import math
p=argparse.ArgumentParser();p.add_argument('--baseline-only',action='store_true');args=p.parse_args()
s=read(FOLDER/'run.json');cue=[]
def seconds(value):
    h,m,t=value.split(':');sec,ms=t.split(',');return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
for block in media(s['inputs']['subtitle']).read_text(encoding='utf-8-sig').strip().split('\n\n'):
    lines=block.splitlines();a,b=map(seconds,lines[1].split(' --> '));first=math.ceil(a*24);end=math.ceil(b*24)
    cue.append(dict(text='\n'.join(lines[2:]),start=a,end=b,frames=list(range(first,end)),sampleFrames=sorted(set([first,(first+end-1)//2,end-1]))))
if len(cue)!=4:raise RuntimeError('Four original subtitle lines required')
indices=sorted({i for c in cue for i in c['sampleFrames']});escaped=str(media(s['inputs']['subtitle'])).replace('\\','/').replace(':',r'\:').replace("'",r"\'")
select='+'.join(rf'eq(n\,{i})' for i in indices)
raw=subprocess.check_output([FFMPEG,'-nostdin','-v','error','-f','lavfi','-i','color=c=black:s=2560x1440:r=24:d=10','-vf',f"subtitles='{escaped}',select='{select}'",'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','pipe:1'])
masks=np.frombuffer(raw,dtype=np.uint8).reshape((-1,1440,2560))
if len(masks)!=len(indices):raise RuntimeError('Expected subtitle renderer frame count differs')
rows=[]
for index,mask in zip(indices,masks):
    core=mask>=max(int(mask.max())-3,220)
    if core.sum()<40:raise RuntimeError('Expected subtitle glyph core absent')
    observed=[]
    versions=[('previous',s['inputs']['original'])] if args.baseline_only else [('previous',s['inputs']['original']),('new',s['finalPath'])]
    for name,path in versions:
        pixels=frame(path,index);gray=cv2.cvtColor(pixels,cv2.COLOR_BGR2GRAY);ratio=float((gray[core]>190).mean())
        if ratio<.90:raise RuntimeError('Rendered subtitle core differs: '+name+' frame'+str(index))
        observed.append(dict(version=name,brightGlyphCoreFraction=ratio))
    rows.append(dict(frame=index,expectedCorePixels=int(core.sum()),observed=observed))
write(FOLDER/('caption-baseline-checks.json' if args.baseline_only else 'caption-render-checks.json'),dict(status='Passed',subtitleSha256=sha(media(s['inputs']['subtitle'])),cues=cue,sampleChecks=rows,scope='Same frozen original SRT and renderer; visible glyph-core presence at each cue first/middle/last frame. This is not OCR or an exhaustive pixel-invariance claim; actual four lines also visually inspected.'))
print('Passed: original four subtitle cues visibly present at first/middle/last sampled frames')

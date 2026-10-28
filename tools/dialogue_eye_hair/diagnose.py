"""Read-only frame evidence around the user-reported eye/hair failure."""
from pathlib import Path
import sys,importlib.util,json,cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent/'Data';FOLDER=DATA/'DialogueEyeHair20261025';FOLDER.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('eye_hair_base',ROOT/'tools/dialogue_stable/run.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
s=b.read(DATA/'DialogueStable20261025/run.json')
def frame(p,i):
    c=cv2.VideoCapture(str(b.media(p)));c.set(cv2.CAP_PROP_POS_FRAMES,i);ok,x=c.read();c.release()
    if not ok:raise RuntimeError('Missing actual frame')
    return x
def crop(pixels):
    h,w=pixels.shape[:2];return pixels[round(h*.055):round(h*.48),round(w*.17):round(w*.44)]
def sheet(items,name,cols=4):
    out=Image.new('RGB',(320*cols,350*((len(items)+cols-1)//cols)),'#10151c');d=ImageDraw.Draw(out)
    for k,(label,x) in enumerate(items):
        im=Image.fromarray(cv2.cvtColor(crop(x),cv2.COLOR_BGR2RGB));im.thumbnail((320,320));xx=k%cols*320;yy=k//cols*350;out.paste(im,(xx+(320-im.width)//2,yy+30));d.text((xx+6,yy+7),label,fill='white')
    out.save(FOLDER/name)
def main():
    reference=cv2.imread(str(b.media(s['inputs']['wideReference'])))
    indices=[88,92,96,97,98,99,100,101,102,104,110,125]
    sheet([(f'actor native {i} | {4+i/25:.3f}s',frame(s['v2_female_widePath'],i)) for i in indices],'actor-around-blink.png')
    sheet([('source reference',reference),('actor f100',frame(s['v2_female_widePath'],100)),('merged f100',frame(s['wideMergePath'],100)),('final f192 |8.000s',frame(s['finalPath'],192))],'stage-comparison.png')
    sheet([(f'final {i} |{i/24:.3f}s',frame(s['finalPath'],i)) for i in range(185,201)],'final-dense-window.png')
    receipt=b.read(b.media(s['v2_female_wideReceiptPath']))
    b.write(FOLDER/'diagnosis.json',dict(sourceFinal=s['finalPath'],sourceFinalSha256=b.sha(b.media(s['finalPath'])),sourceReference=s['inputs']['wideReference'],scheduledBlinkNativeCentre=100,scheduledBlinkGlobalSeconds=8,eyeResidualRows=receipt['eyeCorrectionFrames'][96:105],readOnly=True,newTasks=0))
    r=b.Run('http://127.0.0.1:18081',FOLDER/'access.json');r.access();q=r.session.get('http://127.0.0.1:8188/queue').json()
    b.write(FOLDER/'initial-runtime.json',dict(health=r.api('/api/health'),active=[{k:t.get(k) for k in ['id','status','taskType']} for t in r.api('/api/tasks?limit=500') if t['status'] in ['Running','Pending','Queued']],comfyRunning=len(q['queue_running']),comfyPending=len(q['queue_pending']),queue=r.api('/api/minimax/local/status')['queue']))
    print('Read-only eye/hair evidence saved; no tasks submitted')
if __name__=='__main__':main()

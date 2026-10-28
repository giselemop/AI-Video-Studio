"""Actual decoded contacts for short drivers/canvases/finals; no content scores."""
from run import *
import cv2
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('--stage',choices=['driver','canvas','final'],required=True);p.add_argument('--clip',choices=['close','wide','both'],default='both');p.add_argument('--candidate',choices=['selected','repair','hybrid'],default='selected');a=p.parse_args();s=read(FOLDER/'run.json')
if a.candidate!='selected' and a.clip!='wide':raise ValueError('Directed repair belongs to wide clip only')
if a.candidate=='hybrid' and a.stage!='canvas':raise ValueError('Hybrid is inspected as a composed canvas')
for clip in [x for x in CLIPS if a.clip=='both' or a.clip==x['name']]:
    name=clip['name'];suffix={'driver':'Driver','canvas':'Canvas','final':'Final'}[a.stage]
    indices=[0,5,15,27,40,clip['nativeFrames']-1] if a.stage=='driver' else [0,5,12,26,clip['frames']-2,clip['frames']-1]
    contact=Image.new('RGB',(1024,320*len(indices)),'#10151c');draw=ImageDraw.Draw(contact)
    for row,index in enumerate(indices):
        fps=25 if a.stage=='driver' else 24;baseline_index=min(clip['frames']-1,round(index/fps*24))
        prefix='wideRepair' if a.candidate=='repair' else 'wideHybrid' if a.candidate=='hybrid' else name
        for side,(path,frame_index,label) in enumerate([(s[name+'BaselinePath'],baseline_index,'PREVIOUS'),(s[prefix+suffix+'Path'],index,'NEW '+a.stage.upper())]):
            cap=cv2.VideoCapture(str(media(path)));cap.set(cv2.CAP_PROP_POS_FRAMES,frame_index);ok,image=cap.read();cap.release()
            if not ok:raise RuntimeError('Actual contact frame missing')
            im=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).resize((512,288),Image.Resampling.LANCZOS);contact.paste(im,(512*side,row*320+32))
            timestamp=baseline_index/24 if side==0 else index/fps
            draw.text((512*side+8,row*320+10),label+f' | {timestamp:.3f}s | frame{frame_index}',fill='white')
    contact.save(FOLDER/(name+('-'+a.candidate if a.candidate!='selected' else '')+'-'+a.stage+'-contact.png'))
print('Actual decoded comparison contacts saved; visual review required')

"""CPU face/mouth observations and review sheets, never an automatic lip-sync pass."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
AI=ROOT.parent
FOLDER=AI/'Data/DialoguePilot20261023'
sys.path.insert(0,str(ROOT/'tools/identity_foundation'))
from identity_foundation import import_runtime

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--frames',type=int,default=125);args=parser.parse_args()
    run=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    path=AI/'Data'/run[f'video{args.frames}Path']
    cv2,np,ort,FaceAnalysis=import_runtime()
    app=FaceAnalysis(name='buffalo_l',root=str(AI/'Models/InsightFace'),providers=['CPUExecutionProvider'],allowed_modules=['detection','landmark_3d_68'])
    app.prepare(ctx_id=-1,det_size=(640,640),det_thresh=.45)
    out=FOLDER/f'inspection-{args.frames}';out.mkdir(exist_ok=True)
    cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS)
    count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));rows=[];thumbs=[];mouths=[]
    for index in range(count):
        ok,frame=cap.read()
        if not ok:raise RuntimeError('Frame decode failed')
        if index%3:continue
        faces=sorted(app.get(frame),key=lambda f:float(f.bbox[0]))
        row=dict(frame=index,time=index/fps,faceCount=len(faces),faces=[])
        img=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        for role,face in zip(['female','male'],faces):
            landmarks=getattr(face,'landmark_3d_68',None)
            gap=None
            if landmarks is not None:
                p=np.asarray(landmarks)[:,:2]
                gap=float(np.linalg.norm(p[62]-p[66])/max(np.linalg.norm(p[60]-p[64]),1e-6))
            box=[float(x) for x in face.bbox]
            active=any(t['role']==role and t['startSeconds']<=index/fps<=t['endSeconds'] for t in run['timeline'])
            row['faces'].append(dict(role=role,bbox=box,mouthGapRatio=gap,expectedSpeaker=active,detConfidence=float(face.det_score)))
            if index%12==0:
                x1,y1,x2,y2=box
                tile=img.crop((max(0,x1-8),max(0,y1-8),min(img.width,x2+8),min(img.height,y2+8))).resize((160,180))
                canvas=Image.new('RGB',(160,208),'#151b24');canvas.paste(tile,(0,0));ImageDraw.Draw(canvas).text((4,184),f'{index/fps:.2f}s {role} '+('SPEAK' if active else 'listen'),fill='white');mouths.append(canvas)
        if index%12==0:
            thumb=img.resize((416,240));canvas=Image.new('RGB',(416,266),'#151b24');canvas.paste(thumb,(0,0));ImageDraw.Draw(canvas).text((8,244),f'{index/fps:.2f}s',fill='white');thumbs.append(canvas)
        rows.append(row)
    cap.release()
    def sheet(tiles,cols,name):
        if not tiles:return
        w,h=tiles[0].size;canvas=Image.new('RGB',(w*cols,h*((len(tiles)+cols-1)//cols)),'#151b24')
        for i,tile in enumerate(tiles):canvas.paste(tile,((i%cols)*w,(i//cols)*h))
        canvas.save(out/name)
    sheet(thumbs,3,'contact.jpg');sheet(mouths,6,'speaking-faces.jpg')
    (out/'mouth-observations.json').write_text(json.dumps(dict(status='NeedReview',source=str(path),fps=fps,frames=count,observations=rows,note='Mouth gap and expected speaker are review aids, not a speech/lip accuracy score.'),indent=2),encoding='utf-8')
    print('Decoded frames',count,'face observations',len(rows),'review sheets',str(out),flush=True)

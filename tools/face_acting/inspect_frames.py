"""Same-field visual evidence; observations do not approve identity or artistic quality."""
import argparse
from pathlib import Path
import sys
from PIL import Image,ImageDraw
import cv2
import numpy as np
from run import ROOT,DATA,FOLDER,API,Run,read,write,sha,media


def references(run,role,attempt):
    paths=[media(run.state['geometry'][role]['input'])]+[media(run.state[f'{role}Ref{i}Attempt{attempt}Path']) for i in ([1,2,3] if role=='female' else [1])]
    width=512*len(paths);sheet=Image.new('RGB',(width,550),'#101923');draw=ImageDraw.Draw(sheet)
    labels=['Original reference','Closed relaxed','Slight closed smile','Restrained half-smile']
    for i,path in enumerate(paths):
        tile=Image.open(path).convert('RGB').resize((512,512),Image.Resampling.LANCZOS)
        sheet.paste(tile,(i*512,38));draw.text((i*512+8,10),labels[i],fill='white')
    out=FOLDER/f'{role}-reference-attempt-{attempt}-compare.png';sheet.save(out)
    print(out,flush=True)


def shot(run,index,attempt):
    path=media(run.state[f'shot{index}Attempt{attempt}Path']);cap=cv2.VideoCapture(str(path))
    frames=[]
    while True:
        ok,frame=cap.read()
        if not ok:break
        frames.append(frame)
    cap.release()
    expected=[57,46,151][index-1]
    if len(frames)!=expected:raise RuntimeError('Actual native frame count differs')
    indices=sorted(set([0,len(frames)-1]+list(range(0,len(frames),6 if index<3 else 12))))
    if index==3:
        indices=sorted(set(indices+[i for i in [47,48,55,56,57,58,95,96,103,104,105,106] if i<len(frames)]))
    out=FOLDER/f'inspection-shot-{index}-attempt-{attempt}';out.mkdir(exist_ok=True)
    tiles=[]
    for i in indices:
        image=Image.fromarray(cv2.cvtColor(frames[i],cv2.COLOR_BGR2RGB))
        image.save(out/f'frame-{i:03}.png')
        tile=Image.new('RGB',(416,264),'#101923');draw=ImageDraw.Draw(tile)
        tile.paste(image.resize((416,240)),(0,24));draw.text((7,5),f'frame {i} | {i/25:.3f}s',fill='white');tiles.append(tile)
    columns=3;rows=(len(tiles)+columns-1)//columns
    sheet=Image.new('RGB',(416*columns,264*rows),'#101923')
    for k,tile in enumerate(tiles):sheet.paste(tile,((k%columns)*416,(k//columns)*264))
    sheet.save(out/'contact.jpg',quality=95)
    write(out/'inspection.json',dict(status='NeedReview',sourcePath=str(path.relative_to(DATA)),sourceSha256=sha(path),
        decodedFrames=len(frames),sampledFrames=indices,scope='Actual frame decode and visual contact; no identity or phoneme score'))
    print(out/'contact.jpg',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['references','shot']);parser.add_argument('--role',default='female')
    parser.add_argument('--shot',type=int,default=1);parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    run=Run(API,FOLDER/'run.json')
    if args.kind=='references':references(run,args.role,args.attempt)
    else:shot(run,args.shot,args.attempt)


if __name__=='__main__':main()

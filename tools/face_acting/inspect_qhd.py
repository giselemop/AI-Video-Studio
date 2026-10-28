"""Compare the selected new take against its own QHD reconstruction, including streaming seams."""
import argparse
from PIL import Image,ImageDraw
import cv2
from run import ROOT,DATA,FOLDER,API,Run,read,write,sha,media

parser=argparse.ArgumentParser();parser.add_argument('--shot',required=True,type=int,choices=[1,2,3]);parser.add_argument('--attempt',type=int,default=1)
args=parser.parse_args();run=Run(API,FOLDER/'run.json');review=read(FOLDER/f'shot-{args.shot}-review.json')
before=media(run.state[f'canvas{args.shot}Attempt{review["attempt"]}Path']);after=media(run.state[f'restore{args.shot}Attempt{args.attempt}Path'])
caps=[cv2.VideoCapture(str(before)),cv2.VideoCapture(str(after))]
count=int(caps[0].get(cv2.CAP_PROP_FRAME_COUNT))
if [int(c.get(cv2.CAP_PROP_FRAME_COUNT)) for c in caps]!=[count,count]:raise RuntimeError('QHD changed actual frame count')
samples=sorted(set([0,count//4,count//2,count*3//4,count-1]+[v for v in [31,32,33,34,64,65,66,67,97,98,99,100,130,131,132,133] if v<count]))
folder=FOLDER/f'qhd-inspection-{args.shot}-attempt-{args.attempt}';folder.mkdir(exist_ok=True)
full=[];faces=[]
boxes={1:(1250,160,1000,1000),2:(0,80,1280,1280),3:(300,80,1400,1100)}
for i in range(count):
    frames=[]
    for cap in caps:
        ok,frame=cap.read()
        if not ok:raise RuntimeError('QHD/source full decode failed')
        frames.append(frame)
    if i not in samples:continue
    frames[0]=cv2.resize(frames[0],(2560,1440),interpolation=cv2.INTER_LANCZOS4)
    tile=Image.new('RGB',(1280,390),'#101923');detail=Image.new('RGB',(1024,550),'#101923')
    draw=ImageDraw.Draw(tile);d=ImageDraw.Draw(detail)
    for j,frame in enumerate(frames):
        image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        tile.paste(image.resize((640,360),Image.Resampling.LANCZOS),(j*640,30))
        label=f'{"SOURCE" if j==0 else "QHD stream33"} | frame {i} | {i/24:.3f}s'
        draw.text((j*640+8,8),label,fill='white')
        x,y,w,h=boxes[args.shot];crop=image.crop((x,y,x+w,y+h));crop.thumbnail((512,512),Image.Resampling.LANCZOS)
        detail.paste(crop,(j*512+(512-crop.width)//2,38+(512-crop.height)//2));d.text((j*512+8,8),label,fill='white')
    tile.save(folder/f'full-{i:03}.png');detail.save(folder/f'face-{i:03}.png')
    full.append(tile.resize((960,292)));faces.append(detail.resize((768,412)))
for name,tiles in [('full-contact',full),('face-contact',faces)]:
    width=tiles[0].width;height=tiles[0].height
    sheet=Image.new('RGB',(width,height*len(tiles)),'#101923')
    for i,tile in enumerate(tiles):sheet.paste(tile,(0,i*height))
    sheet.save(folder/(name+'.jpg'),quality=95)
for cap in caps:cap.release()
write(folder/'inspection.json',dict(status='NeedReview',sourceSha256=sha(before),qhdSha256=sha(after),
    decodedFrames=count,sampledFrames=samples,streamingBoundariesChecked=[v for v in [33,66,99,132] if v<count],
    scope='Actual same-frame/source-QHD comparison and seam inspection, not a face identity or phoneme accuracy score'))
print(folder/'face-contact.jpg',flush=True)

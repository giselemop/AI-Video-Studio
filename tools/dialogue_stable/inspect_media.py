"""Decode actual frames into review panels, never substitute generated imagery."""
from run import *
import cv2,numpy as np
from PIL import Image,ImageDraw
NAME_PREFIX=''
def frame(path,i):
    cap=cv2.VideoCapture(str(media(path)));cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read();cap.release()
    if not ok:raise RuntimeError('Frame missing')
    return cv2.cvtColor(pixels,cv2.COLOR_BGR2RGB)
def panel(path,indices,name,box=None,columns=4,size=(360,210)):
    w,h=size;out=Image.new('RGB',(w*columns,(h+27)*((len(indices)+columns-1)//columns)),(14,20,28));draw=ImageDraw.Draw(out)
    for slot,i in enumerate(indices):
        pixels=frame(path,i);im=Image.fromarray(pixels)
        if box:im=im.crop(tuple(round(v*k) for v,k in zip(box,[im.width,im.height,im.width,im.height])))
        im.thumbnail((w,h));x=slot%columns*w;y=slot//columns*(h+27);out.paste(im,(x+(w-im.width)//2,y+27));draw.text((x+7,y+6),f'frame {i}',fill='white')
    out.save(FOLDER/(NAME_PREFIX+name));return rel(FOLDER/(NAME_PREFIX+name))
if __name__=='__main__':
    s=read(FOLDER/'run.json');stage=sys.argv[1]
    if s.get('v2_female_closePath'):
        NAME_PREFIX='v2-'
        for key,value in list(s.items()):
            if key.startswith('v2_'):s[key[3:]]=value
    if stage=='female':
        panel(s['female_closePath'],[0,3,6,10,15,20,22,23,24,25,26,27,28,31,35,40,45,50,53,56],'female-blink-native.png',(.48,.16,.83,.55),4)
    elif stage=='actors':
        panel(s['male_closePath'],[0,5,10,12,13,14,15,18,25,35,42,45],'male-native.png',(.20,.14,.70,.75),4)
        for role in ['female','male']:
            panel(s[role+'_widePath'],[0,25,50,75,95,99,100,101,105,125,129,130,131,135,145,150],role+'-wide-native.png',(.2,.05,.44,.48) if role=='female' else (.50,.07,.75,.50),4)
    elif stage=='canvases':
        panel(s['canvas2Path'],[35,39,41,42],'male-cut-end.png',None,4)
        panel(s['canvas3Path'],[0,1,2,3],'wide-cut-start.png',None,4)
    elif stage=='final':
        panel(s['finalPath'],[0,12,24,36,52,53,72,95,96,120,144,168,180,198,216,239],'full-contact.png',None,4)

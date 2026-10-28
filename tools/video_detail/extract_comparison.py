"""Extract aligned comparison frames; diagnostic images are kept outside Git."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'SeedVR2Enhancement20261022'
FFMPEG='C:/install/FFmpeg/bin/ffmpeg.exe'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['sample','full'],required=True)
    stage=parser.parse_args().stage
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    paths=[state['originalVideoPath'],state['exportTaskIdPath'],state['sampleFinalTaskIdPath'] if stage=='sample' else state['fullFinalTaskIdPath']]
    times=[0,12,24,36,48] if stage=='sample' else [0,60,123,124,180,239]
    target=FOLDER/stage;target.mkdir(exist_ok=True)
    contact=Image.new('RGB',(640*3,385*len(times)),(12,20,32))
    roi=Image.new('RGB',(600*3,680*len(times)),(12,20,32))
    for row,frame in enumerate(times):
        for col,path in enumerate(paths):
            number=frame+(144 if stage=='sample' and col<2 else 0)
            output=target/f'{"ABC"[col]}-{frame:03}.png'
            if not output.exists():
                subprocess.run([FFMPEG,'-v','error','-i',str(DATA/path),'-vf',f'select=eq(n\\,{number})','-fps_mode','passthrough','-frames:v','1','-n',str(output)],check=True)
            image=Image.open(output).convert('RGB')
            contact.paste(image.resize((640,360)),(col*640,row*385+25))
            label=f'{"ABC"[col]} frame {number} / {number/24:.3f}s'
            ImageDraw.Draw(contact).text((col*640+8,row*385+5),label,fill='white')
            region=image.crop((650,300,1250,950))
            roi.paste(region,(col*600,row*680+25))
            ImageDraw.Draw(roi).text((col*600+8,row*680+5),label+' 1:1 crop',fill='white')
            if stage=='sample' and frame==36:
                region.save(target/f'{"ABC"[col]}-face-hand.png')
    contact.save(target/'contact.png');roi.save(target/'person-roi.png')
    print(str(target/'contact.png'));print(str(target/'person-roi.png'))


if __name__=='__main__':main()

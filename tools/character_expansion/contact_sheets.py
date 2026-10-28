"""Unaltered scaled contact sheets for actual visual inspection."""
import argparse
import subprocess
from batch import Batch,PEOPLE,SLOTS,FOLDER,media,logical

def sheet(entries,target,layout,size):
    command=['C:/install/FFmpeg/bin/ffmpeg.exe','-hide_banner','-loglevel','error','-y','-filter_complex_threads','1']
    for entry in entries:command+=['-i',str(media(entry['path']))]
    filters=[f'[{i}:v]scale={size[0]}:{size[1]}[v{i}]' for i in range(len(entries))]
    filters.append(''.join(f'[v{i}]' for i in range(len(entries)))+f'xstack=inputs={len(entries)}:layout={layout}:fill=0xf3f5f7[out]')
    command+=['-filter_complex',';'.join(filters),'-map','[out]','-frames:v','1',str(target)]
    subprocess.run(command,check=True,timeout=120)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['heads','masters','packs']);args=parser.parse_args();batch=Batch()
    if args.stage in ['heads','masters']:
        framing='closeUp' if args.stage=='heads' else 'fullBody'
        entries=[batch.selected(person,'front',framing) for person in PEOPLE]
        sheet(entries,FOLDER/(args.stage+'-contact.png'),'0_0|512_0|1024_0|256_288|768_288',(512,288))
        print(args.stage+' five-image contact sheet written',flush=True)
    else:
        for person in PEOPLE:
            keys=[batch.selected_key(logical(person,view,framing)) for view,framing in SLOTS]
            if not all(batch.state['tasks'].get(key,{}).get('path') for key in keys):continue
            sheet([batch.state['tasks'][key] for key in keys],FOLDER/(person['key']+'-nine-contact.png'),'0_0|512_0|1024_0|0_288|512_288|1024_288|0_576|512_576|1024_576',(512,288))
            print(person['key']+' nine-image contact sheet written',flush=True)

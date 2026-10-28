"""Unaltered candidate thumbnails for visual inspection; originals are retained."""
import subprocess
from run import Run,PEOPLE,SLOTS,FOLDER,media

r=Run()
for person in PEOPLE:
    keys=[r.selected_key(person['key']+'-'+view+'-'+framing) for view,framing in SLOTS]
    if not all(r.state['tasks'].get(key,{}).get('path') for key in keys):continue
    command=['C:/install/FFmpeg/bin/ffmpeg.exe','-hide_banner','-loglevel','error','-y','-filter_complex_threads','1']
    for key in keys:command.extend(['-i',str(media(r.state['tasks'][key]['path']))])
    filters=[f'[{i}:v]scale=512:288[v{i}]' for i in range(9)]
    filters.append(''.join(f'[v{i}]' for i in range(9))+'xstack=inputs=9:layout=0_0|512_0|1024_0|0_288|512_288|1024_288|0_576|512_576|1024_576[out]')
    command.extend(['-filter_complex',';'.join(filters),'-map','[out]','-frames:v','1',str(FOLDER/(person['key']+'-nine-contact.png'))])
    subprocess.run(command,check=True,timeout=120)
    print(person['name'],'nine-image contact sheet prepared',flush=True)

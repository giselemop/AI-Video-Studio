"""Compare exact24fps caption frame sets with the immutable ten-second SRT."""
from run import *
def cues(path):
    values=[]
    def seconds(t):
        h,m,tail=t.split(':');sec,ms=tail.split(',');return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
    for block in path.read_text(encoding='utf-8-sig').strip().split('\n\n'):
        lines=block.splitlines();a,b=lines[1].split(' --> ');values.append(dict(start=seconds(a),end=seconds(b),text='\n'.join(lines[2:])))
    return values
s=read(FOLDER/'run.json');original=cues(media(s['inputs']['subtitle']));rows=[]
for clip in CLIPS:
    selected=cues(FOLDER/(clip['name']+'.srt'));expected=[x for x in original if x['end']>clip['startFrame']/24 and x['start']<(clip['startFrame']+clip['frames'])/24]
    if len(selected)!=1 or len(expected)!=1 or selected[0]['text']!=expected[0]['text']:raise RuntimeError('Expected complete original line not retained')
    old,new=expected[0],selected[0]
    if old['start']<clip['startFrame']/24 or old['end']>(clip['startFrame']+clip['frames'])/24:raise RuntimeError('Excerpt cuts an original caption/utterance')
    original_frames=[i for i in range(clip['frames']) if old['start']<=(clip['startFrame']+i)/24<old['end']]
    new_frames=[i for i in range(clip['frames']) if new['start']<=i/24<new['end']]
    if original_frames!=new_frames:raise RuntimeError('Caption display frame timeline changed')
    rows.append(dict(clip=clip['name'],originalText=old['text'],completeLinePreserved=True,captionDisplayFramesEqual=True,visibleFrames=new_frames,sourceSubtitleSha256=sha(media(s['inputs']['subtitle']))))
write(FOLDER/'caption-timing-checks.json',dict(status='Passed',checks=rows,scope='UTF8 text and exact24fps scheduled frame sets; actual FFmpeg/browser rendering checked separately'))
print('Passed: both full original lines and exact caption display-frame timelines retained')

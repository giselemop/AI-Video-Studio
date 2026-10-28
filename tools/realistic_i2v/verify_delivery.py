"""Verify actual native H3 sources, final frames and complete Qwen narration."""
import copy
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image,ImageDraw
from run import DATA,FOLDER,FFMPEG,sha,probe


def main():
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    if state['stage'] not in ['AwaitingPlaybackInspection','ReadyForUserPreview']:raise RuntimeError('Actual final assembly is required')
    for source in state['sources']:
        if sha(DATA/source['path'])!=source['sha256']:raise RuntimeError('Previous media changed')
    graphs={};preserved=[]
    for field,name in [('video20TaskId','video-20'),('video30TaskId','video-30'),('continuationTaskId','continuation')]:
        path=DATA/state[field+'Path']
        if sha(path)!=state[field+'Sha256']:raise RuntimeError('Generated source changed')
        graph=json.loads((FOLDER/name/'execution-graph.json').read_text(encoding='utf-8'))
        if (graph['6']['inputs']['width'],graph['6']['inputs']['height'],graph['6']['inputs']['length'])!=(1920,1088,124):raise RuntimeError('Source canvas or length differs')
        if (graph['16']['inputs']['width'],graph['16']['inputs']['height'],graph['16']['inputs']['x'],graph['16']['inputs']['y'])!=(1920,1080,0,4):raise RuntimeError('Native crop differs')
        if graph['5']['is_changed']!=[state[field+'ReferenceSha256']]:raise RuntimeError('Source reference differs')
        preserved.append(dict(taskId=state[field],sha256=state[field+'Sha256'],status='Passed'))
        graphs[name]=graph
    left=copy.deepcopy(graphs['video-20']);right=copy.deepcopy(graphs['video-30'])
    assert left['10']['inputs']['steps']==20 and right['10']['inputs']['steps']==30
    for graph in [left,right]:
        graph['10']['inputs']['steps']='COMPARISON_VARIABLE'
        graph['5']['inputs']['image']=state['referenceSha256']
        for node in graph.values():
            if isinstance(node,dict) and 'filename_prefix' in node.get('inputs',{}):node['inputs']['filename_prefix']='TASK_OUTPUT_PREFIX'
    if left!=right:
        different=[key for key in set(left)|set(right) if left.get(key)!=right.get(key)]
        raise RuntimeError('Comparison graph differs beyond steps and task file paths: '+str(different))
    final=DATA/state['finalVideoPath']
    if sha(final)!=state['finalVideoSha256']:raise RuntimeError('Final output changed')
    streams=probe(final)['streams'];video=next(s for s in streams if s['codec_type']=='video')
    if (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))!=(1920,1080,'24/1',240):raise RuntimeError('Final media geometry differs')
    if not any(s['codec_type']=='audio' for s in streams):raise RuntimeError('Narration stream missing')
    if sha(DATA/state['sourceAudioPath'])!=state['sourceAudioSha256']:raise RuntimeError('Qwen source changed')
    actual=FOLDER/'final-audio.f32';expected=FOLDER/'reference-fitted-audio.f32';complete=FOLDER/'complete-fitted-audio.f32'
    for source,target,filters in [(final,actual,'atrim=duration=10,asetpts=PTS-STARTPTS'),
        (DATA/state['sourceAudioPath'],complete,'atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,asetpts=N/SR/TB'),
        (DATA/state['sourceAudioPath'],expected,'atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,apad=whole_dur=10,asetpts=N/SR/TB,atrim=duration=10')]:
        if not target.exists():subprocess.run([FFMPEG,'-v','error','-i',str(source),'-vn','-af',filters,'-ar','24000','-ac','1','-f','f32le','-n',str(target)],check=True)
    a=np.fromfile(actual,dtype='<f4');b=np.fromfile(expected,dtype='<f4');full=np.fromfile(complete,dtype='<f4')
    if len(a)!=240000 or len(b)!=240000 or not 0<len(full)<=240000 or not all(np.isfinite(x).all() for x in [a,b,full]):raise RuntimeError('Complete narration does not fit or contains invalid samples')
    correlation=float(np.corrcoef(a,b)[0,1])
    if not np.isfinite(correlation) or correlation<.97:raise RuntimeError('Final audio differs from the complete fitted Qwen source')
    audio=dict(status='Passed',sampleRate=24000,samples=len(a),correlationWithFittedQwen=correlation,
        tempo=1.32,startSeconds=.12,completeFittedSamples=len(full),completeFittedDurationSeconds=len(full)/24000,
        narrationSamplesTruncated=0,peakDb=float(20*np.log10(max(np.max(np.abs(a)),1e-9))),rmsDb=float(20*np.log10(max(np.sqrt(np.mean(a*a)),1e-9))))
    (FOLDER/'audio-correspondence.json').write_text(json.dumps(audio,indent=2),encoding='utf-8')
    hashes=subprocess.check_output([FFMPEG,'-v','error','-i',str(final),'-map','0:v:0','-f','framemd5','-'],encoding='utf-8')
    (FOLDER/'final-framemd5.txt').write_text(hashes,encoding='utf-8')
    frames=[line.rsplit(',',1)[-1].strip() for line in hashes.splitlines() if line and not line.startswith('#')]
    if len(frames)!=240:raise RuntimeError('Final full decode frame count differs')
    contact=Image.new('RGB',(1440,540),'#111111')
    for i,seconds in enumerate([0,2.4,4.8,5.3,7.4,9.7]):
        path=FOLDER/f'final-{seconds:04.1f}.png'
        if not path.exists():subprocess.run([FFMPEG,'-v','error','-ss',str(seconds),'-i',str(final),'-frames:v','1','-n',str(path)],check=True)
        image=Image.open(path).convert('RGB');image.thumbnail((480,270));x,y=(i%3)*480,(i//3)*270
        contact.paste(image,(x,y));ImageDraw.Draw(contact).text((x+8,y+8),f'{seconds:.1f}s',fill='white')
    contact.save(FOLDER/'final-contact.png')
    report=dict(status='Passed',decodedFrames=len(frames),uniqueDecodedFrameHashes=len(set(frames)),
        comparisonOnlyStepsDiffer=True,sources=preserved,originalSourcesPreserved=True,actualTailContinuationSha256=state['continuationTaskIdReferenceSha256'],
        finalVideoSha256=sha(final),audio=audio,contentStatus='NeedReview',publicationStatus='Blocked')
    (FOLDER/'delivery-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

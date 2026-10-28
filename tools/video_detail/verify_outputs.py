"""Verify exact media specifications, unchanged source bytes and narration preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/qwen3_tts'))
from run_video import sha,probe,FFMPEG
DATA=ROOT.parent/'Data'
FOLDER=DATA/'SeedVR2Enhancement20261022'


def output(args):
    return subprocess.check_output([FFMPEG,'-v','error',*map(str,args)])


def audio_hash(path):
    return hashlib.sha256(output(['-i',path,'-map','0:a:0','-c:a','copy','-f','adts','-'])).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--partial',action='store_true')
    args=parser.parse_args()
    run=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    for source in run['sources']:
        if sha(DATA/source['path'])!=source['sha256']:raise RuntimeError('Original source changed')
    fields=['exportTaskId','sampleExportTaskId','sampleRestoreTaskId','sampleFinalTaskId']+([] if args.partial else ['fullRestoreTaskId','fullFinalTaskId'])
    videos=[]; frame_hashes={}
    for field in fields:
        file=DATA/run[field+'Path']
        if sha(file)!=run[field+'Sha256']:raise RuntimeError('Recorded output changed')
        metadata=probe(file)
        v=next(s for s in metadata['streams'] if s['codec_type']=='video')
        frames=49 if field.startswith('sample') else 240
        if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1920,1080,'24/1',frames):raise RuntimeError('Output media specification differs')
        if abs(float(v['duration'])-frames/24)>.001:raise RuntimeError('Output video duration differs')
        hashes=output(['-i',file,'-map','0:v:0','-f','framemd5','-']).decode('utf-8')
        (FOLDER/(field+'-framemd5.txt')).write_text(hashes,encoding='utf-8')
        decoded=[line.rsplit(',',1)[-1].strip() for line in hashes.splitlines() if line and not line.startswith('#')]
        if len(decoded)!=frames or len(set(decoded))!=frames:raise RuntimeError('Decoded frame count differs or contains duplicate padding')
        frame_hashes[field]=decoded
        videos.append(dict(taskId=run[field],sha256=sha(file),frames=frames,uniqueFrames=len(set(decoded)),width=1920,height=1080,fps=24,status='Passed'))
    audio=[]
    pairs=[('sampleExportTaskId','sampleFinalTaskId')]+([] if args.partial else [('exportTaskId','fullFinalTaskId')])
    for before,after in pairs:
        expected=audio_hash(DATA/run[before+'Path']);actual=audio_hash(DATA/run[after+'Path'])
        if actual!=expected:raise RuntimeError('SeedVR2 changed AAC audio payload')
        audio.append(dict(sourceTaskId=run[before],restoredTaskId=run[after],aacPayloadSha256=actual,status='Passed'))
    for before,after in [('sampleRestoreTaskId','sampleFinalTaskId')]+([] if args.partial else [('fullRestoreTaskId','fullFinalTaskId')]):
        if frame_hashes[before]!=frame_hashes[after]:raise RuntimeError('Audio preservation changed restored video frames')
    reference=np.frombuffer(output(['-i',DATA/run['sourceAudioPath'],'-vn','-af',
        'atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,apad=whole_dur=10,asetpts=N/SR/TB,atrim=duration=10',
        '-ar','24000','-ac','1','-f','f32le','-']),dtype='<f4')
    source=DATA/run['exportTaskIdPath' if args.partial else 'fullFinalTaskIdPath']
    actual=np.frombuffer(output(['-i',source,'-vn','-af','atrim=duration=10,asetpts=PTS-STARTPTS','-ar','24000','-ac','1','-f','f32le','-']),dtype='<f4')
    if len(actual)!=240000 or len(reference)!=240000 or not np.isfinite(actual).all():raise RuntimeError('Narration decode samples differ')
    correlation=float(np.corrcoef(actual,reference)[0,1])
    if not np.isfinite(correlation) or correlation<.97:raise RuntimeError('Narration no longer matches the complete Qwen source')
    complete=output(['-i',DATA/run['sourceAudioPath'],'-vn','-af','atempo=1.32,asetpts=PTS-STARTPTS,adelay=120:all=1,asetpts=N/SR/TB','-ar','24000','-ac','1','-f','f32le','-'])
    if not 0<len(complete)//4<=240000:raise RuntimeError('Complete narration cannot fit the target video')
    samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text(encoding='utf-8').splitlines()]
    peaks={str(task):max(s['usedVramMiB'] for s in samples if s['taskId']==task) for task in set(s['taskId'] for s in samples)}
    report=dict(status='Passed',scope='partial' if args.partial else 'full',originalSourcesPreserved=True,videos=videos,
        restoredVideoFramesPreservedDuringRemux=True,audioPayloadPreserved=audio,narrationCorrelation=correlation,narrationSamples=240000,narrationSamplesTruncated=0,
        completeFittedNarrationSamples=len(complete)//4,completeFittedNarrationSeconds=len(complete)/4/24000,
        audioPeakDb=float(20*np.log10(max(float(np.max(np.abs(actual))),1e-9))),
        sampledDevicePeakVramMiB=peaks,samplingIntervalSeconds=5,contentStatus='NeedReview',publicationStatus='Blocked')
    (FOLDER/('partial-verification.json' if args.partial else 'output-verification.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

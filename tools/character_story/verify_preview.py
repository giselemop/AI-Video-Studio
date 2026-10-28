"""Adopt and verify the actual UI-submitted preview; does not submit or retry."""
from pathlib import Path
import sys,json,subprocess,requests,msvcrt
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,DATA,OUT,write,sha,mysql

def run():
    pilot=json.loads((OUT/'pilot.json').read_text(encoding='utf-8'));ids=[s['Video']['id'] for s in pilot['slots'].values()]
    rows=[json.loads(line) for line in mysql("SELECT JSON_OBJECT('id',id,'status',status,'input',input_json) FROM generation_tasks WHERE task_type='Concat' AND project_id="+str(pilot['projectId'])+' ORDER BY id;').splitlines()]
    matches=[r for r in rows if r['input']['parameters'].get('storyPreview',{}).get('request',{}).get('taskIds')==ids]
    assert len(matches)==1,'Inspect matching preview IDs; never blindly resubmit'
    row=matches[0];marker=row['input']['parameters']['storyPreview'];tid=row['id'];assert row['status']=='Succeeded'
    detail=requests.get(f'http://127.0.0.1:18080/api/tasks/{tid}',timeout=30).json();asset=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.mp4'));path=(DATA/asset['assetPath']).resolve(strict=True)
    checks=[]
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        if not passed:raise AssertionError(name)
    check('actual CPU business task and dependency',detail['task']['resourceClass']=='CPU' and row['input']['DependencyTaskId']==ids[-1])
    check('actual preview belongs to original Episode',marker['request']['episodeId']==pilot['episodeId'])
    check('selected clip order retained',[c['taskId'] for c in marker['clips']]==ids)
    check('controlled real preview file',path.is_relative_to(DATA.resolve()))
    for source in marker['clips']:check('unchanged selected source '+str(source['taskId']),sha(DATA/source['path'])==source['sha256'])
    probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(OUT/f'{tid}-preview-ffprobe.json',probe);video=next(s for s in probe['streams'] if s['codec_type']=='video')
    check('four full 124-frame clips, 24FPS, 864x480',int(video['nb_read_frames'])==496 and video['avg_frame_rate']=='24/1' and video['width']==864 and video['height']==480)
    check('PostDubbing removes native audio',marker['audioStrategy']=='PostDubbing' and not any(s['codec_type']=='audio' for s in probe['streams']))
    check('complete preview duration',abs(float(probe['format']['duration'])-496/24)<.15)
    decode=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120);check('full preview decode',decode.returncode==0 and not decode.stderr)
    response=requests.get('http://127.0.0.1:18080/api/media',params=dict(assetPath=asset['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30);check('preview HTTP Range206',response.status_code==206 and len(response.content)==1024)
    pilot['preview']=dict(id=tid,status='Succeeded',body=marker['request'],assetPath=asset['assetPath'],sha256=sha(path),audioStrategy='PostDubbing');write(OUT/'pilot.json',pilot)
    write(OUT/'preview-media-checks.json',dict(status='Passed',checks=checks,taskId=tid,assetPath=asset['assetPath'],sha256=sha(path),width=864,height=480,fps=24,frames=496,duration=float(probe['format']['duration']),hasAudio=False,contentReview='NeedReview',publication='Blocked'))
    print(f'Actual UI preview {tid}: {len(checks)} checks Passed, 496 frames / 24FPS / no native audio. No additional task submitted.')
if __name__=='__main__':
    with (OUT/'pilot-controller.lock').open('a+b') as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);run()

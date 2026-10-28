"""Real preflight tests for a hash-bound, separately mixed audio preview."""
import copy,json
from character_continuation import Continuation,DATA,OUT,OLD,sha,write,mysql

def main():
    p=Continuation();s=p.state;p.preserve();old=json.loads(OLD.read_text(encoding='utf-8'));source=old['Preview'];tracks=s['audioTracks'];caption=s['captions']
    manifest=[dict(path=source['assetPath'],sha256=source['sha256'])]
    for t in tracks:
        item=next(x for x in [*s['narration'],s['music']] if x['assetPath']==t['path']);manifest.append(dict(path=t['path'],sha256=item['sha256']))
    manifest.append(dict(path=caption['assetPath'],sha256=caption['sha256']))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,parameters=dict(files=[source['assetPath']],targetFps=24,originalAudioVolume=0,audioTracks=tracks,subtitlePath=caption['assetPath'],sourceChecks=manifest))
    before=int(mysql('SELECT COUNT(*) FROM generation_tasks;'));checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(OUT/'mix-preflight-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    check('frozen preview, narration, music and subtitles pass preflight',p.api('/api/tasks/preflight',body)['passed'])
    bad=copy.deepcopy(body);bad['parameters']['sourceChecks'][0]['sha256']='0'*64
    check('changed source hash rejected before queueing',not p.api('/api/tasks/preflight',bad)['passed'])
    bad=copy.deepcopy(body);bad['parameters']['sourceChecks'].pop()
    check('missing subtitle source rejected',not p.api('/api/tasks/preflight',bad)['passed'])
    bad=copy.deepcopy(body);bad['parameters']['audioTracks'][-1]['fadeOutDurationSeconds']=61
    check('invalid fade duration rejected',not p.api('/api/tasks/preflight',bad)['passed'])
    bad=copy.deepcopy(body);bad['parameters'].pop('sourceChecks')
    check('existing unmarked concat remains compatible',p.api('/api/tasks/preflight',bad)['passed'])
    check('preflight tests did not create tasks',int(mysql('SELECT COUNT(*) FROM generation_tasks;'))==before)
    write(OUT/'mix-preflight-checks.json',dict(status='Passed',checks=checks,submitted=0));print(str(len(checks))+' audio mix and hash-bound source checks Passed; no task submitted.')

if __name__=='__main__':main()

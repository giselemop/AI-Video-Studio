"""Read-only live boundary checks before submitting a continuation."""
import copy,json,msvcrt
from character_continuation import Continuation,DATA,OUT,OLD,sha,write,mysql


def main():
 with (OUT/'controller.lock').open('a+b') as lock:
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    p=Continuation();s=p.state;p.preserve();p.idle();old=json.loads(OLD.read_text(encoding='utf-8'));shot=s['shots'][0]
    before=int(mysql('SELECT COUNT(*) FROM generation_tasks;'));checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(OUT/'api-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    def reject(name,body):
        response=p.session.post(p.base+'/api/character-story/resolve/Video',json=body,timeout=120)
        check(name,response.status_code==422)
    original=p.api('/api/character-story/resolve/Video',old['Video']['body'])
    prior=json.loads((OLD.parent/'video-resolved.json').read_text(encoding='utf-8'))
    check('historical keyframe video resolution unchanged',original['task']==prior['task'])
    body=dict(planId=shot['planId'],profile='baseline480',seed=2026102802,continuationSourceTaskId=s['sourceVideoTaskId'],continuationReviewId=s['sourceReviewId'],continuationFramePath=s['sourceTailPath'],continuationFrameSha256=s['sourceTailSha256'],idempotencyKey=p.key('shot2-video'))
    result=p.api('/api/character-story/resolve/Video',body);task=result['task'];marker=task['parameters']['storyPipeline'];provenance=marker['continuation']
    check('checked actual last frame is the H3 input',task['inputImagePath']==s['sourceTailPath'] and marker['inputSha256']==s['sourceTailSha256'] and provenance['frameIndex']==123)
    check('previous video, review and hash are explicit dependencies',task['dependencyTaskId']==1555 and provenance['sourceTaskId']==1555 and provenance['sourceReviewId']==s['sourceReviewId'] and provenance['sourceVideoSha256']==s['sourceVideoSha256'])
    check('H3 keeps prior source resolution and contract',all(task['parameters'][k]==v for k,v in dict(width=864,height=480,frames=124,fps=24,steps=20).items()))
    bad=copy.deepcopy(body);bad['continuationFrameSha256']='0'*64;reject('changed tail hash is rejected',bad)
    bad=copy.deepcopy(body);other=DATA/'CharacterPlotPreview20261027/video-1555/frames/frame-24.png';bad['continuationFramePath']=other.relative_to(DATA).as_posix();bad['continuationFrameSha256']=sha(other);reject('another actual frame is not accepted as tail',bad)
    bad=copy.deepcopy(body);bad['continuationReviewId']=old['Keyframe']['inspection']['id'];reject('wrong review cannot approve the source video',bad)
    bad=copy.deepcopy(body);bad['continuationSourceTaskId']=1551;reject('experimental video from another project is rejected',bad)
    bad=copy.deepcopy(body);bad['planId']=s['shots'][1]['planId'];reject('cannot skip the intervening shot',bad)
    bad=copy.deepcopy(body);bad['keyframeTaskId']=old['Keyframe']['id'];reject('cannot mix keyframe and continuation entry modes',bad)
    generic=p.api('/api/tasks/preflight',task);check('generic task endpoint cannot bypass story validation',not generic['passed'])
    music=dict(projectId=s['projectId'],taskType='MusicSynthesis',resourceClass='CPU',maxRetries=0,parameters=dict(composition='window-warm-piano-v1',durationSeconds=15.5))
    check('fixed original music passes CPU preflight',p.api('/api/tasks/preflight',music)['passed'])
    bad=copy.deepcopy(music);bad['parameters']['composition']='unregistered';check('unknown music composition rejected',not p.api('/api/tasks/preflight',bad)['passed'])
    bad=copy.deepcopy(music);bad['resourceClass']='GPU';check('music cannot reserve GPU',not p.api('/api/tasks/preflight',bad)['passed'])
    check('no test queued any task',int(mysql('SELECT COUNT(*) FROM generation_tasks;'))==before)
    write(OUT/'shot2-resolved-before.json',result);write(OUT/'api-checks.json',dict(status='Passed',checks=checks,gpuSubmitted=0))
    print(str(len(checks))+' real API continuity, music and legacy compatibility checks Passed; no generation submitted.')


if __name__=='__main__':main()

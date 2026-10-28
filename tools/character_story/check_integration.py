"""Real casting/Shot/trace/idempotency checks. No GPU generation is created here.
Only the existing labelled project49 test fixture is mutated; pilot records replay read only.
"""
from pathlib import Path
import sys,json,requests,uuid
sys.path.insert(0,str(Path(__file__).parent))
from setup import OUT,write,mysql
BASE='http://127.0.0.1:18080'
def run():
    path=OUT/'integration-fixtures.json';state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(runId=str(uuid.uuid4()),records={})
    s=requests.Session();auth=s.get(BASE+'/api/auth/status').json();assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];s.headers['X-CSRF-Token']=auth['csrfToken']
    checks=[]
    def save():write(path,state)
    def key(name):return 'story-integration:'+state['runId']+':'+name
    def call(name,url,body=None,code=200):
        r=s.request('POST' if body is not None else 'GET',BASE+url,json=body,timeout=180)
        if r.status_code!=code:raise AssertionError(name+' HTTP'+str(r.status_code)+' '+r.text[:600])
        checks.append(dict(name=name,status='Passed',http=r.status_code));write(OUT/'integration-checks.json',dict(status='Running',checks=checks,gpuTasksCreatedByTests=0));return r.json()
    if state.get('completed'):
        cast=s.get(BASE+'/api/character-story/projects/49/cast?episodeId='+str(state['episodeId']),timeout=30).json()
        assert cast['episode']['id']==state['records']['episodeCast']['id'] and cast['episode']['payload']['roles'][0]['versionId']==4
        shot=s.get(BASE+'/api/character-story/shots/'+str(state['shotId']),timeout=30).json()
        assert shot['plans'][0]['id']==state['records']['shotPlan']['id']
        write(OUT/'integration-readonly-recheck.json',dict(status='Passed',episodeCastId=cast['episode']['id'],shotPlanId=shot['plans'][0]['id'],noTaskSubmitted=True))
        if '--verify-existing' not in sys.argv:
            print('Completed integration checkpoint verified read-only; no new task or cast record.');return
    save();countBefore=mysql('SELECT COUNT(*) FROM generation_tasks WHERE project_id=49;')
    first=dict(roles=[dict(role='回归角色',versionId=4)],audioStrategy='PostDubbing',idempotencyKey=key('cast-A'))
    if 'castA' not in state['records']:state['records']['castA']=call('save immutable project cast','/api/character-story/projects/49/cast',first);save()
    same=call('cast idempotent replay preserves id','/api/character-story/projects/49/cast',first);assert same['id']==state['records']['castA']['id']
    call('same cast key with changed version conflicts','/api/character-story/projects/49/cast',dict(first,roles=[dict(role='回归角色',versionId=5)]),409)
    if 'episodeId' not in state:
        old=next((e for e in call('read fixture episodes','/api/projects/49/episodes') if e['name']=='选角绑定回归（无生成）'),None)
        state['episodeId']=old['id'] if old else call('create labelled fixture Episode','/api/episodes',dict(projectId=49,name='选角绑定回归（无生成）',episodeNumber=1,outputWidth=864,outputHeight=480,outputFps=24),201)['id'];save()
    eid=state['episodeId']
    if 'episodeCast' not in state['records']:state['records']['episodeCast']=call('pin project cast to Episode','/api/character-story/episodes/'+str(eid)+'/cast',dict(idempotencyKey=key('episode-cast')));save()
    if not state.get('projectUpdated'):
        same=call('Episode snapshot idempotent before cast change','/api/character-story/episodes/'+str(eid)+'/cast',dict(idempotencyKey=key('episode-cast')));assert same['id']==state['records']['episodeCast']['id']
        state['records']['castB']=call('explicit project cast update creates new version','/api/character-story/projects/49/cast',dict(first,roles=[dict(role='回归角色',versionId=5)],idempotencyKey=key('cast-B')));state['projectUpdated']=True;save()
    cast=call('Episode keeps original actor after project update',f'/api/character-story/projects/49/cast?episodeId={eid}');assert cast['projectChanged'] and cast['episode']['payload']['roles'][0]['versionId']==4 and cast['project']['payload']['roles'][0]['versionId']==5
    if 'shotId' not in state:
        old=next((v for v in call('read fixture shots',f'/api/episodes/{eid}/shots') if v['title']=='分镜版本绑定回归（无生成）'),None)
        state['shotId']=old['id'] if old else call('create labelled fixture Shot','/api/shots',dict(projectId=49,episodeId=eid,shotNumber=1,title='分镜版本绑定回归（无生成）',width=864,height=480,frames=124,fps=24,durationSeconds=124/24),201)['id'];save()
    sid=state['shotId'];plan=dict(episodeCastId=state['records']['episodeCast']['id'],actors=[dict(role='回归角色',view='front',framing='closeUp',position='center',action='Neutral still pose')],shotFraming='closeUp',scene='Labelled test fixture, no rendering',action='Neutral still pose',camera='Locked',props='None',idempotencyKey=key('shot-plan'))
    if 'shotPlan' not in state['records']:state['records']['shotPlan']=call('Shot freezes original Episode actor version','/api/character-story/shots/'+str(sid),plan);save()
    same=call('Shot plan idempotent replay preserves id','/api/character-story/shots/'+str(sid),plan);assert same['id']==state['records']['shotPlan']['id'] and same['payload']['actors'][0]['versionId']==4
    call('wrong Episode snapshot rejected','/api/character-story/shots/'+str(sid),dict(plan,episodeCastId=7,idempotencyKey=key('wrong-episode')),422)
    call('missing back face reference never falls back','/api/character-story/shots/'+str(sid),dict(plan,actors=[dict(role='回归角色',view='back',framing='closeUp',position='center')],idempotencyKey=key('missing-back-face')),422)
    call('wrong actor role rejected','/api/character-story/shots/'+str(sid),dict(plan,actors=[dict(role='未选角角色',view='front',framing='closeUp',position='center')],idempotencyKey=key('wrong-role')),422)
    pilot=json.loads((OUT/'pilot.json').read_text(encoding='utf-8'));a=pilot['slots']['a-face']['Keyframe'];base=dict(planId=pilot['slots']['a-face']['planId'],keyframeTaskId=a['id'],profile='baseline480',seed=2026102701,idempotencyKey=key('negative-video'))
    call('video blocked before explicit static review','/api/character-story/generate/Video',dict(base,reviewId=0),422)
    call('keyframe from another Shot plan rejected','/api/character-story/resolve/Video',dict(base,planId=pilot['slots']['a-body']['planId'],reviewId=a['inspection']['id']),422)
    call('cross-project keyframe source rejected','/api/character-story/resolve/Video',dict(base,planId=state['records']['shotPlan']['id'],reviewId=a['inspection']['id']),422)
    resolved=call('H3 binds reviewed actual story keyframe','/api/character-story/resolve/Video',dict(base,reviewId=a['inspection']['id']))['task'];assert resolved['inputImagePath']==a['assetPath'] and resolved['parameters']['storyPipeline']['inputSha256']==a['sha256'] and resolved['parameters']['frames']==124 and resolved['parameters']['fps']==24
    replay=call('completed real keyframe idempotent submission returns original task','/api/character-story/generate/Keyframe',a['body']);assert replay['id']==a['id'] and not replay['created']
    call('changed real request with same key conflicts','/api/character-story/generate/Keyframe',dict(a['body'],seed=a['body']['seed']+1),409)
    call('passed keyframe cannot be repaired as a failed task','/api/character-story/generate/Keyframe',dict(a['body'],seed=a['body']['seed']+10,repairOfTaskId=a['id'],changeReason='negative repair test',idempotencyKey=key('invalid-repair')),422)
    assert mysql('SELECT COUNT(*) FROM generation_tasks WHERE project_id=49;')==countBefore
    state['completed']=True;save();write(OUT/'integration-checks.json',dict(status='Passed',checks=checks,fixture=state,gpuTasksCreatedByTests=0,originalPilotVersionIds=[4,5],humanApprovals=0));print(str(len(checks))+' real integration checks Passed; no GPU job created by tests.')
if __name__=='__main__':run()

"""Real API checks without GPU submission or human approval. Fixtures remain clearly labelled.
Does not mutate existing people, immutable versions, or task status.
"""
from pathlib import Path
import requests,json,uuid,sys
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,OUT,DATA,write,mysql,sha
BASE='http://127.0.0.1:18080'
def run():
    session=requests.Session();auth=session.get(BASE+'/api/auth/status',timeout=30).json()
    assert auth.get('accessMode')=='LocalOnly' and not auth['loginRequired']
    session.headers['X-CSRF-Token']=auth['csrfToken']
    checks=[]
    def call(name,path,body=None,status=200,method=None):
        r=session.request(method or ('POST' if body is not None else 'GET'),BASE+path,json=body,timeout=120)
        if r.status_code!=status:raise AssertionError(name+': HTTP '+str(r.status_code)+' '+r.text[:500])
        value=r.json();checks.append(dict(name=name,status='Passed',http=r.status_code));write(OUT/'api-checks.json',dict(status='Running',checks=checks,gpuSubmitted=0,humanApprovalsWritten=0));return value
    before=mysql('SELECT COUNT(*) FROM generation_tasks;')
    library=call('existing library readable','/api/character-library');frozen={v['id']:v['sha256'] for v in library['versions']}
    readiness=call('migration readiness accurately reported','/api/character-story/readiness')
    caps=call('capabilities distinguish first-frame and unverified Ref2VA','/api/character-story/capabilities');assert not caps['h3Ref2VA'] and not caps['formalProduction']
    review=call('nine slots are separate from content approval','/api/character-story/library-reviews');assert all(r['contentStatus']=='NeedReview' for r in review if r['versionId'] in [4,5])
    for version in [4,5]:
        result=call('exact reference resolution v'+str(version),'/api/character-library/resolve',dict(projectId=46,versionId=version,view='front',framing='closeUp',prompt='Quiet reading room, gentle head motion',seed=2026102701,idempotencyKey='readonly-check-'+str(version)))
        assert result['binding']['referenceSha256']==next(r['sha256'] for v in library['versions'] if v['id']==version for r in v['payload']['references'] if r['view']=='front' and r.get('framing')=='closeUp')
    call('missing view never falls back','/api/character-library/resolve',dict(projectId=46,versionId=4,view='back',framing='closeUp',prompt='x'),422)
    call('nonexistent immutable version rejected','/api/character-library/resolve',dict(projectId=46,versionId=999999,view='front',framing='closeUp',prompt='x'),422)
    fixture=OUT/'api-fixtures.json'
    state=json.loads(fixture.read_text()) if fixture.exists() else {}
    if not state.get('projectId'):
        result=call('create labelled workflow test project','/api/projects',dict(name='人物剧情接口验证_20261027（无生成）',description='Retained API regression fixture. No generated assets, no human content approval.',defaultWidth=864,defaultHeight=480,defaultFps=24),201);state['projectId']=result['id'];write(fixture,state)
    if not state.get('characterId'):
        facts=dict(projectId=state['projectId'],name='接口验证人物草稿（未生成）',ageSetting='30岁成年虚构人物',faceFeatures='Oval face, dark brown eyes',hair='Short black hair',bodyRatio='Natural adult proportions',clothes='Blue shirt and beige trousers',fixedPrompt='Fictional adult East Asian man, age30, oval face, short black hair',metadata=dict(referenceStudio=dict(shoes='Black leather shoes',immutableTraits='Keep oval face, eye shape and short black hairstyle')))
        result=call('new character facts including shoes and invariants','/api/characters',facts,201);state['characterId']=result['id'];write(fixture,state)
    character=state['characterId'];project=state['projectId']
    result=call('draft candidate collection readable','/api/character-workshop/'+str(character));assert result['anchors'] is None and all(r['metadata']['stage']=='regression-test' for r in result['references'])
    if not readiness.get('referenceReviewAuditReady',True) and result['references']:
        ref=result['references'][0]
        response=call('missing audit table rolls back test reference rejection',f"/api/characters/{character}/references/{ref['id']}/review",dict(decision='Rejected',note='只针对未生成测试副本的事务回滚测试，不是人工素材审核'),503)
        assert response['code']=='REFERENCE_REVIEW_MIGRATION_REQUIRED'
        after=call('test reference remains pending after rejected transaction','/api/character-workshop/'+str(character));assert after['references'][0]['metadata']['humanReviewStatus']=='NeedReview'
    request=dict(characterId=character,kind='identity',view='front',framing='closeUp',seed=2026102701,idempotencyKey='readonly-character-candidate-20261027')
    result=call('RealVis initial candidate resolves without generation','/api/character-workshop/resolve',request);assert result['task']['parameters']['width']==1536 and result['task']['parameters']['height']==864
    assert 'Black leather shoes' not in result['task']['parameters']['positive'] and 'Blue shirt and beige trousers' not in result['task']['parameters']['positive']
    assert 'Fictional adult East Asian man' in result['task']['parameters']['positive']
    call('unconfirmed identity blocks outfit derivation','/api/character-workshop/resolve',dict(request,kind='outfit',framing='fullBody'),422)
    call('wrong close-up slot rejected','/api/character-workshop/resolve',dict(request,view='back'),422)
    call('unapproved missing anchor rejected','/api/character-workshop/'+str(character)+'/anchors',dict(identityId=99999,outfitId=0,idempotencyKey=str(uuid.uuid4())),422)
    call('cross-project source adoption rejected','/api/character-workshop/'+str(character)+'/collect',dict(taskId=1454,view='front',framing='closeUp'),422)
    call('business marker cannot bypass repair budget at generic queue','/api/tasks',result['task'],422)
    call('human final review cannot be written without acknowledgment','/api/character-story/inspect',dict(taskId=1454,scope='HumanReview',decision='Passed',note='negative check',idempotencyKey=str(uuid.uuid4())),422)
    call('invalid audio policy rejected','/api/character-story/projects/'+str(project)+'/cast',dict(roles=[dict(role='主角',versionId=4)],audioStrategy='Automatic',idempotencyKey=str(uuid.uuid4())),422)
    call('wrong cast version rejected','/api/character-story/projects/'+str(project)+'/cast',dict(roles=[dict(role='主角',versionId=999999)],idempotencyKey=str(uuid.uuid4())),422)
    if not readiness['ready']:
        body=dict(roles=[dict(role='主角',versionId=4)],audioStrategy='PostDubbing',idempotencyKey='migration-blocked-api-check-20261027')
        for i in range(2):
            result=call('unavailable migration prevents partial cast write '+str(i+1),'/api/character-story/projects/'+str(project)+'/cast',body,503);assert result['code']=='STORY_MIGRATION_REQUIRED'
        result=call('no partial cast was saved','/api/character-story/projects/'+str(project)+'/cast');assert result['project'] is None
    assert mysql('SELECT COUNT(*) FROM generation_tasks;')==before
    after=call('old immutable hashes retained','/api/character-library');assert frozen=={v['id']:v['sha256'] for v in after['versions']}
    allowActive='--allow-active' in sys.argv
    status=call('queue GPU concurrency1'+(' while registered pilot runs' if allowActive else ' and idle'),'/api/minimax/local/status');assert status['queue']['gpuConcurrency']==1 and status['queue']['activeTasks']<=(1 if allowActive else 0)
    write(OUT/'api-checks.json',dict(status='Passed',checks=checks,fixture=state,migration=readiness,taskCountBeforeAfter=before,gpuSubmitted=0,humanApprovalsWritten=0,dependentTests='Blocked' if not readiness['ready'] else 'Pending'))
    print(str(len(checks))+' API checks Passed; no GPU work, no approvals; migration-dependent acceptance recorded separately.')
if __name__=='__main__':run()

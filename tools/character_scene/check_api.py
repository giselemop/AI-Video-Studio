"""Live scene/Shot contract checks; no GPU submission, no human approval."""
from pathlib import Path
import sys,json,copy
sys.path.insert(0,str(Path(__file__).parent))
from pilot import Pilot,REGIONS,SCENE
from common import OUT,write,mysql

def run():
    p=Pilot();checks=[];count=mysql('SELECT COUNT(*) FROM generation_tasks;');versions=p.api('/api/character-library')['versions']
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:raise AssertionError(name)
    def reject(name,url,body,code=422):
        response=p.s.post(p.base+url,json=body,timeout=180);check(name,response.status_code==code)
    check('old immutable character versions unchanged',{v['id']:v['sha256'] for v in versions}=={v['id']:v['sha256'] for v in p.state['originalVersions']})
    scenes=p.api('/api/character-story/scenes?projectId='+str(p.state['projectId']));scene=next(v for v in scenes if v['id']==p.state['sceneVersionId'])
    check('frozen scene version SHA and real original task retained',scene['sha256']==p.state['sceneVersionSha256'] and scene['payload']['source']['taskId']==1514)
    for slot,item in p.state['slots'].items():
        plan=next(v for v in p.api('/api/character-story/shots/'+str(item['shotId']))['plans'] if v['id']==item['planId'])
        check(slot+' same scene immutable version',plan['payload']['sceneBinding']['versionId']==scene['id'] and plan['payload']['sceneBinding']['versionSha256']==scene['sha256'])
        check(slot+' two independent actor versions and positions',[(a['characterId'],a['versionId'],a['position']) for a in plan['payload']['actors']]==[(19,4,'left'),(20,5,'right')])
    item=p.state['slots']['search'];request=dict(planId=item['planId'],profile='baseline480',seed=2026102731,idempotencyKey=p.key('readonly-resolve'))
    resolved=p.api('/api/character-story/resolve/Keyframe',request)['task'];slots=resolved['parameters']['inputSlots']
    check('five distinct source roles and paths',len(slots)==5 and len(set(slots.values()))==5)
    check('scene input SHA frozen separately from actor references',resolved['parameters']['storyPipeline']['inputHashes'][slots['sceneReference']]==scene['payload']['source']['sha256'])
    check('explicit background composite and region provenance',resolved['parameters']['sceneLock']['versionId']==scene['id'] and len(resolved['parameters']['sceneLock']['payload']['regions'])==2)
    base=item['planBody'];uri='/api/character-story/shots/'+str(item['shotId'])
    reject('nonexistent scene cannot silently fall back',uri,dict(base,sceneVersionId=999999,idempotencyKey=p.key('negative-missing-scene')))
    reject('camera pan rejected before any plan write',uri,dict(base,camera='Pan right',idempotencyKey=p.key('negative-pan')))
    reject('different room rejected for locked scene',uri,dict(base,scene='A different room',idempotencyKey=p.key('negative-room')))
    reject('wrong scene framing rejected',uri,dict(base,shotFraming='medium',idempotencyKey=p.key('negative-framing')))
    wrong=copy.deepcopy(base);wrong['actors'][0]['position']='right';wrong['actors'][1]['position']='left';wrong['idempotencyKey']=p.key('negative-swapped');reject('swapped actor positions rejected',uri,wrong)
    reject('raw generic submit cannot bypass business scene contract','/api/tasks',resolved)
    reject('other plan old keyframe cannot become new video source','/api/character-story/resolve/Video',dict(request,keyframeTaskId=1514,reviewId=17))
    capture=f'/api/character-story/scenes/{p.state["sceneId"]}/capture';source=dict(sourceTaskId=1514,description=SCENE,regions=REGIONS,idempotencyKey=p.key('scene-version'))
    same=p.api(capture,source);check('scene capture replay preserves original version',same['id']==scene['id'])
    reject('failed image cannot become a scene baseline',capture,dict(source,sourceTaskId=1511,idempotencyKey=p.key('negative-rejected-source')))
    bad=copy.deepcopy(source);bad['regions'][0]['width']=9999;bad['idempotencyKey']=p.key('negative-region');reject('invalid region rejected before write',capture,bad)
    reject('cross-project scene version rejected','/api/character-story/shots/252',dict(base,episodeCastId=19,actors=[dict(role='回归角色',view='front',framing='fullBody',position='left')],idempotencyKey=p.key('negative-project')))
    check('no GPU task created by API tests',mysql('SELECT COUNT(*) FROM generation_tasks;')==count)
    write(OUT/'api-checks.json',dict(status='Passed',checks=checks,taskCountBeforeAfter=count,gpuTasksCreated=0,humanApprovals=0));print(f'{len(checks)} live API checks Passed; no GPU task or human approval created.')
if __name__=='__main__':run()

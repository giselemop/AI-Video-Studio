"""Current review-hold regression; external user-owned task runs are preserved."""
import datetime
from pathlib import Path
from pilot import Pilot
from common import OUT,DATA,ROOT,write,sha,mysql

def run():
    p=Pilot();checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:raise AssertionError(name)
    before=mysql('SELECT COUNT(*) FROM generation_tasks;');versions=p.api('/api/character-library')['versions'];current={v['id']:v['sha256'] for v in versions}
    check('user review hold is explicit and no automatic static continuity approval',p.state.get('generationHold',{}).get('userReply')=='保持待审' and p.state['generationHold']['active'] and not p.state['staticContinuityPassed'])
    try:p.require_generation_allowed()
    except RuntimeError as e:check('controller blocks new generation before any request', '保持待审' in str(e))
    else:raise AssertionError('Review hold not enforced')
    for v in p.state['originalVersions']:check('original immutable character version '+str(v['id'])+' unchanged',current.get(v['id'])==v['sha256'])
    check('previous completed story checkpoint unchanged',sha(Path(p.state['previousPilotPath']))==p.state['previousPilotSha256'])
    check('separate expansion checkpoint unchanged',sha(DATA/'CharacterExpansionFive20261026/run.json')==p.state['expansionCheckpointSha256'])
    for item in p.state['protectedFiles']:check('protected historical media '+Path(item['assetPath']).name,sha(DATA/item['assetPath'])==item['sha256'])
    scenes={v['id']:v for v in p.api('/api/character-story/scenes?projectId='+str(p.state['projectId']))}
    check('initial immutable scene retained',scenes[p.state['sceneVersionId']]['sha256']==p.state['sceneVersionSha256'])
    check('targeted scene repair version retained separately',scenes[p.state['repairSceneVersionId']]['sha256']==p.state['repairSceneVersionSha256'])
    for key,item in p.state['slots'].items():
        plans={v['id']:v for v in p.api('/api/character-story/shots/'+str(item['shotId']))['plans']}
        original=plans[item['Keyframe']['body']['planId']]
        check(key+' original output keeps original plan and scene',original['payload']['sceneBinding']['versionId']==p.state['sceneVersionId'])
        check(key+' current plan scene is explicit',plans[item['planId']]['payload']['sceneBinding']['versionId']==item['planBody']['sceneVersionId'])
        check(key+' has no new video',not item.get('Video',{}).get('id'))
    reviews=p.api('/api/character-story/library-reviews');write(OUT/'current-library-review-block.json',reviews)
    check('rejected pinned actor versions are reported live',any(r['versionId'] in [4,5] and r['contentStatus']=='Rejected' for r in reviews))
    entry=p.state['slots']['search'];body=dict(planId=entry['planId'],profile=p.state['profile'],seed=2026102731,idempotencyKey=p.key('negative-source-review-hold'))
    for operation in ['resolve','generate']:
        response=p.s.post(p.base+'/api/character-story/'+operation+'/Keyframe',json=body,timeout=60)
        check(operation+' rejects actual refused sources without fallback',response.status_code==422 and '拒绝' in response.text)
    counts=[p.api('/api/tasks?limit='+str(n)) for n in [5,100,500]]
    for n,rows in zip([5,100,500],counts):check('task list '+str(n)+' remains readable after large scene snapshots',isinstance(rows,list) and len(rows)<=n)
    check('scene review page deployed from current source',sha(ROOT/'web/public/character-scene-preview.html')==sha(ROOT/'web/dist/character-scene-preview.html'))
    check('old story and external character repair pages remain present',all((ROOT/'web/dist'/f).is_file() for f in ['character-story-preview.html','character-reference-repair.html']))
    ownIds=sorted(int(line.split('\t')[0]) for line in mysql('SELECT id,status FROM generation_tasks WHERE project_id='+str(p.state['projectId'])+' ORDER BY id;').splitlines() if line)
    check('this project contains only its four actual keyframe tasks',ownIds==sorted(s['Keyframe']['id'] for s in p.state['slots'].values()))
    check('regression created no business task or approval',mysql('SELECT COUNT(*) FROM generation_tasks;')==before)
    write(OUT/'delivery-checks.json',dict(status='Passed',checkedAt=datetime.datetime.now().astimezone().isoformat(),checks=checks,ownTaskIds=ownIds,totalTaskCount=before,gpuTasksCreated=0,humanApprovals=0,userReviewHold=True,contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' current delivery checks Passed; four new real keyframes, zero new videos, user review hold retained.')

if __name__=='__main__':run()

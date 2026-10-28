"""Live v2 boundary checks, plus immutable v1 replay. Does not create GPU work."""
import copy
from run import Run,PEOPLE,SLOTS,FOLDER,ROOT,read,write,media,sha

r=Run();r.access();r.preserve();checks=[]
def check(name,passed):
    checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
    write(FOLDER/'api-regression.json',dict(status='Passed' if all(c['status']=='Passed' for c in checks) else 'Failed',checks=checks))
    if not passed:raise AssertionError(name)
def reject(name,path,body,code=422,method='POST'):
    response=r.session.request(method,r.base+path,json=body,timeout=120)
    check(name,response.status_code==code)
task_ids=lambda:{t['id'] for t in r.api('/api/tasks?limit=500')}
before=task_ids();library=r.api('/api/character-library')
check('eight_directional_views_and_separate_framings',len(library['views'])==8 and 'fullBody' not in library['views'] and set(library['framings'])=={'closeUp','medium','fullBody'})
check('nine_slots_and_explicit_convention',len(library['basicSlots'])==9 and library['viewConvention']=='image-facing-v1')
check('no_automatic_approval',library['mode']=='Experimental' and library['contentReview']=='NeedReview' and library['automaticPublication'] is False)
resolutions={}
for person in PEOPLE:
    entry=r.state['people'][person['key']];version=next(v for v in library['versions'] if v['id']==entry['versionId'])
    payload=version['payload'];prefix=person['key']
    check(prefix+'_v2_complete_snapshot',payload['schema']=='character-library-v2' and payload['referencePack']=='basic-nine-v1' and payload['viewConvention']=='image-facing-v1' and len(payload['references'])==9)
    coverage=next(c['coverage'] for c in library['coverage'] if c['versionId']==version['id'])
    check(prefix+'_coverage_is_nine',coverage==dict(present=9,expected=9,complete=True,missing=[]))
    check(prefix+'_body_and_outfit_frozen',payload['bodyRatio']==person['body'] and payload['outfit']==person['outfit'])
    for view,framing in SLOTS:
        body=dict(projectId=r.state['projectId'],versionId=entry['versionId'],view=view,framing=framing,prompt='The same person breathes calmly. Locked camera.',seed=2026102901)
        result=r.api('/api/character-library/resolve',body);binding=result['binding']
        ref=next(x for x in payload['references'] if x['view']==view and x['framing']==framing)
        check(prefix+'_'+view+'_'+framing+'_exact_binding',binding['schema']==payload['schema'] and binding['versionSha256']==entry['versionSha256'] and binding['referenceId']==ref['referenceId'] and binding['view']==view and binding['framing']==framing and binding['referenceSha256']==sha(media(ref['assetPath'])))
        check(prefix+'_'+view+'_'+framing+'_frozen_prompt',payload['fixedPrompt'] in result['resolvedPrompt'] and 'Wardrobe: '+person['outfit'] in result['resolvedPrompt'] and 'Body proportions: '+person['body'] in result['resolvedPrompt'] and result['task']['parameters']['contentReview']=='NeedReview' and result['publication']=='Blocked')
        resolutions[(prefix,view,framing)]=(body,result)
    face=resolutions[(prefix,'front','closeUp')][1]['binding'];full=resolutions[(prefix,'front','fullBody')][1]['binding']
    check(prefix+'_front_close_and_full_are_distinct',face['referenceId']!=full['referenceId'] and face['referenceSha256']!=full['referenceSha256'])
    path=f"/api/character-library/{entry['characterId']}/versions";capture=entry['versionBody']
    check(prefix+'_identical_capture_deduplicates',r.api(path,capture)['id']==entry['versionId'])
    reject(prefix+'_incomplete_basic_pack',path,dict(capture,references=capture['references'][:-1]))
    reject(prefix+'_duplicate_pair',path,dict(capture,references=capture['references']+[capture['references'][0]]))
    missing=copy.deepcopy(capture);missing['references'][0].pop('framing');reject(prefix+'_capture_missing_framing',path,missing)
    reject(prefix+'_unknown_pack',path,dict(capture,referencePack='made-up-pack'))
    reject(prefix+'_oversized_body',path,dict(capture,bodyDescription='x'*2001))
    reject(prefix+'_delete_protected',f"/api/characters/{entry['characterId']}",None,409,'DELETE')

body,valid=resolutions[('linan','front','fullBody')]
for name,changes in [('missing_framing',dict(framing=None)),('invalid_framing',dict(framing='wide')),('legacy_fullbody_as_view',dict(view='fullBody')),('unsupported_back_closeup',dict(view='back',framing='closeUp')),('unsupported_side_medium',dict(view='left',framing='medium')),('traversal_direction',dict(view='../front')),('unknown_version',dict(versionId=9223372036854775806)),('empty_prompt',dict(prompt='')),('null_prompt',dict(prompt=None)),('negative_seed',dict(seed=-1))]:
    reject(name,'/api/character-library/resolve',dict(body,**changes))
for name,changes in [('missing_idempotency',{}),('short_idempotency',dict(idempotencyKey='a'))]:
    reject(name,'/api/character-library/generate',dict(body,**changes))
other=r.state['people']['zhouyan']
wrong=copy.deepcopy(r.state['people']['linan']['versionBody']);wrong['references'][0]['referenceId']=other['front-closeUp']
reject('reference_owner_cannot_change','/api/character-library/19/versions',wrong)
mutations=[
 ('different_framing',lambda t:t['parameters']['characterLibrary'].update(framing='closeUp')),
 ('missing_framing_marker',lambda t:t['parameters']['characterLibrary'].pop('framing')),
 ('legacy_schema_marker',lambda t:t['parameters']['characterLibrary'].update(schema='character-library-v1')),
 ('different_reference',lambda t:t['parameters']['characterLibrary'].update(referenceId=other['front-fullBody'])),
 ('different_hash',lambda t:t['parameters']['characterLibrary'].update(referenceSha256='0'*64)),
 ('different_version_hash',lambda t:t['parameters']['characterLibrary'].update(versionSha256='0'*64)),
 ('different_workflow',lambda t:t.update(workflowId=1)),
 ('different_first_frame',lambda t:t.update(inputImagePath=r.state['tasks']['zhouyan-front-fullBody']['path'])),
 ('positive_override',lambda t:t['parameters'].update(positive='different person')),
 ('prompt_override',lambda t:t['parameters'].update(prompt='different person')),
 ('scene_override',lambda t:t['parameters']['characterLibrary'].update(scenePrompt='unbound scene')),
 ('approved_override',lambda t:t['parameters'].update(contentReview='Passed')),
 ('production_override',lambda t:t['parameters']['characterLibrary'].update(mode='Production')),
 ('attach_episode',lambda t:t.update(episodeId=1)),
 ('null_snapshot',lambda t:t['parameters'].update(characterLibrary=None))
]
for name,mutate in mutations:
    task=copy.deepcopy(valid['task']);mutate(task)
    preflight=r.api('/api/tasks/preflight',task)
    check(name+'_preflight',not preflight['passed'] and any(c['name']=='characterLibrary' and not c['passed'] for c in preflight['checks']))
    reject(name+'_submission','/api/tasks',task)

old=read(ROOT.parent/'Data/CharacterLibrary20261026/run.json')
for original in r.state['originalVersions']:
    current=next(v for v in r.api('/api/character-library')['versions'] if v['id']==original['id'])
    check('old_version_'+str(original['id'])+'_immutable',current['sha256']==original['sha256'] and current['payload']['schema']=='character-library-v1' and all('framing' not in ref for ref in current['payload']['references']))
    legacy=r.api('/api/character-library/resolve',dict(projectId=r.state['projectId'],versionId=original['id'],view='front',prompt='Original version remains usable.',seed=1))
    check('old_version_'+str(original['id'])+'_still_resolves',legacy['binding']['schema']=='character-library-v1' and 'framing' not in legacy['binding'])
for key,entry in old['tasks'].items():
    if '-video-' not in key:continue
    replay=r.api('/api/character-library/generate',entry['body'])
    check(key+'_old_idempotent_replay',replay['id']==entry['id'] and replay['created'] is False)
check('no_gpu_tasks_created',before==task_ids());r.preserve()
print(str(len(checks))+' live API checks Passed; no GPU tasks created',flush=True)

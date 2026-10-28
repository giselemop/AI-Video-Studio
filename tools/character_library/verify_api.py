"""Live API regression; invalid calls must not create GPU tasks."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).parent))
from run_acceptance import Run, PEOPLE, FOLDER, read, write, media, sha

r=Run('http://127.0.0.1:18080');r.access();r.preserve();checks=[]
def check(name, condition):
    checks.append(dict(name=name,status='Passed' if condition else 'Failed'))
    write(FOLDER/'api-regression.json',dict(checks=checks,status='Passed' if all(c['status']=='Passed' for c in checks) else 'Failed'))
    if not condition:raise AssertionError(name)
def reject(name,path,body,code=422,method='POST'):
    response=r.session.request(method,r.base+path,json=body,timeout=120)
    check(name,response.status_code==code)
    return response
person=r.state['people']['linan'];second=r.state['people']['zhouyan']
body=dict(projectId=r.state['projectId'],versionId=person['versionId'],view='front',prompt='The same person blinks naturally. Fixed camera.',seed=2026102671)
resolved=r.api('/api/character-library/resolve',body)
check('resolve_exact_version',resolved['binding']['versionId']==person['versionId'] and resolved['binding']['versionSha256']==person['versionSha256'])
check('resolve_source_hash',sha(media(resolved['binding']['referenceAssetPath']))==resolved['binding']['referenceSha256'])
check('fixed_character_prompt_is_applied',PEOPLE[0]['fixedPrompt'] in resolved['resolvedPrompt'])
check('wardrobe_is_applied','Wardrobe: '+PEOPLE[0]['clothes'] in resolved['resolvedPrompt'])
check('explicit_experiment_not_approval',resolved['contentReview']=='NeedReview' and resolved['publication']=='Blocked' and resolved['binding']['mode']=='Experimental')
check('pinned_workflow',resolved['task']['workflowId']==resolved['binding']['workflowId'])
task_ids=lambda:{t['id'] for t in r.api('/api/tasks?limit=500')}
before=task_ids()
for name,changes in [('unknown_version',dict(versionId=9223372036854775806)),('unknown_view',dict(view='back')),('unknown_project',dict(projectId=9223372036854775806)),('empty_prompt',dict(prompt='')),('null_prompt',dict(prompt=None)),('oversized_prompt',dict(prompt='a'*4001)),('negative_seed',dict(seed=-1)),('view_path',dict(view='../front'))]:
    invalid=dict(body);invalid.update(changes);reject(name,'/api/character-library/resolve',invalid)
reject('missing_idempotency','/api/character-library/generate',body)
reject('null_idempotency','/api/character-library/generate',dict(body,idempotencyKey=None))
reject('short_idempotency','/api/character-library/generate',dict(body,idempotencyKey='a'))
path=f"/api/character-library/{person['characterId']}/versions"
capture=person['versionBody']
reject('wrong_reference_owner',path,dict(capture,references=[dict(referenceId=second['frontReferenceId'],view='front')]))
reject('no_references',path,dict(capture,references=[]))
reject('null_references',path,dict(capture,references=None))
reject('duplicate_view',path,dict(capture,references=[dict(referenceId=person['frontReferenceId'],view='front')]*2))
reject('unknown_workflow',path,dict(capture,workflowId=1))
reject('unsupported_profile',path,dict(capture,profile='native1080'))
check('capture_same_content_deduplicates',r.api(path,capture)['id']==person['versionId'])
reject('library_character_delete_protected',f"/api/characters/{person['characterId']}",None,409,'DELETE')

valid=resolved['task']
mutations=[
    ('swapped_first_frame',lambda task:task.update(inputImagePath=r.state['tasks']['zhouyan-master']['path'])),
    ('path_traversal',lambda task:task.update(inputImagePath='../Models/x.png')),
    ('wrong_task_workflow',lambda task:task.update(workflowId=1)),
    ('tampered_identity',lambda task:task['parameters']['characterLibrary'].update(characterId=second['characterId'])),
    ('tampered_version_hash',lambda task:task['parameters']['characterLibrary'].update(versionSha256='0'*64)),
    ('tampered_reference_hash',lambda task:task['parameters']['characterLibrary'].update(referenceSha256='0'*64)),
    ('tampered_workflow_hash',lambda task:task['parameters']['characterLibrary'].update(workflowSha256='0'*64)),
    ('tampered_scene_prompt',lambda task:task['parameters']['characterLibrary'].update(scenePrompt='Different unbound content')),
    ('tampered_fixed_prompt',lambda task:task['parameters'].update(prompt='a different person')),
    ('positive_prompt_override',lambda task:task['parameters'].update(positive='a different person')),
    ('production_flag',lambda task:task['parameters']['characterLibrary'].update(mode='Production')),
    ('pretend_content_approval',lambda task:task['parameters'].update(contentReview='Passed')),
    ('attach_formal_episode',lambda task:task.update(episodeId=1)),
    ('null_library_snapshot',lambda task:task['parameters'].update(characterLibrary=None)),
]
for name,mutate in mutations:
    task=copy.deepcopy(valid);mutate(task)
    response=r.api('/api/tasks/preflight',task)
    check(name+'_preflight',not response['passed'] and any(c['name']=='characterLibrary' and not c['passed'] for c in response['checks']))
    reject(name+'_submission','/api/tasks',task)
check('negative_calls_create_no_tasks',before==task_ids())

# A draft edit must not change a previously captured version or resolve result.
original={k:v for k,v in PEOPLE[0].items() if k!='key'}
original.update(name='林安（人物库试用）',projectId=r.state['projectId'],voiceId='',voiceSpeed=1,voicePitch=0)
try:
    r.api(f"/api/characters/{person['characterId']}",dict(original,fixedPrompt=original['fixedPrompt']+' Draft-only edit.'),method='PUT')
    after=r.api('/api/character-library/resolve',body)
    check('draft_edit_does_not_change_snapshot',after['version']['sha256']==resolved['version']['sha256'] and after['resolvedPrompt']==resolved['resolvedPrompt'])
finally:r.api(f"/api/characters/{person['characterId']}",original,method='PUT')
new_version=r.api(path,dict(capture,label='阅读室日常装 · 版本留存'))
check('changed_version_is_append_only',new_version['id']!=person['versionId'] and new_version['version']>person['version'])
check('old_version_still_resolves',r.api('/api/character-library/resolve',body)['binding']==resolved['binding'])
left=r.api('/api/character-library/resolve',dict(body,view='threeQuarterRight'))
check('view_selects_distinct_reference',left['binding']['referenceId']!=resolved['binding']['referenceId'] and left['binding']['referenceSha256']!=resolved['binding']['referenceSha256'])
all_versions=r.api('/api/character-library')['versions']
check('two_fixed_characters_present',all(any(v['payload']['characterId']==r.state['people'][p['key']]['characterId'] for v in all_versions) for p in PEOPLE))
other_project=next((p['id'] for p in r.api('/api/projects') if p['id']!=r.state['projectId']),None)
if other_project:
    cross=r.api('/api/character-library/resolve',dict(body,projectId=other_project))
    check('cross_project_resolution_uses_same_library_version',cross['binding']==resolved['binding'] and cross['task']['projectId']==other_project)
check('negative_calls_and_version_edits_create_no_tasks',before==task_ids())

if '--source-drift' in sys.argv:
    # Test only the newly uploaded pilot reference, and only while both queues
    # are idle. Original generation artifacts and model/workflow files are untouched.
    queue=r.session.get('http://127.0.0.1:8188/queue',timeout=10).json()
    if queue['queue_running'] or queue['queue_pending'] or r.api('/api/minimax/local/status')['queue']['activeTasks']:
        raise RuntimeError('Physical source-drift test requires the completed, idle pilot')
    source=media(resolved['binding']['referenceAssetPath'])
    if 'Artifacts' in source.parts:raise RuntimeError('Never mutate final generation artifacts for a drift test')
    original_bytes=source.read_bytes();original_stat=source.stat()
    try:
        source.write_bytes(original_bytes+b'\ncharacter-library-drift-test')
        reject('actual_source_file_drift_is_rejected','/api/character-library/resolve',body)
    finally:
        source.write_bytes(original_bytes)
        os.utime(source,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
    check('source_restored_exactly',sha(source)==resolved['binding']['referenceSha256'])
    check('restored_version_resolves',r.api('/api/character-library/resolve',body)['binding']==resolved['binding'])
    for key,record in r.state['tasks'].items():
        if '-video-' not in key:continue
        replay=r.api('/api/character-library/generate',record['body'])
        check(key+'_completed_replay_is_same_task',replay['id']==record['id'] and replay['created'] is False)
        invalid=dict(record['body'],prompt=record['body']['prompt']+' Changed request.')
        reject(key+'_idempotency_conflict','/api/character-library/generate',invalid,409)
    check('drift_and_replay_tests_create_no_tasks',before==task_ids())
r.preserve()
print(f'{len(checks)} live API checks Passed; no new GPU task from invalid calls',flush=True)

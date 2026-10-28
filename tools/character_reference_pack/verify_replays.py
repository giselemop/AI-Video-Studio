"""Post-execution v2 replay/conflict checks; must never add a task."""
from run import Run,PEOPLE,FOLDER,read,write

r=Run();r.access();r.preserve();report=read(FOLDER/'api-regression.json')
if report['status']!='Passed':raise RuntimeError('Complete the API boundary regression first')
checks={item['name']:item for item in report['checks']}
def check(name,passed):
    checks[name]=dict(name=name,status='Passed' if passed else 'Failed')
    write(FOLDER/'api-regression.json',dict(status='Passed' if all(item['status']=='Passed' for item in checks.values()) else 'Failed',checks=list(checks.values())))
    if not passed:raise AssertionError(name)
task_ids=lambda:{task['id'] for task in r.api('/api/tasks?limit=500')}
before=task_ids()
for person in PEOPLE:
    entry=r.state['tasks'][person['key']+'-fullBody-video']
    if entry['status']!='Succeeded':raise RuntimeError('Video must finish before replay acceptance')
    same=r.api('/api/character-library/generate',entry['body'])
    check(person['key']+'_v2_completed_replay_is_same_task',same['id']==entry['id'] and same['created'] is False)
    for field,value in [('prompt',entry['body']['prompt']+' A different action.'),('framing','closeUp')]:
        changed=dict(entry['body']);changed[field]=value
        response=r.session.post(r.base+'/api/character-library/generate',json=changed,timeout=120)
        check(person['key']+'_same_key_different_'+field+'_conflicts',response.status_code==409)
check('v2_completed_replays_create_no_new_tasks',before==task_ids())
print(str(len(checks))+' cumulative live API checks Passed',flush=True)

"""Resolve-only tests exercise the real deployed prompt builder without generation."""
import uuid
from run import Repair
from inventory import OUT, write

if __name__=='__main__':
 r=Repair();checks=[];before=r.api('/api/tasks?limit=500')
 for cid in range(19,26):
    body=dict(characterId=cid,kind='identity',view='front',framing='closeUp',seed=2026102701,idempotencyKey='prompt-resolve-test:'+str(uuid.uuid4()))
    result=r.api('/api/character-workshop/resolve',body);p=result['task']['parameters']
    assert p['promptPolicy']=='character-anatomy-v2' and p['width']==1536 and p['height']==864 and 'ONE anatomically normal head' in p['positive']
    assert 'Exactly two legs' not in p['positive'] and 'inputSlots' not in p
    checks.append(dict(name='real identity prompt resolve '+str(cid),status='Passed'))
 for changes in [dict(view='unknown'),dict(seed=-1),dict(view='back',framing='closeUp'),dict(kind='slot',view='right',framing='fullBody')]:
    body=dict(characterId=21,kind='identity',view='front',framing='closeUp',seed=1,idempotencyKey='prompt-reject-test:'+str(uuid.uuid4()));body.update(changes)
    response=r.s.post('http://127.0.0.1:18080/api/character-workshop/resolve',json=body,timeout=60)
    assert response.status_code==422,(changes,response.status_code,response.text)
    checks.append(dict(name='invalid input or unapproved anchors rejected '+str(changes),status='Passed'))
 after=r.api('/api/tasks?limit=500');assert {x['id'] for x in before}=={x['id'] for x in after}
 checks.append(dict(name='resolve and rejection tests create zero generation tasks',status='Passed'))
 write(OUT/'api-tests.json',dict(status='Passed',checks=checks,newGpuTasks=0));print('REAL_PROMPT_API_TESTS_PASSED',len(checks))

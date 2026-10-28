"""Offline submission guards; no real task or inference is created."""
import json
from pathlib import Path
import tempfile
import run

class Stub:
    def __init__(self,state):self.state=state;self.posts=0;self.polls=0
    def api(self,*args,**kwargs):self.posts+=1;raise AssertionError('Unexpected submission')
    def poll(self,task):self.polls+=1;return dict(task=dict(id=task,status='Succeeded'),results=[])

if __name__=='__main__':
    body=dict(projectId=33,taskType='ImageToVideo')
    checks=[]
    with tempfile.TemporaryDirectory(dir=run.FOLDER,prefix='guard-') as folder:
        old=run.FOLDER;run.FOLDER=Path(folder)
        known=Stub(dict(checkTaskId=777,checkTaskIdInput=body))
        assert run.once(known,'checkTaskId','/api/tasks',body)['task']['id']==777
        assert known.posts==0 and known.polls==1
        checks.append('recorded ID is polled without submitting')
        pending=Stub(dict(checkTaskIdSubmissionStarted=True,checkTaskIdInput=body))
        try:run.once(pending,'checkTaskId','/api/tasks',body)
        except RuntimeError as e:assert 'unresolved' in str(e)
        else:raise AssertionError('Unknown submission was repeated')
        assert pending.posts==pending.polls==0
        checks.append('uncertain submission is stopped')
        changed=Stub(dict(checkTaskId=777,checkTaskIdInput=body))
        try:run.once(changed,'checkTaskId','/api/tasks',dict(body,projectId=999))
        except RuntimeError as e:assert 'Frozen input changed' in str(e)
        else:raise AssertionError('Frozen input was changed')
        assert changed.posts==changed.polls==0
        checks.append('changed frozen input is stopped')
        run.FOLDER=old
    (run.FOLDER/'guard-verification.json').write_text(json.dumps(dict(status='Passed',kind='Offline, no generation or task creation',checks=checks),indent=2),encoding='utf-8')
    print('3 offline submission guards: Passed')

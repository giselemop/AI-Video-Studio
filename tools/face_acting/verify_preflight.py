"""Read-only admission checks for the four newly pinned local workflows."""
import copy
from run import API,FOLDER,Run,read,write

run=Run(API,FOLDER/'run.json');run.access()
def task_ids():return sorted(t['id'] for t in run.api('/api/tasks?limit=1000') if t.get('projectId')==run.state['projectId'])
before=task_ids();cases=[]
ref=copy.deepcopy(run.state['femaleRef2Attempt3TaskIdInput'])
video=copy.deepcopy(run.state['shot1Attempt1TaskIdInput'])
def check(name,body,expected):
    response=run.api('/api/tasks/preflight',body,timeout=600)
    if response['passed']!=expected:raise RuntimeError(name+': '+str(response['issues']))
    cases.append(dict(name=name,passed=True,expected=expected,issues=response['issues']))
check('Pinned reference workflow and frozen local input slots',ref,True)
check('Pinned revised audio-driven workflow',video,True)
body=copy.deepcopy(ref);body['parameters']['width']=1024;check('Reject unregistered reference geometry',body,False)
body=copy.deepcopy(ref);body['parameters']['inputSlots'].pop('editMask');check('Reject missing expression mask',body,False)
body=copy.deepcopy(ref);body['parameters']['workflowVersion']='not-a-registered-route';check('Reject workflow version mismatch',body,False)
body=copy.deepcopy(video);body['parameters']['fps']=24;check('Reject native audio/video rate drift',body,False)
body=copy.deepcopy(video);body['parameters']['frames']=58;check('Reject exact native frame count drift',body,False)
body=copy.deepcopy(video);body['parameters']['inputSlots'].pop('speakerAudio');check('Reject missing unchanged speaker audio',body,False)
after=task_ids()
if before!=after:raise RuntimeError('Read-only preflight created tasks')
write(FOLDER/'preflight-verification.json',dict(status='Passed',cases=cases,projectTaskIdsBefore=before,projectTaskIdsAfter=after,newTasksCreated=0))
print(f'Passed: {len(cases)} real read-only preflight cases, no new task',flush=True)

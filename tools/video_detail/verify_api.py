"""Read-only actual preflight regression; one rejected POST must create no task."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/minimax'))
from run_local_acceptance import Acceptance

FOLDER = ROOT.parent/'Data/SeedVR2Enhancement20261022'
run = Acceptance('http://127.0.0.1:18080', FOLDER/'run.json')
run.access()
state = run.state
base = copy.deepcopy(state['sampleRestoreTaskIdInput'])
base['parameters']['engineVersion'] = run.api('/api/video-restore/status')['engineVersion']
checks = []


def check(name, body, expected):
    result = run.api('/api/tasks/preflight',body)
    if result['passed'] != expected: raise RuntimeError('Unexpected preflight: '+name)
    checks.append(dict(name=name,status='Passed',submissionExpected=expected,issues=result['issues']))


check('Valid bound GPU preview',base,True)
for name, key, value in [('CPU resource','resourceClass','CPU'),('Formal association','productionRunId',1)]:
    body=copy.deepcopy(base);body[key]=value;check(name,body,False)
for name,key,value in [('Engine drift','engineVersion','changed'),('Source hash drift','sourceSha256','0'*64),
    ('Excessive strength','strength',1.01),('String strength','strength','0.65'),('Boolean strength','strength',True),
    ('Null strength','strength',None),('Duplicate cuts','cutFrames',[9,9]),('Descending cuts','cutFrames',[12,9]),
    ('Out of range cut','cutFrames',[49]),('Non-integer cut','cutFrames',[1.5]),('Non-array cuts','cutFrames','9'),
    ('External source','input','C:/Windows/win.ini')]:
    body=copy.deepcopy(base);body['parameters'][key]=value;check(name,body,False)
export=copy.deepcopy(state['exportTaskIdInput'])
check('Explicit one-pass export',export,True)
for name,key,value in [('String FPS with trim','targetFps','24'),('Fractional trim','trimStartSeconds',.01),
    ('Missing explicit dimensions','targetWidth',None),('Odd dimensions','targetWidth',1919),('String singlePass','singlePass','true')]:
    body=copy.deepcopy(export);body['parameters'][key]=value;check(name,body,False)
if state.get('fullFinalTaskIdInput'):
    remux=copy.deepcopy(state['fullFinalTaskIdInput'])
    check('Bound lossless audio remux',remux,True)
    for name,key,value in [('Remux video drift','videoSha256','0'*64),('Remux audio drift','audioStreamCopySha256','0'*64),
        ('Remux invalid source','audioStreamCopyFrom','C:/Windows/win.ini'),('Remux resampling forbidden','targetFps',60),
        ('Remux cannot combine encoding','singlePass',True),('Remux cannot combine gain','originalAudioVolume',0),
        ('Remux cannot trim audio','trimStartSeconds',1)]:
        body=copy.deepcopy(remux);body['parameters'][key]=value;check(name,body,False)
before=[t['id'] for t in run.api('/api/dashboard')['recentTasks']]
bad=copy.deepcopy(base);bad['parameters']['strength']=2
response=run.session.post(run.base+'/api/tasks',json=bad,headers={'Origin':run.base},timeout=30)
if response.status_code != 422: raise RuntimeError(f'Invalid POST returned unexpected HTTP {response.status_code}')
after=[t['id'] for t in run.api('/api/dashboard')['recentTasks']]
if before!=after: raise RuntimeError('Rejected input changed task history')
checks.append(dict(name='Rejected POST creates no row',status='Passed',httpStatus=422))
(FOLDER/'api-regression.json').write_text(json.dumps(dict(status='Passed',checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Video detail actual API: {len(checks)} Passed; no task submitted')

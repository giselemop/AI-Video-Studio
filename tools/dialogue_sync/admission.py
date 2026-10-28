"""Real preflight compatibility and invalid POST rejection; create no tasks."""
from run import *
import uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
manifest=FOLDER/'wideMerge-composition.json';original=read(manifest)
body=copy.deepcopy(s.get('wideInitialMergeTaskIdInput',s['wideMergeTaskIdInput']));body['stage']='Sync-Admission-Only'
before=sorted(x['id'] for x in r.api('/api/tasks?limit=500'));rows=[]
for label,value in [('new57',body),('legacy151',dict(projectId=s['projectId'],taskType='DialogueComposite',resourceClass='CPU',maxRetries=0,stage='Legacy-Read-Only-Preflight',parameters=dict(manifest='DialogueVisual20261025/wide-merge-v1.json',manifestSha256=sha(DATA/'DialogueVisual20261025/wide-merge-v1.json'),engineVersion=sha(ROOT/'tools/dialogue_visual/compose.py'))))]:
    pre=r.api('/api/tasks/preflight',value,timeout=180);write(FOLDER/('admission-valid-'+label+'.json'),pre)
    if not pre['passed']:raise RuntimeError('Valid profile compatibility failed: '+label)
    rows.append(dict(name=label,status='Passed',preflightOnly=True))
cases=[]
for label,key,value in [('unknown-profile','compositionProfile','../arbitrary.py'),('non-string-profile','compositionProfile',7),('wrong-engine','engineVersion','0'*64),('wrong-manifest-sha','manifestSha256','0'*64)]:
    request=copy.deepcopy(body);request['parameters'][key]=value;cases.append((label,request))
for label,change in [('wrong-frames',lambda m:m.update(frames=151)),('wrong-fps',lambda m:m.update(fps=24)),
                      ('old-manifest-profile',lambda m:m.update(profile='dialogue-compose-v1')),
                      ('swapped-person-receipts',lambda m:m['files'].update(leftReceipt=copy.deepcopy(m['files']['rightReceipt']))),
                      ('mask-sha-drift',lambda m:m['files']['leftMask'].update(sha256='0'*64))]:
    m=copy.deepcopy(original);change(m);p=FOLDER/('invalid-'+label+'.json');write(p,m)
    request=copy.deepcopy(body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));cases.append((label,request))
request=copy.deepcopy(body);request['episodeId']=1;cases.append(('formal-parent',request))
request=copy.deepcopy(body);request['resourceClass']='GPU';cases.append(('cpu-profile-on-gpu',request))
# Legacy profile must retain its151-frame boundary.
m=read(DATA/'DialogueVisual20261025/wide-merge-v1.json');m['frames']=57;p=FOLDER/'invalid-legacy57.json';write(p,m)
request=copy.deepcopy(body);request['parameters']=dict(manifest=rel(p),manifestSha256=sha(p),engineVersion=sha(ROOT/'tools/dialogue_visual/compose.py'));cases.append(('legacy57-rejected',request))
for label,request in cases:
    response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'sync-invalid-'+uuid.uuid4().hex},timeout=180)
    rows.append(dict(name=label,http=response.status_code,status='Passed' if response.status_code==422 else 'Failed'))
    if response.status_code!=422:raise RuntimeError('Invalid request was not rejected; inspect existing tasks before any retry')
after=sorted(x['id'] for x in r.api('/api/tasks?limit=500'))
if before!=after:raise RuntimeError('Admission test unexpectedly changed task set')
write(FOLDER/'api-admission-checks.json',dict(status='Passed',checks=rows,invalidPostCount=len(cases),newTaskSubmissions=0,taskSetUnchanged=True))
print('Passed: new57/legacy151 valid preflights and '+str(len(cases))+' actual invalid POST rejections; zero new tasks')

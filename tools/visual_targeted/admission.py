"""Invalid real POSTs must be rejected before any task row is created."""
from run import *
import copy,uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve()
before=sorted(x['id'] for x in r.api('/api/tasks?limit=500'))
cases=[]
for kind in ['blink','detail']:
    original=r.state[kind+'TaskIdInput']
    for name,value in [('engineVersion','0'*64),('manifestSha256','0'*64),('manifest','../outside.json')]:
        body=copy.deepcopy(original);body['parameters'][name]=value;cases.append((kind+'-'+name,body))
for value in ['unknown',123]:
    body=copy.deepcopy(r.state['blinkTaskIdInput']);body['parameters']['repairProfile']=value;cases.append(('blink-profile-'+str(value),body))
folder=FOLDER/'admission';folder.mkdir(exist_ok=True)
for kind,field,value in [('blink','eyeResidualGain',2),('blink','sourceSha256','0'*64),('detail','strength',.99),('detail','maskEngineSha256','0'*64),('detail','profile','unknown')]:
    body=copy.deepcopy(r.state[kind+'TaskIdInput']);m=read(media(body['parameters']['manifest']));m[field]=value
    p=folder/(kind+'-'+field+'.json');write(p,m);body['parameters']['manifest']=rel(p);body['parameters']['manifestSha256']=sha(p);cases.append((kind+'-'+field,body))
rows=[]
for name,body in cases:
    response=r.session.post(r.base+'/api/tasks',json=body,headers={'Origin':r.base,'Idempotency-Key':'targeted-invalid-'+uuid.uuid4().hex},timeout=90)
    rows.append(dict(name=name,status='Passed' if response.status_code==422 else 'Failed',http=response.status_code))
    if response.status_code!=422:break
after=sorted(x['id'] for x in r.api('/api/tasks?limit=500'))
passed=len(rows)==len(cases) and all(x['status']=='Passed' for x in rows) and before==after
write(FOLDER/'api-admission-checks.json',dict(status='Passed' if passed else 'Failed',checks=rows,taskSetUnchanged=before==after,
    validPreflightsAlreadyPassed=['blinkTaskId-preflight.json','detailTaskId-preflight.json'],newTaskSubmissions=0 if before==after else 'Investigate'))
if not passed:raise RuntimeError('Invalid input admission checks failed; inspect report before more work')
print(f'Passed: {len(rows)} real invalid POSTs rejected; task set unchanged')

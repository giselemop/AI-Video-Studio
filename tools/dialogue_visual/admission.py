"""Actual API rejection checks; no valid new generation is submitted."""
from run import *
import copy,uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve()
before=sorted(x['id'] for x in r.api('/api/tasks?limit=500'));cases=[];folder=FOLDER/'admission';folder.mkdir(exist_ok=True)
for field in ['femaleA1TaskIdInput','wideMergeTaskIdInput']:
    original=r.state[field]
    for name,value in [('engineVersion','0'*64),('manifestSha256','0'*64),('manifest','../outside.json')]:
        body=copy.deepcopy(original);body['parameters'][name]=value;cases.append((field+'-'+name,body))
for name,value in [('faceDirection','unknown'),('faceDirection',123),('durationSeconds',.8),('durationSeconds',8),('eyeResidualGain',3)]:
    body=copy.deepcopy(r.state['femaleA1TaskIdInput']);m=read(media(body['parameters']['manifest']));m[name]=value
    p=folder/(name+'-'+str(value)+'.json');write(p,m);body['parameters']['manifest']=rel(p);body['parameters']['manifestSha256']=sha(p);cases.append(('actor-'+name+'-'+str(value),body))
for name in ['wrong-role','wrong-mask','wrong-frames','unknown-phase']:
    body=copy.deepcopy(r.state['wideMergeTaskIdInput']);m=read(media(body['parameters']['manifest']))
    if name=='wrong-role':m['files']['leftReceipt'],m['files']['rightReceipt']=m['files']['rightReceipt'],m['files']['leftReceipt']
    elif name=='wrong-mask':m['files']['leftMask']['sha256']='0'*64
    elif name=='wrong-frames':m['frames']=150
    else:m['phase']='unknown'
    p=folder/(name+'.json');write(p,m);body['parameters']['manifest']=rel(p);body['parameters']['manifestSha256']=sha(p);cases.append((name,body))
rows=[]
for name,body in cases:
    response=r.session.post(r.base+'/api/tasks',json=body,headers={'Origin':r.base,'Idempotency-Key':'dialogue-invalid-'+uuid.uuid4().hex},timeout=90)
    rows.append(dict(name=name,http=response.status_code,status='Passed' if response.status_code==422 else 'Failed'))
    if response.status_code!=422:break
after=sorted(x['id'] for x in r.api('/api/tasks?limit=500'))
passed=len(rows)==len(cases) and before==after and all(x['status']=='Passed' for x in rows)
write(FOLDER/'api-admission-checks.json',dict(status='Passed' if passed else 'Failed',checks=rows,taskSetUnchanged=before==after,newTasks=0 if before==after else 'Investigate',gpuSubmissions=0))
if not passed:raise RuntimeError('Admission checks failed; inspect before more work')
print(f'Passed: {len(rows)} actual invalid POSTs; no tasks created')

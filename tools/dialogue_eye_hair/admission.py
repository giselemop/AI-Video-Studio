"""Actual invalid requests and preserved profile preflights; no valid submissions."""
from run import *
import uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();s=r.state;body=copy.deepcopy(s['wideMergeTaskIdInput']);manifest=read(FOLDER/'guard-merge.json');rows=[]
snapshot=lambda:{t['id'] for t in r.api('/api/tasks?limit=500')}
before=snapshot()
for name,key,value in [('phase','phase','detail'),('frames','frames',57),('mouth-roi','mouthEllipse',[360,150,26,23]),('policy','femalePolicy','all-face'),('cue-timing','speakingSeconds',[0,6])]:
    m=copy.deepcopy(manifest);m[key]=value;p=FOLDER/('invalid-'+name+'.json');write(p,m);request=copy.deepcopy(body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'eye-hair-invalid-'+uuid.uuid4().hex},timeout=180)
    if response.status_code!=422:raise RuntimeError('Invalid guard admitted '+name)
    rows.append(dict(name=name,status='Passed',http=422))
for name,path,key in [('stable-old','DialogueStable20261025/run.json','wideMergeTaskIdInput'),('full-old','DialogueSyncFull20261025/run.json','wideMergeTaskIdInput')]:
    pre=r.api('/api/tasks/preflight',read(DATA/path)[key],timeout=180)
    if not pre['passed']:raise RuntimeError('Preserved profile preflight failed')
    rows.append(dict(name=name,status='Passed',preflightOnly=True))
if snapshot()!=before:raise RuntimeError('Admission test created task')
write(FOLDER/'admission-checks.json',dict(status='Passed',checks=rows,newTasks=0));print('Passed:5 guard rejections,2 preserved-profile preflights,no new tasks')

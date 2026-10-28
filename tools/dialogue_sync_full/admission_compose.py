"""Validate actual full composition inputs and reject boundary violations without jobs."""
from run import *
import uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state;rows=[]
before=r.api('/api/dashboard')
for key in ['wideMerge','detail1','detail2','detail3']:
    request=copy.deepcopy(s[key+'TaskIdInput']);pre=r.api('/api/tasks/preflight',request,timeout=180);write(FOLDER/('valid-full-compose-'+key+'.json'),pre)
    if not pre['passed']:raise RuntimeError('Valid full composition preflight failed: '+key+' '+str(pre['issues']))
    rows.append(dict(name=key,status='Passed',preflightOnly=True))
base_body=copy.deepcopy(s['wideMergeTaskIdInput']);manifest=read(media(base_body['parameters']['manifest']));cases=[]
changes=[('short-frame-count',lambda m:m.update(frames=57)),('wrong-fps',lambda m:m.update(fps=24)),('wrong-geometry',lambda m:m.update(width=1280)),('wrong-phase',lambda m:m.update(phase='unknown')),('source-sha',lambda m:m['files']['source'].update(sha256='0'*64)),('source-outside',lambda m:m['files']['source'].update(path=r'C:\outside.png')),('swapped-role-receipt',lambda m:m['files'].update(leftReceipt=m['files']['rightReceipt'])),('mask-sha',lambda m:m['files']['leftMask'].update(sha256='0'*64))]
for name,change in changes:
    m=copy.deepcopy(manifest);change(m);p=FOLDER/('invalid-compose-'+name+'.json');write(p,m);request=copy.deepcopy(base_body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));cases.append((name,request))
for name,key,value in [('formal-parent','episodeId',1),('compose-on-gpu','resourceClass','GPU')]:
    request=copy.deepcopy(base_body);request[key]=value;cases.append((name,request))
for name,key,value in [('engine-sha','engineVersion','0'*64),('manifest-sha','manifestSha256','0'*64),('unknown-profile','compositionProfile','unknown'),('nonstring-profile','compositionProfile',8)]:
    request=copy.deepcopy(base_body);request['parameters'][key]=value;cases.append((name,request))
for name,request in cases:
    response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'full-compose-invalid-'+uuid.uuid4().hex},timeout=180)
    if response.status_code!=422:raise RuntimeError('Invalid composition not rejected: '+name+' HTTP'+str(response.status_code))
    rows.append(dict(name=name,status='Passed',http=422))
after=r.api('/api/dashboard')
if [t['id'] for t in before['recentTasks']]!=[t['id'] for t in after['recentTasks']]:raise RuntimeError('Composition checks changed newest task set')
write(FOLDER/'composition-admission-checks.json',dict(status='Passed',checks=rows,invalidPostCount=len(cases),newTaskSubmissions=0,recentTaskSetUnchanged=True))
print('Passed: real full merge/detail preflights and14 invalid POST rejections, zero tasks')

"""Actual hybrid boundary rejection and prior portrait/composition compatibility."""
from run import *
import uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
body=copy.deepcopy(s['wideHybridFemaleTaskIdInput']);body['stage']='Hybrid-Admission-Only';manifest=read(media(body['parameters']['manifest']))
before=sorted(x['id'] for x in r.api('/api/tasks?limit=500'));rows=[]
for name,request in [('hybrid57-preflight',body),('old-dialogue-blink-preflight',s['closeFemaleTaskIdInput']),('hybrid-compose57-preflight',s['wideHybridMergeTaskIdInput'])]:
    pre=r.api('/api/tasks/preflight',request,timeout=180);write(FOLDER/('valid-'+name+'.json'),pre)
    if not pre['passed']:raise RuntimeError('Valid compatibility failed: '+name)
    rows.append(dict(name=name,status='Passed',preflightOnly=True))
cases=[]
for name,change in [('pose-sha',lambda m:m.update(poseSha256='0'*64)),('pose-outside',lambda m:m.update(posePath=r'C:\outside.mp4')),
                    ('pose-wrong-frames',lambda m:m.update(posePath=str(media(s['closeDriverPath'])),poseSha256=s['closeDriverSha256'])),
                    ('direction',lambda m:m.update(faceDirection='large-small')),('duration',lambda m:m.update(durationSeconds=2)),
                    ('multiplier',lambda m:m.update(drivingMultiplier=.7)),('region',lambda m:m.update(animationRegion='exp')),
                    ('source-sha',lambda m:m.update(sourceSha256='0'*64))]:
    m=copy.deepcopy(manifest);change(m);p=FOLDER/('invalid-hybrid-'+name+'.json');write(p,m)
    request=copy.deepcopy(body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));cases.append((name,request))
request=copy.deepcopy(body);request['episodeId']=1;cases.append(('formal-parent',request))
request=copy.deepcopy(body);request['resourceClass']='CPU';cases.append(('portrait-on-cpu',request))
request=copy.deepcopy(body);request['parameters']['engineVersion']='0'*64;cases.append(('engine-sha',request))
for name,request in cases:
    response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'hybrid-invalid-'+uuid.uuid4().hex},timeout=180)
    rows.append(dict(name=name,http=response.status_code,status='Passed' if response.status_code==422 else 'Failed'))
    if response.status_code!=422:raise RuntimeError('Invalid hybrid request not rejected; inspect existing task set')
after=sorted(x['id'] for x in r.api('/api/tasks?limit=500'))
if before!=after:raise RuntimeError('Hybrid tests created tasks')
write(FOLDER/'hybrid-api-checks.json',dict(status='Passed',checks=rows,invalidPostCount=len(cases),newTaskSubmissions=0,taskSetUnchanged=True))
print('Passed: hybrid/old portrait/short compose preflights and '+str(len(cases))+' invalid POST rejections; zero new tasks')

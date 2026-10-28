"""Live API profile compatibility/rejection checks; never submit a valid generation."""
from run import *
import uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
pilot=read(DATA/'DialogueSync20261025/run.json');rows=[]
pose=s['inputs']['pose'];source=s['inputs']['wideReference']
manifest=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(pose)),drivingSha256=sha(media(pose)),posePath=str(media(pose)),poseSha256=sha(media(pose)),durationSeconds=151/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,repairProfile='dialogue-hybrid-full-v1',eyeResidualGain=1,faceDirection='left-right',driverOrigin='Existing local media for CPU preflight only, not a fresh render or quality result',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
path=FOLDER/'admission-full151.json';write(path,manifest)
body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='SyncFull-Admission-Only',parameters=dict(manifest=rel(path),manifestSha256=sha(path),repairProfile='dialogue-hybrid-full-v1',engineVersion=sha(ROOT/'tools/dialogue_sync_full/hybrid.py')))
before=r.api('/api/dashboard');snapshot=lambda x:dict(counts=x['counts'],tasks=[(t['id'],t['status']) for t in x['recentTasks']])
for name,request in [('full151-preflight',body),('accepted-short57-preflight',pilot['wideHybridFemaleTaskIdInput']),('old-dialogue-blink-preflight',pilot['closeFemaleTaskIdInput']),('old-short-compose-preflight',pilot['wideHybridMergeTaskIdInput'])]:
    pre=r.api('/api/tasks/preflight',request,timeout=180);write(FOLDER/('valid-'+name+'.json'),pre)
    if not pre['passed']:raise RuntimeError('Valid profile compatibility failed: '+name+' '+str(pre['issues']))
    rows.append(dict(name=name,status='Passed',preflightOnly=True))
cases=[]
for name,change in [('pose-sha',lambda m:m.update(poseSha256='0'*64)),('pose-outside',lambda m:m.update(posePath=r'C:\outside.mp4')),('pose-short',lambda m:m.update(posePath=str(media(pilot['widePosePath'])),poseSha256=pilot['widePoseSha256'])),('direction',lambda m:m.update(faceDirection='large-small')),('duration',lambda m:m.update(durationSeconds=57/25)),('multiplier',lambda m:m.update(drivingMultiplier=.7)),('region',lambda m:m.update(animationRegion='exp')),('source-sha',lambda m:m.update(sourceSha256='0'*64))]:
    m=copy.deepcopy(manifest);change(m);p=FOLDER/('invalid-full-'+name+'.json');write(p,m);request=copy.deepcopy(body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));cases.append((name,request))
for name,key,value in [('formal-parent','episodeId',1),('portrait-on-cpu','resourceClass','CPU')]:
    request=copy.deepcopy(body);request[key]=value;cases.append((name,request))
for name,key,value in [('engine-sha','engineVersion','0'*64),('unknown-profile','repairProfile','unknown'),('nonstring-profile','repairProfile',9)]:
    request=copy.deepcopy(body);request['parameters'][key]=value;cases.append((name,request))
for name,request in cases:
    response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'full-invalid-'+uuid.uuid4().hex},timeout=180)
    if response.status_code!=422:raise RuntimeError('Invalid request not rejected: '+name+' HTTP'+str(response.status_code))
    rows.append(dict(name=name,http=422,status='Passed'))
after=r.api('/api/dashboard')
if snapshot(before)!=snapshot(after):raise RuntimeError('Admission check changed task set/status; inspect real queue')
write(FOLDER/'api-admission-checks.json',dict(status='Passed',checks=rows,invalidPostCount=len(cases),newTaskSubmissions=0,taskSetUnchanged=True,scope='Real API CPU preflights and invalid POST boundaries. Valid full preflight uses existing151frame media, not generation quality.'))
print('Passed: full151 and legacy57/portrait/compose compatibility,13 invalid POST rejections, zero tasks')

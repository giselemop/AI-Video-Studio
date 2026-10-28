"""Real opt-in caption preflight and invalid request rejection before assembly."""
from run import *
import copy,uuid
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();r.preserve();s=r.state
if not str(read(FOLDER/'deployment.json')['executable']).endswith('DialogueVisual20261025V2\\VideoStudio.Server.exe'):raise RuntimeError('Use tested V2 deployment only')
body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Dialogue-Caption-Preflight',parameters=dict(
    files=[s[f'detail{i}Path'] for i in [1,2,3]],singlePass=True,targetWidth=2560,targetHeight=1440,targetFps=24,targetDurationSeconds=10,
    originalAudioVolume=0,subtitlePath=s['inputs']['subtitle'],outputName='never-submitted-valid-preflight.mp4'))
pre=r.api('/api/tasks/preflight',body);write(FOLDER/'caption-valid-preflight.json',pre)
if not pre['passed']:raise RuntimeError('Valid single-pass caption preflight failed')
before=sorted(x['id'] for x in r.api('/api/tasks?limit=500'));cases=[]
for name,key,value in [('non-srt','subtitlePath','DialogueVisual20261025/run.json'),('outside-caption','subtitlePath','../outside.srt'),('non-bool-mode','singlePass','yes'),('fractional-frame-duration','targetDurationSeconds',10.01)]:
    bad=copy.deepcopy(body);bad['parameters'][key]=value;cases.append((name,bad))
bad=copy.deepcopy(body);bad['episodeId']=1;cases.append(('formal-parent-not-independent',bad))
rows=[dict(name='valid-preflight-only',status='Passed',taskCreated=False)]
for name,bad in cases:
    response=r.session.post(r.base+'/api/tasks',json=bad,headers={'Origin':r.base,'Idempotency-Key':'caption-invalid-'+uuid.uuid4().hex},timeout=90)
    rows.append(dict(name=name,http=response.status_code,status='Passed' if response.status_code==422 else 'Failed'))
    if response.status_code!=422:break
after=sorted(x['id'] for x in r.api('/api/tasks?limit=500'));passed=len(rows)==len(cases)+1 and before==after and all(x['status']=='Passed' for x in rows)
write(FOLDER/'caption-api-checks.json',dict(status='Passed' if passed else 'Failed',checks=rows,taskSetUnchanged=before==after,newTaskSubmissions=0 if before==after else 'Investigate'))
if not passed:raise RuntimeError('Caption request-boundary checks failed')
r.save('ReadyForSinglePassAssembly',singlePassCaptionBuildReady=True)
print('Passed: actual caption preflight,5 invalid POST rejections,zero created tasks')

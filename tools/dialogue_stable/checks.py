"""Boundaries and repeatability evidence; valid generation remains queue-only."""
from run import *
import uuid,hashlib,cv2,numpy as np
def repeat():
    s=read(FOLDER/'run.json');a=cv2.VideoCapture(str(media(s['v2_female_closePath'])));b=cv2.VideoCapture(str(media(s['v2_female_repeatPath'])));rows=[]
    while True:
        ok,x=a.read();ok2,y=b.read()
        if ok!=ok2:raise RuntimeError('Repeated decode counts differ')
        if not ok:break
        delta=np.abs(x.astype(np.int16)-y.astype(np.int16));rows.append(dict(frame=len(rows),maxPixelDifference=int(delta.max()),meanPixelDifference=float(delta.mean())))
    a.release();b.release()
    if len(rows)!=57 or max(x['meanPixelDifference'] for x in rows)>.5:raise RuntimeError('Repeated output not stable')
    ra=read(media(s['v2_female_closeReceiptPath']));rb=read(media(s['v2_female_repeatReceiptPath']))
    if ra['controlledMotionFrames']!=rb['controlledMotionFrames'] or ra['eyeCorrectionFrames']!=rb['eyeCorrectionFrames']:raise RuntimeError('Control traces differ')
    write(FOLDER/'repeatability.json',dict(status='Passed',frames=57,runs=2,decodedFramesExactlyEqual=all(x['maxPixelDifference']==0 for x in rows),maxMeanPixelDifference=max(x['meanPixelDifference'] for x in rows),controlTracesExactlyEqual=True,scope='One repeated 2.28s shot on this hardware and frozen inputs. No claim about arbitrary prompts/models.',rows=rows))
    print('Passed: repeated57-frame render compared')
def admission():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();s=r.state;body=copy.deepcopy(s['v2_female_closeTaskIdInput']);manifest=read(FOLDER/'v2_female_close.json');rows=[]
    task_ids=lambda:{x['id'] for x in r.api('/api/tasks?limit=500')};before=task_ids()
    for name,key,value in [('unknown-role','stableRole','unknown'),('pose-sha','poseSha256','0'*64),('wrong-duration','durationSeconds',2),('wrong-direction','faceDirection','right-left'),('wrong-gain','eyeResidualGain',1.5),('wrong-region','animationRegion','exp')]:
        m=copy.deepcopy(manifest);m[key]=value;p=FOLDER/('invalid-'+name+'.json');write(p,m);request=copy.deepcopy(body);request['parameters'].update(manifest=rel(p),manifestSha256=sha(p));response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'stable-invalid-'+uuid.uuid4().hex},timeout=180)
        if response.status_code!=422:raise RuntimeError('Invalid request accepted '+name)
        rows.append(dict(name=name,status='Passed',http=422))
    for name,key,value in [('unknown-profile','repairProfile','unknown'),('nonstring-profile','repairProfile',9),('engine-drift','engineVersion','0'*64)]:
        request=copy.deepcopy(body);request['parameters'][key]=value;response=r.session.post(r.base+'/api/tasks',json=request,headers={'Origin':r.base,'Idempotency-Key':'stable-invalid-'+uuid.uuid4().hex},timeout=180)
        if response.status_code!=422:raise RuntimeError('Invalid request accepted '+name)
        rows.append(dict(name=name,status='Passed',http=422))
    # Preserved profiles must remain admissible under this deployment.
    old=read(DATA/'DialogueSyncFull20261025/run.json')
    for name,key in [('old-close','actor1FemaleTaskIdInput'),('old-full-hybrid','actor3FemaleTaskIdInput'),('old-full-merge','wideMergeTaskIdInput')]:
        pre=r.api('/api/tasks/preflight',old[key],timeout=180)
        if not pre['passed']:raise RuntimeError('Legacy admission failed '+name+' '+str(pre['issues']))
        rows.append(dict(name=name,status='Passed',preflightOnly=True))
    if task_ids()!=before:raise RuntimeError('Admission checks created tasks')
    write(FOLDER/'admission-checks.json',dict(status='Passed',checks=rows,newTasks=0,scope='Real API rejections and legacy CPU preflights; task states may progress independently.'))
    print('Passed:9 actual invalidPOST rejections,3 legacy preflights, zero new tasks')
def composition():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access();body=copy.deepcopy(r.state['wideMergeTaskIdInput']);manifest=read(FOLDER/'merge.json');rows=[]
    before={x['id'] for x in r.api('/api/tasks?limit=500')}
    if not r.api('/api/tasks/preflight',body,timeout=180)['passed']:raise RuntimeError('Valid merge rejected')
    for name,key,value in [('phase','phase','detail'),('frames','frames',57),('width','width',1366)]:
        m=copy.deepcopy(manifest);m[key]=value;p=FOLDER/('invalid-merge-'+name+'.json');write(p,m);b=copy.deepcopy(body);b['parameters'].update(manifest=rel(p),manifestSha256=sha(p));response=r.session.post(r.base+'/api/tasks',json=b,headers={'Origin':r.base,'Idempotency-Key':'stable-merge-invalid-'+uuid.uuid4().hex},timeout=180)
        if response.status_code!=422:raise RuntimeError('Invalid merge admitted '+name)
        rows.append(dict(name=name,http=422,status='Passed'))
    if before!={x['id'] for x in r.api('/api/tasks?limit=500')}:raise RuntimeError('Composition checks created tasks')
    write(FOLDER/'composition-checks.json',dict(status='Passed',validPreflight=True,checks=rows,newTasks=0));print('Passed: merge boundary checks, no tasks')
if __name__=='__main__':globals()[sys.argv[1]]()

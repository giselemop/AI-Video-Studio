"""Exercise real admission failures without creating media tasks."""
import copy
from pilot import API,FOLDER,Run,read,write,sha,ROOT

run=Run(API,FOLDER/'run.json');run.access()
base=copy.deepcopy(run.state['compositeAttempt2Revision3TaskIdInput'])
rows=[]
def case(name,body,expected):
    result=run.api('/api/tasks/preflight',body,timeout=180)
    if result['passed']!=expected:raise RuntimeError(name+': '+str(result['issues']))
    rows.append(dict(name=name,expected=expected,passed=True,issues=result['issues']))
def project_tasks():
    return sorted(t['id'] for t in run.api('/api/tasks?limit=1000') if t.get('projectId')==run.state['projectId'])
before=project_tasks()
case('frozen valid local manifest',base,True)
for name,patch in [('GPU resource',dict(resourceClass='GPU')),('formal production',dict(productionRunId=1))]:
    body=copy.deepcopy(base);body.update(patch);case(name,body,False)
for name,patch in [('stale engine',dict(engineVersion='0'*64)),('wrong manifest hash',dict(manifestSha256='0'*64)),
                   ('missing manifest',dict(manifest='SkinPilot20261024/missing.json')),('outside Data',dict(manifest='../VideoStudio/config/appsettings.json')),
                   ('wrong manifest type',dict(manifest=42))]:
    body=copy.deepcopy(base);body['parameters'].update(patch);case(name,body,False)
manifest=read(FOLDER/'attempt-2-manifest.json')
for name,field,value in [('wrong frame count','frameCount',49),('wrong start frame','startFrame',6),
                         ('wrong blend','blend',1.0),('bad ROI','roi',[-1,0,800,800]),('unbounded keys','keyframes',[0,47])]:
    altered=copy.deepcopy(manifest);altered[field]=value
    path=FOLDER/'preflight-fixtures'/(field+'.json');write(path,altered)
    body=copy.deepcopy(base);body['parameters'].update(manifest=str(path.relative_to(FOLDER.parent)),manifestSha256=sha(path))
    case(name,body,False)
bad=copy.deepcopy(base);bad['parameters']['engineVersion']='0'*64
response=run.session.post(API+'/api/tasks',json=bad,headers={'Origin':API},timeout=180)
if response.status_code!=422:raise RuntimeError('Invalid POST must be rejected before a task is written')
after=project_tasks()
if before!=after:raise RuntimeError('Preflight created a task')
write(FOLDER/'preflight-verification.json',dict(status='Passed',cases=rows,invalidPostStatus=422,
    projectTaskIdsBefore=before,projectTaskIdsAfter=after,newTasks=0))
print(f'Passed: {len(rows)} real preflight cases, rejected POST422, no task created',flush=True)

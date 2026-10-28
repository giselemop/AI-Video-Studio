"""Exercise real pose admission and rejection without submitting GPU inference."""
import copy
import json
from run import RealisticRun,FOLDER


def main():
    run=RealisticRun('http://127.0.0.1:18080',FOLDER/'run.json');run.access()
    workflow=next(w['id'] for w in run.api('/api/workflows') if w['name']=='realvisxl_openpose_reference_api')
    pose='ReferenceGuides/RealisticI2V20261022/standing-pose.png'
    base=dict(projectId=run.state['projectId'],taskType='Image',resourceClass='GPU',workflowId=workflow,maxRetries=0,
        parameters=dict(workflowVersion='realvisxl-openpose-reference-1536-v1',inputSlots=dict(pose=pose),
            width=1536,height=864,positive='Preflight only; no inference',seed=2026102206,steps=35,cfg=5.5))
    before=[t['id'] for t in run.api('/api/tasks?limit=100')]
    cases=[('valid-named-pose',{},True),('missing-pose',dict(inputSlots={}),False),
        ('wrong-identity-role',dict(inputSlots=dict(identityReference=pose)),False),
        ('outside-data',dict(inputSlots=dict(pose='../../config/local.env')),False),
        ('empty-pose',dict(inputSlots=dict(pose='')),False),
        ('legacy-mixed-with-slots',dict(controlImagePath=pose),False)]
    results=[]
    for name,changes,expected in cases:
        body=copy.deepcopy(base);body['parameters'].update(changes)
        check=run.api('/api/tasks/preflight',body)
        assert check['passed']==expected,(name,check['issues'])
        if expected:assert next(c for c in check['checks'] if c['name']=='controlNetInput')['value']['poseSlot'] is True
        results.append(dict(name=name,status='Passed',preflight=check))
    rejected=copy.deepcopy(base);rejected['parameters']['inputSlots']={}
    response=run.session.post(run.base+'/api/tasks',json=rejected,headers={'Origin':run.base},timeout=60)
    assert response.status_code==422,response.status_code
    after=[t['id'] for t in run.api('/api/tasks?limit=100')]
    assert before==after,'Preflight or rejected POST created a task'
    (FOLDER/'pose-preflight-regression.json').write_text(json.dumps(dict(status='Passed',checks=results,
        rejectedSubmitHttp=422,noTasksCreated=True),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='Passed',preflightCases=len(results),rejectedSubmitHttp=422,noTasksCreated=True)),flush=True)


if __name__=='__main__':main()

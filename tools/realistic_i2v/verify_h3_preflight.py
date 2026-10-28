"""Verify installed 20/30 H3 admission paths without spending GPU generation."""
import copy
import json
from run import RealisticRun,FOLDER,VIDEO_PROMPT


def main():
    run=RealisticRun('http://127.0.0.1:18080',FOLDER/'run.json');run.access()
    workflows={w['name']:w['id'] for w in run.api('/api/workflows')}
    image=run.state['reference4TaskIdPath']
    # This image is a technical input fixture only. It was rejected for content.
    parameters=dict(provider='MiniMaxLocal',profile='native1080',textToVideo=False,prompt=VIDEO_PROMPT,
        seed=2026102220,width=1920,height=1088,frames=124,fps=24,steps=20,duration=124/24,
        preserveAudio=True,extractNativeAudio=True,qualityReferenceImagePath=image,contentReview='NeedReview')
    base=dict(projectId=run.state['projectId'],taskType='ImageToVideo',resourceClass='GPU',inputImagePath=image,
        workflowId=workflows['minimax_h3_local_1088_i2v_api'],stage='MiniMax-Local-Experiment',maxRetries=0,parameters=parameters)
    before=[t['id'] for t in run.api('/api/tasks?limit=100')]
    results=[]
    for steps in [20,30]:
        body=copy.deepcopy(base);body['parameters']['steps']=steps
        if steps==30:body['workflowId']=workflows['minimax_h3_local_1088_i2v_30steps_api']
        result=run.api('/api/tasks/preflight',body,timeout=600)
        assert result['passed'],result['issues']
        results.append(dict(steps=steps,status='Passed',preflight=result))
    wrong=copy.deepcopy(base);wrong['parameters']['steps']=30
    result=run.api('/api/tasks/preflight',wrong,timeout=600)
    assert result['passed'] is False,'Cross-template step mismatch was admitted'
    results.append(dict(name='30-steps-with-20-step-template',status='Passed',preflight=result))
    after=[t['id'] for t in run.api('/api/tasks?limit=100')]
    assert before==after,'Preflight created a task'
    (FOLDER/'h3-preflight-regression.json').write_text(json.dumps(dict(status='Passed',checks=results,
        noTasksCreated=True,contentApproved=False,actual30StepInference='BlockedByReferenceContent'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='Passed',preflightCases=3,noTasksCreated=True,contentApproved=False)),flush=True)


if __name__=='__main__':main()

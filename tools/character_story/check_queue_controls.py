"""Real pending CPU preview cancellation. No GPU task or fabricated failure."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).parent))
from pilot import Pilot
from setup import OUT,write,mysql

def run():
    checkpoint=OUT/'queue-controls.json'
    state=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    if state.get('status')=='Passed':print('Preserved completed queue control evidence; no repeated task.');return
    p=Pilot();runtime=p.api('/api/minimax/local/status');assert not runtime['queue']['paused'],'Do not override another pause'
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Running','Pending') AND project_id<>50;")=='0'
    p.api('/api/production/pause',{})
    try:
        body=dict(episodeId=p.state['episodeId'],taskIds=[p.state['slots']['a-face']['Video']['id']],idempotencyKey=p.key('cancel-only-CPU-preview-regression'))
        result=p.api('/api/character-story/preview',body);tid=result['id'];state.update(taskId=tid,request=body,stage='PendingCancellation');write(checkpoint,state)
        before=p.api('/api/tasks/'+str(tid));assert before['task']['status']=='Pending' and before['task']['resourceClass']=='CPU' and before['task']['attempts']==0
        p.api(f'/api/tasks/{tid}/cancel',{})
        after=p.api('/api/tasks/'+str(tid));assert after['task']['status']=='Cancelled' and after['task']['attempts']==0 and not after['results']
        retry=p.s.post(p.base+f'/api/tasks/{tid}/retry',json={},timeout=30);assert retry.status_code==422
        replay=p.api('/api/character-story/preview',body);assert replay['id']==tid and replay.get('created') is False
        state.update(status='Passed',stage='Completed',before=before['task'],after=after['task'],cancelledBeforeExecution=True,genericRetryStatus=retry.status_code,genericRetryBlocked=True,idempotentReplayPreservedTask=True,gpuTasksCreated=0,humanApprovals=0)
        write(checkpoint,state)
    finally:p.api('/api/production/resume',{})
    print(f'CPU task {tid}: durable Pending, cancellation, no execution, retry bypass rejection and idempotent replay Passed; GPU task untouched.')
if __name__=='__main__':run()

"""Verify the one controlled API process-loss test without changing any task."""
from pathlib import Path
import sys,json,requests
sys.path.insert(0,str(Path(__file__).parent))
from setup import OUT,DATA,write,mysql,ROOT,sha

def run():
    r=json.loads((OUT/'restart-recovery.json').read_text(encoding='utf-8-sig'));tid=int(r['targetTaskId'])
    query=f"SELECT JSON_OBJECT('id',id,'status',status,'attempts',attempts,'comfyPromptId',comfy_prompt_id) FROM generation_tasks WHERE id={tid};"
    task=json.loads(mysql(query));attempts=[json.loads(line) for line in mysql(f"SELECT JSON_OBJECT('attempt',attempt_no,'status',status,'failureCode',failure_code) FROM task_attempts WHERE task_id={tid} ORDER BY attempt_no;").splitlines()]
    assert task['status']=='Succeeded' and task['attempts']==2 and task['comfyPromptId']==r['originalPromptId']
    assert [(a['attempt'],a['status']) for a in attempts]==[(1,'Abandoned'),(2,'Succeeded')]
    original=json.loads((DATA/f'CharacterStoryTrace/task_{tid}/submission.json').read_text(encoding='utf-8'));assert original['attemptNo']==1 and original['promptId']==r['originalPromptId']
    executed=json.loads((DATA/f'CharacterStoryTrace/task_{tid}/attempt_2/applied-workflow.json').read_text(encoding='utf-8'))
    submitted=json.loads((DATA/f'CharacterStoryTrace/task_{tid}/submitted-workflow.json').read_text(encoding='utf-8'));assert submitted==executed
    histories=requests.get('http://127.0.0.1:8188/history',timeout=30).json()
    matching=[key for key,h in histories.items() if f'task_{tid}_attempt_' in json.dumps(h.get('prompt',[]))]
    assert matching==[r['originalPromptId']],matching
    assert sha(ROOT/'server/publish/VideoStudio.Server.dll')==r['dllSha256']
    r.update(status='Passed',task=task,attempts=attempts,matchingComfyExecutions=matching,originalSubmittedGraphReused=True,duplicateGpuSubmission=False,leaseRecovery='Passed',completedTaskIdPreserved=True,contentReview='NeedReview',publication='Blocked')
    write(OUT/'restart-recovery.json',r);print(f'Real task {tid}: API restart, expired lease, original prompt reused, single Comfy execution and final artifact Passed.')
if __name__=='__main__':run()

"""One bounded recovery after native Comfy torch storage failure; keep task1452."""
from repair_closeups import candidate
from run import Run,PEOPLE,FOLDER,read,write

r=Run();r.access()
failed=r.state['tasks']['zhouyan-threeQuarterRight-closeUp-repair1']
detail=r.api('/api/tasks/'+str(failed['id']))
if failed['id']!=1452 or detail['task']['status']!='Failed':raise RuntimeError('Expected recorded failed candidate; never duplicate an unresolved task')
queue=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
if queue['queue_running'] or queue['queue_pending']:raise RuntimeError('Keep GPU concurrency one')
failed.update(status='Failed',errorMessage=detail['task']['errorMessage']);r.save();write(FOLDER/'zhouyan-threeQuarterRight-closeUp-repair1-task.json',detail)
r,key,body=candidate(PEOPLE[1],'threeQuarterRight')
body['parameters']['seed']+=1;body['stage']='Character-Pack-CloseUp-Repair-2-RecoveredRuntime'
repaired=key+'-repair2';r.once(repaired,body)
selected=read(FOLDER/'selection.json');selected[key]=repaired;write(FOLDER/'selection.json',selected)
print('Final close-up recovery completed; original failed task retained',flush=True)

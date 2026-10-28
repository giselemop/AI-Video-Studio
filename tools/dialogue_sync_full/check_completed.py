"""Exercise completion guard and compare real dashboard counts/newest task set."""
from run import *
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access()
if not r.state.get('completed'):raise RuntimeError('Real acceptance must finish first')
def snapshot():
    value=r.api('/api/dashboard');return dict(counts=value['counts'],recentTasks=[dict(id=t['id'],status=t['status']) for t in value['recentTasks']])
before=snapshot();write(FOLDER/'guard-before.json',before);results=[]
commands=[(stage,[str(ROOT/'tools/dialogue_sync_full/run.py'),'--stage',stage]) for stage in ['check','generate']]
commands += [(name,[str(ROOT/'tools/dialogue_sync_full'/name)]) for name in ['recover_driver.py','finish.py']]
for stage,arguments in commands:
    result=subprocess.run([sys.executable,*arguments],capture_output=True,text=True)
    if result.returncode or 'Preserved; no new tasks' not in result.stdout:raise RuntimeError('Completed-run guard failed')
    results.append(dict(stage=stage,exitCode=result.returncode,output=result.stdout.strip()))
after=snapshot();write(FOLDER/'guard-after.json',after)
if before!=after:raise RuntimeError('Task snapshot changed during completion guard checks')
write(FOLDER/'completed-guard-checks.json',dict(status='Passed',checks=results,taskCountsUnchanged=True,recentTaskSetUnchanged=True,newestTaskId=after['recentTasks'][0]['id'],observationMethod='Actual local API dashboard counts and newest12 task IDs/statuses before/after'))
print('Passed: completed check/generate did not create or change real tasks')

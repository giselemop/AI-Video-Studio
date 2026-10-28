from run import *
r=Run('http://127.0.0.1:18081',FOLDER/'run.json');r.access()
if not r.state.get('completed'):raise RuntimeError('Acceptance incomplete')
def snapshot():
    d=r.api('/api/dashboard');return dict(counts=d['counts'],recent=[(t['id'],t['status']) for t in d['recentTasks']])
before=snapshot();rows=[]
for args in [['run.py','check'],['run.py','act','--role','female-close'],['run.py','assemble'],['finish.py']]:
    out=subprocess.run([sys.executable,str(ROOT/'tools/dialogue_stable'/args[0]),*args[1:]],capture_output=True,text=True)
    if out.returncode or 'Preserved; no new tasks' not in out.stdout:raise RuntimeError('Completed guard failed')
    rows.append(dict(arguments=args,exitCode=out.returncode,output=out.stdout.strip()))
if before!=snapshot():raise RuntimeError('Completed guard changed tasks')
write(FOLDER/'completed-guard-checks.json',dict(status='Passed',checks=rows,taskCountsAndRecentTasksUnchanged=True,newTasks=0))
print('Passed: completed stages did not submit or modify tasks')

"""Return queue control through supported APIs; never terminate an existing service."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import API, FOLDER, Run, read, write

run = Run(API, FOLDER / 'run.json')
run.access()
active = [t for t in run.api('/api/tasks?limit=1000') if t['status'] in ('Pending', 'Queued', 'Running', 'Cancelling')]
if active:
    raise RuntimeError('Tasks remain active; preserve queue ownership until they finish')
run.api('/api/production/pause', {})
old = Run('http://127.0.0.1:18080', FOLDER / 'run.json')
old.access()
initial = read(FOLDER / 'original-queue-before.json')
if not initial['paused']:
    old.api('/api/production/resume', {})
new_status = run.api('/api/minimax/local/status')['queue']
old_status = old.api('/api/minimax/local/status')['queue']
if not new_status['paused'] or old_status['paused'] != initial['paused']:
    raise RuntimeError('Queue states did not return to the intended configuration')
write(FOLDER / 'final-queue-states.json', dict(status='Passed', original=old_status, preview=new_status))
print('Passed: isolated preview queue paused, original queue state restored')

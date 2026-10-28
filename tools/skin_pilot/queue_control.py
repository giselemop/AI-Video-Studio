"""Coordinate existing workers with their supported pause/resume APIs."""
import argparse
from pilot import API,FOLDER,Run,write,read

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['acquire','restore'])
args=parser.parse_args()
run=Run(API,FOLDER/'run.json')
if args.action=='acquire':
    before={}
    for port in [18080,18081]:
        client=Run(f'http://127.0.0.1:{port}',FOLDER/'run.json')
        client.access()
        before[str(port)]=client.api('/api/minimax/local/status')['queue']
        if any(t['status'] in ['Running','Cancelling','Pending','Queued'] for t in client.api('/api/tasks?limit=1000')):
            raise RuntimeError('An existing task is active; do not take over its queue')
    if not (FOLDER/'queues-before.json').exists():write(FOLDER/'queues-before.json',before)
    for port in [18080,18081]:
        client=Run(f'http://127.0.0.1:{port}',FOLDER/'run.json');client.access()
        client.api('/api/production/pause',{})
    print('Existing idle workers paused through APIs; binaries preserved',flush=True)
else:
    run.access()
    for key,value in run.state.items():
        if key.endswith('TaskId') and isinstance(value,int):
            if run.api(f'/api/tasks/{value}')['task']['status'] not in ['Succeeded','Failed','Cancelled']:
                raise RuntimeError('A recorded task still needs its worker')
    run.api('/api/production/pause',{})
    before=read(FOLDER/'queues-before.json')
    after={}
    for port in [18080,18081]:
        client=Run(f'http://127.0.0.1:{port}',FOLDER/'run.json');client.access()
        desired=before[str(port)]['paused']
        client.api('/api/production/pause' if desired else '/api/production/resume',{})
        after[str(port)]=client.api('/api/minimax/local/status')['queue']
        if after[str(port)]['paused']!=desired:raise RuntimeError('Queue restore mismatch')
    after['18081']=run.api('/api/minimax/local/status')['queue']
    write(FOLDER/'queues-after.json',after)
    print('Preview worker paused; original queue states restored',flush=True)

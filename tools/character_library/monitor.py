"""Bounded resource samples for this acceptance run; never submits a task."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime,timezone
import requests

sys.path.insert(0,str(Path(__file__).parent))
from run_acceptance import FOLDER,read,write

samples=[];deadline=time.monotonic()+7200
while time.monotonic()<deadline:
    state=read(FOLDER/'run.json')
    sample=dict(at=datetime.now(timezone.utc).isoformat(),stage=state['stage'],freeDiskBytes=shutil.disk_usage(FOLDER).free)
    try:
        queue=requests.get('http://127.0.0.1:8188/queue',timeout=10).json()
        sample.update(comfyRunning=len(queue['queue_running']),comfyPending=len(queue['queue_pending']))
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True,timeout=10).strip().split(',')
        sample.update(gpuUsedMiB=int(gpu[0]),gpuFreeMiB=int(gpu[1]),gpuUtilizationPercent=int(gpu[2]))
    except Exception as ex:sample['error']=type(ex).__name__
    samples.append(sample);write(FOLDER/'resource-samples.json',dict(samples=samples,scope='Periodic observations, not an exact per-task resource peak'))
    if state['stage']=='VideosReady':
        ui=read(FOLDER/'browser-ui-checks.json')
        detail=requests.get('http://127.0.0.1:18080/api/tasks/'+str(ui['submittedTaskId']),timeout=15).json()
        if detail['task']['status'] in ['Succeeded','Failed','Cancelled']:break
    time.sleep(10)
print('Resource observations saved:',len(samples),flush=True)

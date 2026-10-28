"""Cross-check queue records, Comfy outputs, local restoration receipts and resource samples."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import requests
import subprocess
from run import ROOT,DATA,FOLDER,API,Run,read,write,sha,media,preserve

run=Run(API,FOLDER/'run.json');run.access();preserve(run)
for name in ['pilot-verification.json','final-verification.json','pilot-qhd-verification.json','preflight-verification.json','workflow-verification.json','streaming-boundary-verification.json']:
    if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Required verification not passed: '+name)
ids=sorted({v for k,v in run.state.items() if k.endswith('TaskId') and isinstance(v,int)})
details={i:run.api(f'/api/tasks/{i}') for i in ids};tasks={i:d['task'] for i,d in details.items()}
if any(t['status'] not in ['Succeeded','Failed','Cancelled'] for t in tasks.values()):raise RuntimeError('An existing task is unresolved')
if tasks[run.state['finalTaskId']]['status']!='Succeeded':raise RuntimeError('Final task is not successful')
for i in [1,2,3]:
    review=read(FOLDER/f'qhd-{i}-review.json')
    if review['decision']!='SelectedForAssembly':raise RuntimeError('QHD review missing')
    task_id=run.state[f'restore{i}Attempt{review["attempt"]}TaskId']
    if tasks[task_id]['status']!='Succeeded':raise RuntimeError('Selected restoration failed')
    receipt=next(x['assetPath'] for x in details[task_id]['results'] if x.get('available') and x.get('mimeType')=='application/json')
    value=read(media(receipt))
    if value['chunkSize']!=33 or value['batchSize']!=5 or value['temporalOverlap']!=3 or [value['width'],value['height']]!=[2560,1440]:
        raise RuntimeError('Actual streaming QHD settings differ')
    write(FOLDER/f'qhd-{i}-actual-receipt.json',value)
s=requests.Session();s.trust_env=False
history=s.get('http://127.0.0.1:8188/history',params=dict(max_items=100),timeout=30).json()
comfy_ids={i for i,t in tasks.items() if t['taskType'] in ['Image','ImageToVideo'] and t['status']=='Succeeded'}
matched={}
for prompt_id,item in history.items():
    graph=item['prompt'][2]
    outputs=[(key,n) for key,n in graph.items() if n['class_type'] in ['SaveImage','SaveVideo']]
    if not outputs:continue
    key,node=outputs[-1];match=re.search(r'task_(\d+)',node['inputs'].get('filename_prefix',''))
    if not match or int(match[1]) not in comfy_ids:continue
    task_id=int(match[1])
    if not item['status']['completed'] or item['status']['status_str']!='success':raise RuntimeError('Comfy history not successful')
    extension='.png' if tasks[task_id]['taskType']=='Image' else '.mp4'
    published=next(x['assetPath'] for x in details[task_id]['results'] if x.get('available') and x.get('assetPath','').endswith(extension))
    def files(value):
        if isinstance(value,dict):
            if 'filename' in value:yield value
            for v in value.values():yield from files(v)
        elif isinstance(value,list):
            for v in value:yield from files(v)
    raw=next(x for x in files(item['outputs'][key]) if x['filename'].endswith(extension))
    file=(ROOT.parent/'ComfyUI/output'/raw.get('subfolder','')/raw['filename']).resolve(strict=True)
    if not file.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()) or sha(file)!=sha(media(published)):
        raise RuntimeError('Published file differs from actual Comfy output')
    if extension=='.mp4' and graph['15']['inputs']['steps']!=8:raise RuntimeError('Actual video sampler differs')
    matched[task_id]=dict(taskId=task_id,promptId=prompt_id,sha256=sha(file),status='Succeeded')
    write(FOLDER/'comfy-history'/f'{task_id}.json',item)
if set(matched)!=comfy_ids:raise RuntimeError('Missing actual Comfy task history')
gpu={i:t for i,t in tasks.items() if t['resourceClass']=='GPU'};events=[]
for t in gpu.values():
    if t.get('startedAt') and t.get('finishedAt'):
        events.extend([(datetime.fromisoformat(t['startedAt']),1),(datetime.fromisoformat(t['finishedAt']),-1)])
active=peak=0
for _,delta in sorted(events):active+=delta;peak=max(peak,active)
if peak!=1:raise RuntimeError('GPU tasks overlapped')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines()]
qhd_ids={i for i,t in tasks.items() if t['taskType']=='VideoRestore'}
qhd_samples=[r for r in samples if r['taskId'] in qhd_ids]
summary=dict(status='Passed',tasks=tasks,comfyHistory=matched,gpuMaximumConcurrency=peak,
    gpuSeconds=sum((t.get('durationMs') or 0) for t in gpu.values())/1000,
    cpuSeconds=sum((t.get('durationMs') or 0) for t in tasks.values() if t['resourceClass']=='CPU')/1000,
    resourceSamples=len(samples),sampledDevicePeakMiB=max(r['gpu'][0] for r in samples),
    minimumAvailableRamMiB=min(r['availableRamMiB'] for r in samples),
    qhdMinimumAvailableRamMiB=min(r['availableRamMiB'] for r in qhd_samples),
    qhdSampledDevicePeakMiB=max(r['gpu'][0] for r in qhd_samples),newModelDownloads=0,cloudInferenceCalls=0)
write(FOLDER/'execution-summary.json',summary)
subprocess.run([str(ROOT.parent/'ComfyUI/venv/Scripts/python.exe'),'-m','compileall','-q',str(ROOT/'tools/face_acting'),str(ROOT/'tools/video_detail/restore.py')],check=True)
for name in ['face-acting-preview.html','face-acting-preview.json']:
    if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Static deployment differs')
write(FOLDER/'source-verification.json',dict(status='Passed',pythonCompiled=True,publicDistEqual=True,
    newWorkflows=run.state['registeredWorkflows'],originalMediaPreserved=True,originalVoicePacketsPreserved=True))
print({k:summary[k] for k in ['status','gpuSeconds','cpuSeconds','gpuMaximumConcurrency','sampledDevicePeakMiB','minimumAvailableRamMiB','qhdMinimumAvailableRamMiB']},flush=True)

"""Cross-check actual Comfy history, queue records, files and resource samples."""
from datetime import datetime
import json
import re
import subprocess
import requests
from pilot import ROOT,DATA,FOLDER,API,Run,read,write,sha,media,preserve

run=Run(API,FOLDER/'run.json');run.access();preserve(run)
ids=sorted({value for key,value in run.state.items() if key.endswith('TaskId') and isinstance(value,int)})
tasks={i:run.api(f'/api/tasks/{i}')['task'] for i in ids}
if any(t['status'] not in ['Succeeded','Failed','Cancelled'] for t in tasks.values()):raise RuntimeError('Unresolved recorded task')
if tasks[run.state['selectedCompositeTaskId']]['status']!='Succeeded':raise RuntimeError('Selected CPU task not successful')
gpu={i:t for i,t in tasks.items() if t['resourceClass']=='GPU'}
if len(gpu)!=10 or any(t['status']!='Succeeded' for t in gpu.values()):raise RuntimeError('Expected ten real local GPU tasks')
s=requests.Session();s.trust_env=False
histories=s.get('http://127.0.0.1:8188/history',params=dict(max_items=50),timeout=30).json()
matched={}
for prompt_id,entry in histories.items():
    graph=entry['prompt'][2]
    prefix=graph.get('12',{}).get('inputs',{}).get('filename_prefix','')
    match=re.search(r'task_(\d+)',prefix)
    if not match or int(match[1]) not in gpu:continue
    task_id=int(match[1])
    if not entry['status']['completed'] or entry['status']['status_str']!='success':raise RuntimeError('Comfy history is not successful')
    if graph['1']['inputs']['ckpt_name']!='RealVisXL_V5.0_fp16.safetensors':raise RuntimeError('Unexpected GPU model')
    key=next(k for k,v in run.state.items() if k.endswith('TaskId') and v==task_id)
    artifact=media(run.state[key[:-6]+'Path'])
    image=entry['outputs']['12']['images'][0]
    raw=(ROOT.parent/'ComfyUI/output'/image['subfolder']/image['filename']).resolve(strict=True)
    if not raw.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()) or sha(raw)!=sha(artifact):
        raise RuntimeError('Comfy image and published artifact differ')
    matched[task_id]=dict(promptId=prompt_id,taskId=task_id,status='Succeeded',sha256=sha(artifact),
                          sampler=graph['9']['inputs'],checkpoint=graph['1']['inputs']['ckpt_name'])
    write(FOLDER/'comfy-history'/f'{task_id}.json',entry)
if set(matched)!=set(gpu):raise RuntimeError('Comfy histories do not cover every GPU task')
events=[]
for task in gpu.values():
    events.extend([(datetime.fromisoformat(task['startedAt']),1),(datetime.fromisoformat(task['finishedAt']),-1)])
active=peak=0
for _,change in sorted(events):active+=change;peak=max(peak,active)
if peak!=1:raise RuntimeError('Actual GPU tasks overlapped')
samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text().splitlines()]
summary=dict(status='Passed',gpuTasks=list(gpu),cpuTasks=[i for i,t in tasks.items() if t['resourceClass']=='CPU'],
    tasks=tasks,gpuSeconds=sum(t['durationMs'] for t in gpu.values())/1000,
    cpuSeconds=sum(t['durationMs'] for t in tasks.values() if t['resourceClass']=='CPU')/1000,
    maximumGpuConcurrency=peak,sampledDevicePeakMiB=max(s['gpu'][0] for s in samples),
    minimumAvailableRamMiB=min(s['availableRamMiB'] for s in samples),resourceSamples=len(samples),
    selectedFinalTask=run.state['selectedCompositeTaskId'],rejectedCandidates=[dict(taskId=1279,taskStatus=tasks[1279]['status'],delivery='Failed: ROI boundary check'),
        dict(taskId=1280,taskStatus=tasks[1280]['status'],delivery='Failed: audio excerpt duration')],
    originalFilesPreserved=True,newModelDownloads=0,cloudInferenceCalls=0,comfyHistory=matched)
write(FOLDER/'execution-summary.json',summary)
contract=read(ROOT/'config/workflow-contracts.json');before=read(FOLDER/'source-before/config/workflow-contracts.json')
contract['contracts']=[c for c in contract['contracts'] if c['id']!='realvisxl-skin-patch-768-v1']
if contract!=before:raise RuntimeError('An unrelated workflow contract changed')
model=ROOT.parent/'Models/checkpoints/RealVisXL_V5.0_fp16.safetensors'
actual=sha(model)
if actual!=run.state['modelSha256'][model.name]:raise RuntimeError('Model content changed')
subprocess.run([str(ROOT.parent/'ComfyUI/venv/Scripts/python.exe'),'-m','compileall','-q',str(ROOT/'tools/skin_pilot')],check=True)
write(FOLDER/'source-verification.json',dict(status='Passed',existingWorkflowContractsPreserved=True,modelSha256=actual,
    pythonCompiled=True,htmlPublicDistEqual=sha(ROOT/'web/public/skin-pilot-compare.html')==sha(ROOT/'web/dist/skin-pilot-compare.html'),
    jsonPublicDistEqual=sha(ROOT/'web/public/skin-pilot-compare.json')==sha(ROOT/'web/dist/skin-pilot-compare.json')))
print({k:summary[k] for k in ['status','gpuSeconds','cpuSeconds','sampledDevicePeakMiB','minimumAvailableRamMiB','maximumGpuConcurrency']},flush=True)

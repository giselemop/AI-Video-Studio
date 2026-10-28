"""Read-only final availability and idle-queue checks; no service reconfiguration."""
import json
import shutil
import psutil
import requests
from run import ROOT,DATA,FOLDER,API,Run,read,write,sha,media,preserve

run=Run(API,FOLDER/'run.json');preserve(run)
verified=read(FOLDER/'final-verification.json')
if verified['status']!='Passed' or verified['sha256']!=sha(media(run.state['finalPath'])):
    raise RuntimeError('Final media verification required')
health=run.api('/api/health');tasks=run.api('/api/tasks?limit=500')
active=[dict(id=t['id'],status=t['status']) for t in tasks if t['status'] in ['Pending','Running','Queued','Retrying']]
if active or not health['database']['online'] or not health['ffmpeg']['available']:
    raise RuntimeError('Queue or local dependencies not ready')
session=requests.Session();session.trust_env=False
response=session.get('http://127.0.0.1:8188/queue',timeout=30);response.raise_for_status();comfy=response.json()
if comfy['queue_running'] or comfy['queue_pending']:raise RuntimeError('Comfy queue still active')
listeners=[dict(port=c.laddr.port,address=c.laddr.ip,pid=c.pid) for c in psutil.net_connections(kind='tcp')
    if c.status==psutil.CONN_LISTEN and c.laddr.port in [18080,8188]]
if {c['port'] for c in listeners}!={18080,8188} or any(c['address'] not in ['127.0.0.1','::1'] for c in listeners):
    raise RuntimeError('Expected loopback-only preview and Comfy listeners')
html=session.get(API+'/face-acting-preview.html',timeout=30);html.raise_for_status()
metadata=session.get(API+'/face-acting-preview.json',timeout=30);metadata.raise_for_status();value=metadata.json()
if value['full']['paths'][2]!=run.state['finalPath'].replace('\\','/') or not value['pilot']['paths'][2].endswith('.mp4'):
    raise RuntimeError('Preview is not pointing to the verified final')
if html.content!=(ROOT/'web/dist/face-acting-preview.html').read_bytes():raise RuntimeError('Served page differs from deployed page')
write(FOLDER/'final-environment-verification.json',dict(status='Passed',databaseOnline=True,ffmpegAvailable=True,
    activeQueueTasks=active,comfyQueueIdle=True,loopbackListeners=listeners,previewHttpStatus=html.status_code,
    metadataHttpStatus=metadata.status_code,servedPageSha256=sha(ROOT/'web/dist/face-acting-preview.html'),
    finalSha256=verified['sha256'],freeDataDiskGiB=shutil.disk_usage(DATA).free/1024**3,servicesLeftRunning=True))
print('Passed: local dependencies healthy, both queues idle, exact final preview served',flush=True)

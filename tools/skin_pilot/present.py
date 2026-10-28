"""Publish the verified comparison UI as local static files, without replacing prior pages."""
import shutil
import subprocess
from pilot import ROOT,DATA,FOLDER,API,Run,read,write,sha,preserve

run=Run(API,FOLDER/'run.json')
preserve(run)
verification=read(FOLDER/'verification.json')
if verification['status']!='Passed' or not all(verification['checks'].values()):raise RuntimeError('Verify real files first')
value=dict(technicalStatus='Passed',contentStatus='NeedReview',outputs={k:v.replace('\\','/') for k,v in run.state['outputs'].items()
    if k in ['original','qhd','optimized']},samplesPrefix='SkinPilot20261024/compare-face-',
    line=run.state['line'],startFrame=5,frameCount=48,fps=24)
path=ROOT/'web/public/skin-pilot-compare.json'
write(path,value)
for name in ['skin-pilot-compare.html','skin-pilot-compare.json']:
    shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
    if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Static deployment differs')
import re
js=re.search(r'<script>([\s\S]*?)</script>',(ROOT/'web/public/skin-pilot-compare.html').read_text(encoding='utf-8'))[1]
(FOLDER/'preview.js').write_text(js,encoding='utf-8')
subprocess.run(['node','--check',str(FOLDER/'preview.js')],check=True)
run.save('AwaitingBrowserPlayback',previewUrl='http://127.0.0.1:18080/skin-pilot-compare.html')
print(run.state['previewUrl'],flush=True)

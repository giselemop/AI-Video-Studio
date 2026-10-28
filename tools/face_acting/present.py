"""Publish verified pilot/final comparisons through the existing local media API."""
import shutil
from run import ROOT,DATA,FOLDER,API,Run,read,write,media,sha,preserve

run=Run(API,FOLDER/'run.json');preserve(run)
pilot=read(FOLDER/'pilot-verification.json')
if pilot['status']!='Passed':raise RuntimeError('Actual pilot verification required')
old=read(DATA/'SkinPilot20261024/run.json')
new_pilot=run.state.get('pilotQhdPath',run.state['pilotPath'])
if run.state.get('pilotQhdPath'):
    verified=read(FOLDER/'pilot-qhd-verification.json')
    if verified['status']!='Passed' or verified['sha256']!=sha(media(new_pilot)):raise RuntimeError('QHD pilot verification required')
value=dict(technicalStatus='Passed',contentStatus='NeedReview',intro='纯本地 · 原声和时间轴保持 · 两秒表情短测已完成，十秒三镜头正在处理。',
    pilot=dict(seconds=2,frames=48,paths=[old['outputs']['original'],old['outputs']['qhd'],new_pilot],
      newTitle='新版表情 · '+('2K' if run.state.get('pilotQhdPath') else '720p 短测'),
      comparisonPrefix='FaceActing20261024/'+('pilot-qhd-comparison' if run.state.get('pilotQhdPath') else 'pilot-comparison')+'/compare-',moments=[dict(frame=i,label=f'{i/24:.3f} 秒') for i in [0,12,24,36,47]]),
    full=None,references=[dict(label='原始露齿笑参考',path=run.state['geometry']['female']['input'],selected=False)])
for i in [1,2,3]:
    value['references'].append(dict(label=['A · 闭口表情候选','B · 轻微闭口（本轮选用）','C · 侧脸表情候选'][i-1],
        path=run.state[f'femaleRef{i}Attempt3Path'],selected=i==2))
if (FOLDER/'final-verification.json').exists():
    final=read(FOLDER/'final-verification.json')
    if final['status']!='Passed' or final['sha256']!=sha(media(run.state['finalPath'])):raise RuntimeError('Final verification changed')
    value['intro']='纯本地完成 · 十秒三镜头 · 同一组人物参考、四句原台词与完整原声。支持同步播放、逐帧和两秒短测对照。'
    value['full']=dict(seconds=10,frames=240,paths=[run.state['originalPath'],run.state['previousQhdPath'],run.state['finalPath']],newTitle='表情重建 · 2K',
        comparisonPrefix='FaceActing20261024/final-comparison/compare-',moments=[dict(frame=i,label=label) for i,label in [(19,'女方近景'),(77,'男方回应'),(127,'女方让步'),(168,'男方收尾'),(239,'末帧')]])
def browser_paths(value):
    if isinstance(value,str):return value.replace('\\','/')
    if isinstance(value,list):return [browser_paths(v) for v in value]
    if isinstance(value,dict):return {k:browser_paths(v) for k,v in value.items()}
    return value
write(ROOT/'web/public/face-acting-preview.json',browser_paths(value))
for name in ['face-acting-preview.html','face-acting-preview.json']:
    shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
    if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Static preview deployment differs')
print('http://127.0.0.1:18080/face-acting-preview.html',flush=True)

"""Publish only verified new media; keep the previous project previews intact."""
from run import ROOT,DATA,FOLDER,Run,read,write,media,sha
import shutil

run=Run('http://127.0.0.1:18081',FOLDER/'run.json');run.preserve();s=run.state
verified=read(FOLDER/'media-verification.json')
if verified['status']!='Passed':raise RuntimeError('Complete media verification required')
for item in verified['videos'].values():
    if sha(media(item['path']))!=item['sha256']:raise RuntimeError('Verified video changed')
labels=['同角度 · 中性闭口','同角度 · 极轻闭口微笑','轻微转角 A','轻微转角 B','近景 · 中性','近景 · 微笑']
keyframes=[dict(label=labels[i-1],path=s[f'keyframe{i}Path'],selectedForPilot=i in [1,2,5],
    note=('本轮用于小样 · 身份与质感待人工复核' if i in [1,2,5] else
          '转角超过预期，保留结果供对照，未用于连续动作' if i==3 else
          '保留候选，未选入本轮视频')) for i in range(1,7)]
def moments(label,frames,fps):
    lookup={m['frame']:m.get('faceCompare',m['path']) for m in verified['comparisons'][label]}
    return [dict(label=f'{i/fps:.3f} 秒',frame=i,compare=lookup[i]) for i in frames]
groups=[
    dict(key='h3',title='首尾帧动作',seconds=124/24,frames=124,fps=24,
        note='两版均为本轮新生成，同一首帧、提示词、种子、模型与规格。右侧增加目标尾帧约束；请看收尾表情、身份和中间运动。',
        before=dict(title='仅首帧 · 新生成基线',path=s['h3BaselinePath'],spec='H3原生864×480 · 24FPS · 124帧'),
        after=dict(title='首尾双帧 · 本轮实验',path=s['h3ControlledPath'],spec='原生864×480 · 24FPS · 首尾帧约束'),
        moments=moments('h3',[0,30,61,92,123],24)),
    dict(key='acting',title='近景表演',seconds=2,frames=48,fps=24,
        note='左侧为上一轮自有生成素材；右侧把它的动作驱动到本轮新关键帧。它不是新真人表演。两版保持2秒时长，统一24FPS展示；观察外观与时序，口型准确性仍需人工判断。',
        before=dict(title='既有近景 · 对照输入',path=s['actingOriginalComparePath'],spec='旧task1293取2秒 · 统一720p/24FPS'),
        after=dict(title='新关键帧＋本地表演重演',path=s['actingNewComparePath'],spec='LivePortrait原生1024×576/25FPS · 转24FPS展示'),
        moments=moments('acting',[0,12,24,36,47],24)),
    dict(key='qhd',title='QHD精修',seconds=2,frames=48,fps=24,
        note='同一段本轮表演结果，右侧进行SeedVR2逐帧时序修复与超分。QHD为后期输出，不代表原生2K或恢复真实毛孔。',
        before=dict(title='本轮表演 · 精修前',path=s['actingNewComparePath'],spec='1280×720 · 24FPS · 48帧'),
        after=dict(title='本轮表演 · QHD精修',path=s['qhdPath'],spec='2560×1440 · 24FPS · 48帧 · 强度0.30'),
        moments=moments('qhd',[0,12,24,36,47],24))]
value=dict(intro='六张新关键帧、首尾帧动作对照、两秒近景重演与QHD对照已完成技术核验。请观看比较身份、细节和自然度。',
    reference=s['femaleReference'],keyframes=keyframes,groups=groups,technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked')
write(ROOT/'web/public/visual-validation.json',value)
for name in ['visual-validation.html','visual-validation.json']:
    shutil.copy2(ROOT/'web/public'/name,ROOT/'web/dist'/name)
    if sha(ROOT/'web/public'/name)!=sha(ROOT/'web/dist'/name):raise RuntimeError('Preview deployment differs')
write(FOLDER/'preview-publication.json',dict(status='Passed',url='http://127.0.0.1:18080/visual-validation.html',
    metadataSha256=sha(ROOT/'web/dist/visual-validation.json'),htmlSha256=sha(ROOT/'web/dist/visual-validation.html')))
print('http://127.0.0.1:18080/visual-validation.html',flush=True)

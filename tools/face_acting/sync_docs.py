"""Bounded authoritative progress updates; retain every previous document body."""
import argparse
import re
from run import ROOT,FOLDER,read,write

parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['active','final'],default='active');args=parser.parse_args()
state=read(FOLDER/'run.json');marker='face-acting-20261024'
if args.phase=='active':
    text=('2026-10-24：用户已批准按“参考脸校正→两秒原声对白→逐镜头肤质/2K→十秒三镜头”顺序纯本地实施。'
          '项目37，三张女主表情参考经两次定向修复，选择第三轮轻微闭口版本；男主修复眼部重叠后用柔化遮罩合成。'
          '当前按Data/FaceActing20261024/run.json与已登记任务ID续接，不能重复提交。技术验收尚未完成，发布Blocked；'
          '保留原1263/1268/1281及四句原声，口型/表情本轮允许重新生成并复核。')
else:
    if state.get('stage')!='ReadyForUserPreview':raise RuntimeError('Final delivery not verified')
    text=(f'2026-10-24：项目{state["projectId"]}同人物参考/表情重建已交付，最终任务{state["finalTaskId"]}实际2560×1440/24FPS/240帧/10秒。'
          '两秒原声短测、三镜头重生成、逐镜头SeedVR2与原AAC完整接回已执行；技术Passed，人物自然度与口型仍待用户复核，发布Blocked。'
          '恢复Data/FaceActing20261024/run.json为ReadyForUserPreview，只核验、不重复生成；原版、旧2K和旧肤质小样保留。')
documents=['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
for name in documents:
    path=ROOT/name;body=path.read_text(encoding='utf-8-sig')
    clean=re.sub(r'<!-- '+marker+r':start -->[\s\S]*?<!-- '+marker+r':end -->\n\n?','',body)
    before=(FOLDER/'source-before'/name).read_text(encoding='utf-8-sig')
    if clean!=before:raise RuntimeError('Unrelated document body changed: '+name)
    link='FACE_ACTING_20261024.md' if name.startswith('docs/') else 'docs/FACE_ACTING_20261024.md'
    path.write_text(f'<!-- {marker}:start -->\n> {text} 见[本轮记录]({link})。\n<!-- {marker}:end -->\n\n'+clean,encoding='utf-8')
if args.phase=='active':
    (ROOT/'docs/FACE_ACTING_20261024.md').write_text('# 同人物参考与表情重建\n\n'+text+'\n\n'
      '本轮复用现有RealVisXL V5 FP16、Wan2.1 I2V Q4、InfiniteTalk Multi Q8、LightX2V及SeedVR2 3B FP8。'
      '无新模型下载或云推理。视频原生832×480/25FPS，8步、57帧窗口，2K为后期修复超分。'
      '三张参考为同一三分之四角度的表情对照，未声称完成正脸或其他未展示视角的身份验证。\n\n'
      '原声、台词、时序保持；脸部像素/口型/表演重新生成，不能沿用上一轮“原嘴部像素不变”的说法。'
      '旧版仅作为输入/对比，不冒充新生成片段。实际任务与每轮失败记录位于Data/FaceActing20261024。\n',encoding='utf-8')
write(FOLDER/'documentation-verification.json',dict(status='Passed',phase=args.phase,preservedBodies=documents))
print('Updated bounded authoritative progress blocks; prior bodies preserved',flush=True)

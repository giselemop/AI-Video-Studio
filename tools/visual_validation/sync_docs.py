"""Add an auditable in-progress/completion entry, preserving all previous project notes."""
from run import ROOT,FOLDER,Run,read,write
import shutil
run=Run('http://127.0.0.1:18081',FOLDER/'run.json')
start='<!-- visual-validation-20261024:start -->';end='<!-- visual-validation-20261024:end -->'
status=run.state.get('stage','Preparing')
complete=status=='ReadyForUserPreview' and (FOLDER/'final-environment-verification.json').is_file()
text=(f'{start}\n> 2026-10-24：用户批准纯本地画面小验证包，项目{run.state.get("projectId","待建立")}，当前阶段{status}。'
      '保留旧模型、旧工作流与成片，冻结源SHA；新增Klein关键帧、H3首尾帧实验及LivePortrait参考表演分支，GPU并发1。'
      '当前仍在模型准备/逐项生成验收，不能称成片完成。恢复先读Data/VisualValidation20261024/run.json，按已登记任务续接，禁止重复提交。'
      '详见[执行记录](docs/VISUAL_VALIDATION_20261024.md)。\n'+end+'\n\n')
if complete:
    text=(f'{start}\n> 2026-10-24画面小验证包已交付，项目{run.state["projectId"]}。六张新Klein关键帧、H3首帧/首尾双帧动作对照、两秒LivePortrait重演及选片QHD对照已完成。'
          '文件技术与真实页面验收Passed；身份、自然度和画面偏好NeedReview，发布Blocked。LP使用旧自有生成素材驱动，不是新真人表演；QHD为后期超分。'
          '旧模型元数据与冻结原片SHA保全，原队列已恢复此前状态。恢复Data/VisualValidation20261024/run.json，仅核验，不重复生成。'
          '见[执行与验收记录](docs/VISUAL_VALIDATION_20261024.md)，[本机对比](http://127.0.0.1:18080/visual-validation.html)。\n'+end+'\n\n')
names=['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
for name in names:
    path=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(path,backup)
    before=path.read_text(encoding='utf-8-sig')
    if start in before:
        a=before.index(start);b=before.index(end,a)+len(end);before=before[:a]+before[b:].lstrip('\r\n')
    entry=text.replace('(docs/VISUAL_VALIDATION_20261024.md)','(VISUAL_VALIDATION_20261024.md)') if name.startswith('docs/') else text
    path.write_text(entry+before,encoding='utf-8')
print(('Completed validation note' if complete else 'In-progress recovery note')+' added; prior project history preserved')

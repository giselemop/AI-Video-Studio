"""Authoritative Chinese recovery status, preserving all prior notes."""
from run import *
s=read(FOLDER/'run.json');complete=s.get('completed',False)
start='<!-- dialogue-visual-20261025:start -->';end='<!-- dialogue-visual-20261025:end -->'
text=(start+'\n> 2026-10-25：项目40十秒对话画面升级，阶段'+s['stage']+'。'
      +('已完成，技术Passed；内容NeedReview，发布Blocked。原四句对白/声轨/字幕、53/96帧切点和旧版本保留，原队列恢复。新对比：http://127.0.0.1:18080/dialogue-visual.html。' if complete else
        '按03:35约定恢复，纯本地、GPU并发1；保留原声、字幕、切点和既有版本，尚未最终验收。')
      +'恢复Data/DialogueVisual20261025/run.json，先查已登记任务，禁止重复提交；见[执行记录](docs/DIALOGUE_VISUAL_20261025.md)。\n'+end+'\n\n')
for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
    path=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(path,backup)
    old=path.read_text(encoding='utf-8-sig')
    if start in old:
        a=old.index(start);b=old.index(end,a)+len(end);old=old[:a]+old[b:].lstrip('\r\n')
    entry=text.replace('(docs/DIALOGUE_VISUAL_20261025.md)','(DIALOGUE_VISUAL_20261025.md)') if name.startswith('docs/') else text
    path.write_text(entry+old,encoding='utf-8')
print('Recovery status synchronized')

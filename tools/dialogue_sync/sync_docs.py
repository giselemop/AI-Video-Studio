"""Keep Chinese recovery state and compatibility entries current, additively."""
from run import *
s=read(FOLDER/'run.json');complete=s.get('completed',False)
start='<!-- dialogue-sync-20261025:start -->';end='<!-- dialogue-sync-20261025:end -->'
entry=(start+'\n> 2026-10-25：项目'+str(s['projectId'])+'口型与双人回应小样，阶段'+s['stage']+'。'
    +('已完成，技术Passed，内容NeedReview，发布Blocked；新对比http://127.0.0.1:18080/dialogue-sync.html。' if complete else '执行中，未完成验收；仅两段短样本，音频条件驱动、当前人物区域绑定与原声时间轴保留。')
    +'全程本地、GPU并发1，项目40十秒版及模型保留。恢复Data/DialogueSync20261025/run.json，先查已登记任务，禁止重复提交。见[执行记录](docs/DIALOGUE_SYNC_20261025.md)。\n'+end+'\n\n')
for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
    path=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(path,backup)
    old=path.read_text(encoding='utf-8-sig')
    if start in old:
        a=old.index(start);b=old.index(end,a)+len(end);old=old[:a]+old[b:].lstrip('\r\n')
    text=entry.replace('(docs/DIALOGUE_SYNC_20261025.md)','(DIALOGUE_SYNC_20261025.md)') if name.startswith('docs/') else entry
    path.write_text(text+old,encoding='utf-8')
print('Additive recovery documents synchronized')

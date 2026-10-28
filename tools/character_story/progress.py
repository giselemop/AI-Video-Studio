"""Live phase recorder; never submits a generation or approves content."""
from pathlib import Path
import sys,json,datetime,re,subprocess,requests
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,OUT,write,mysql
MARK='character-story-20261027'
def note(path,body):
    start='<!-- '+MARK+':start -->';end='<!-- '+MARK+':end -->';old=path.read_text(encoding='utf-8-sig')
    old=re.sub(re.escape(start)+r'.*?'+re.escape(end)+r'\s*','',old,flags=re.S)
    path.write_text(start+'\n'+body+'\n'+end+'\n\n'+old,encoding='utf-8')
def run():
    ready=requests.get('http://127.0.0.1:18080/api/character-story/readiness',timeout=30).json()
    pilot=json.loads((OUT/'pilot.json').read_text(encoding='utf-8'));state=json.loads((OUT/'run.json').read_text(encoding='utf-8'))
    if not (OUT/'run-before-resume.json').exists():write(OUT/'run-before-resume.json',state)
    state.update(stage='RuntimeVerification',completed=False,technicalOverall='Running',schema=ready,resumedAt=state.get('resumedAt',datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()))
    if ready['ready']:state.pop('blocker',None)
    tasks=[dict(slot=slot,kind=k,id=t['id'],status=t.get('status'),repairAttempt=t.get('repairAttempt',0)) for slot,v in pilot['slots'].items() for k in ['Keyframe','Video'] for t in v.get(k+'History',[])+([v[k]] if v.get(k,{}).get('id') else [])]
    baseClips=sum(t['kind']=='Video' and t['repairAttempt']==0 for t in tasks)
    state.update(projectId=pilot.get('projectId'),episodeId=pilot.get('episodeId'),newGpuTasks=len(tasks),newStoryBaseClips=baseClips)
    state['phases'].update(schema='Passed' if ready['ready'] else 'Blocked',reference_policy='Passed',casting_persistence='Passed' if pilot.get('episodeCastId') else 'Pending',story_keyframe_gpu='Running',four_clip_acceptance='Running')
    write(OUT/'run.json',state);write(OUT/'runtime-progress.json',dict(schema=ready,tasks=tasks,contentReview='NeedReview',publication='Blocked'))
    write(OUT/'schema-after-admin.json',dict(status='Passed' if ready['ready'] else 'Blocked',readiness=ready,reviewColumns=mysql('SHOW COLUMNS FROM character_reference_reviews;'),reviewForeignKeys=mysql("SELECT CONSTRAINT_NAME,REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='character_reference_reviews' AND REFERENCED_TABLE_NAME IS NOT NULL;"),oldVersionsCount=mysql("SELECT COUNT(*) FROM entity_versions WHERE entity_type='Character';")))
    report=ROOT/'docs/CHARACTER_STORY_ACCEPTANCE_20261027.md'
    if not (OUT/'acceptance-before-resume.md').exists():(OUT/'acceptance-before-resume.md').write_text(report.read_text(encoding='utf-8'),encoding='utf-8')
    body=f'> 2026-10-27继续实施：管理员完成010/011后，本机readiness已核验为{ready["status"]}，原结构阻断已解除。项目{pilot.get("projectId")}、集{pilot.get("episodeId")}已固定林安版本4、周言版本5及原Shot计划。新GPU任务当前{len(tasks)}个（包含失败素材的定向修复），基础视频{baseClips}/4，真实验证进行中；内容仍NeedReview、发布Blocked，未宣称完整验收通过。最新结果见Data/CharacterStory20261027/runtime-progress.json。'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:note(ROOT/name,body)
    note(report,body+' 以下保留前一阶段及历史阻断记录，最终结果将在本阶段验收后更新。')
    print('Live state recorded; schema ready, actual tasks '+str(len(tasks))+', content remains NeedReview.')
if __name__=='__main__':run()

"""Update this run's bounded documentation block from actual persisted evidence."""
import json
import re
from run import ROOT,FOLDER


def main():
    state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
    completed=sum(bool(state.get(f'shot{n}VideoPath')) for n in range(1,7))
    latest=max((state.get(f'shot{n}TaskId') or 0) for n in range(1,7))
    if state['stage']=='ReadyForUserPreview':
        delivery=json.loads((FOLDER/'delivery-verification.json').read_text(encoding='utf-8'))
        playback=json.loads((FOLDER/'browser-final-playback.json').read_text(encoding='utf-8'))
        if delivery['status']!='Passed' or playback['status']!='Passed':raise RuntimeError('Final evidence is incomplete')
        message=(f'2026-10-23交付：项目32男女双人客厅剧情，最终任务{state["assemblyTaskId"]}实际1280×720/24FPS/744帧/31秒，'
            '六段H3原生1376×768/20步、实际尾帧续接，11句Qwen男女声原速完整接入。完整解码、逐句音轨比对和真实浏览器完整播放Passed。'
            '开场改为回家后落座，衣服/站位跟随实际新角色；精细肢体与口型仍NeedReview，发布Blocked。'
            '恢复Data/DouyinReference20261023/run.json为ReadyForUserPreview，仅核验现有文件/任务，不自动重生成。')
    else:
        message=(f'2026-10-23执行中：项目32按抖音《午后小日常》复刻男女双人客厅剧情。原片实测1280×720/30FPS/30.7秒并已核对画面/字幕；'
            f'11句Qwen男女声1219–1229完成，H3素材已完成{completed}/6段，最近视频任务{latest}，阶段{state["stage"]}。'
            '选首帧1216并跟随实际衣服/位置，开场为回家后已落座；1217/1218修复和原要求未满足记录保留。'
            '计划31秒/720p展示版，尚未完成本轮最终验收；内容NeedReview、发布Blocked。'
            'GitHub方案已研究，MultiTalk/InfiniteTalk完整路线尚未安装。此前1215单人校园片不算此需求完成。'
            '恢复Data/DouyinReference20261023/run.json，先核已有任务，结果未决时不重复提交。')
    names=['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
    for name in names:
        path=ROOT/name
        target='DOUYIN_REFERENCE_20261023.md' if name.startswith('docs/') else 'docs/DOUYIN_REFERENCE_20261023.md'
        block='<!-- douyin-reference-20261023:start -->\n> '+message+'见[本轮记录]('+target+')。\n<!-- douyin-reference-20261023:end -->'
        old=path.read_text(encoding='utf-8-sig')
        pattern=r'<!-- douyin-reference-20261023:start -->.*?<!-- douyin-reference-20261023:end -->'
        updated=re.sub(pattern,lambda match:block,old,count=1,flags=re.S) if re.search(pattern,old,flags=re.S) else block+'\n\n'+old
        if updated!=old:path.write_text(updated,encoding='utf-8')
    path=ROOT/'docs/DOUYIN_REFERENCE_20261023.md'
    old=path.read_text(encoding='utf-8')
    if state['stage']=='ReadyForUserPreview':
        old=old.replace('2026-10-23，执行中。技术尚未完成，内容 NeedReview，发布 Blocked。',
            '2026-10-23，已交付可观看样片。技术 Passed，内容 NeedReview，发布 Blocked。')
    rows=[]
    for n in range(1,7):
        metrics=state.get(f'shot{n}TaskMetrics',{})
        rows.append(f'| {n} | {state["shotPlan"][n-1]["title"]} | {state.get(f"shot{n}TaskId", "未提交")} | '+
            (f'Succeeded，{metrics.get("durationMs",0)/1000:.3f}秒' if state.get(f'shot{n}VideoPath') else '执行中/尚未提交')+' |')
    progress='<!-- execution-evidence:start -->\n## 实际执行进度\n\n'+message+'\n\n| 段 | 剧情 | 任务ID | 实际状态 |\n| --- | --- | --- | --- |\n'+'\n'.join(rows)+'\n<!-- execution-evidence:end -->'
    pattern=r'<!-- execution-evidence:start -->.*?<!-- execution-evidence:end -->'
    updated=re.sub(pattern,lambda match:progress,old,count=1,flags=re.S) if re.search(pattern,old,flags=re.S) else old+'\n\n'+progress+'\n'
    if updated!=old:path.write_text(updated,encoding='utf-8')
    print(json.dumps(dict(stage=state['stage'],completedSourceShots=completed,latestTask=latest,documentsUpdated=True)),flush=True)


if __name__=='__main__':main()

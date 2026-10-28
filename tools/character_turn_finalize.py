"""Record the checked outcome without regenerating or approving content."""
import datetime,json,msvcrt,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from character_turn_repair import Repair,ROOT,DATA,OUT,sha,write,mysql

def run():
 with (OUT/'controller.lock').open('a+b') as lock:
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);r=Repair();a=r.state['attempts'][-1];folder=OUT/f'attempt-{a["attempt"]}'
    checks=json.loads((folder/'media-checks.json').read_text(encoding='utf-8'));visual=json.loads((folder/'visual-inspection.json').read_text(encoding='utf-8'));browser=json.loads((folder/'browser-playback.json').read_text(encoding='utf-8'));ui=json.loads((folder/'browser-ui-checks.json').read_text(encoding='utf-8'));trace=json.loads((folder/'task-trace.json').read_text(encoding='utf-8'))
    assert checks['status']=='Passed' and visual['status']=='Passed' and browser['status']=='Passed' and ui['status']=='Passed'
    assert not visual['humanApproved'] and visual['identityScore'] is None and all(x['ended'] for x in browser['videos'])
    assert sha(DATA/a['assetPath'])==a['sha256'] and sha(DATA/r.state['baseVideoPath'])==r.state['baseVideoSha256']
    assert sha(DATA/'CharacterSinglePreview20261027/run.json')==r.state['baseRunSha256'] and sha(DATA/'CharacterScene20261027/run.json')==r.state['sceneCheckpointSha256']
    assert sha(ROOT/'web/public/character-turn-repair.html')==sha(ROOT/'web/dist/character-turn-repair.html')
    countBefore=int(mysql('SELECT COUNT(*) FROM generation_tasks;'));r.submit(a['attempt']);countAfter=int(mysql('SELECT COUNT(*) FROM generation_tasks;'));assert countBefore==countAfter
    write(folder/'idempotency-check.json',dict(status='Passed',taskId=a['taskId'],taskCountBefore=countBefore,taskCountAfter=countAfter,newSubmissions=0))
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True,encoding='utf-8').strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,encoding='utf-8').strip()
    nativeAudio='有' if checks['nativeAudioPresent'] else '无'
    report=f'''# 林安左转回正定向试片（2026-10-27）

用户要求继续优化原试片1550中不明显的左转与回正，并保持人物和服装一致。此次生成一个新候选，实际动作试片检查 **Passed**；技术与浏览器播放 **Passed**；人物一致性与自然度仍为 **NeedReview**，发布 **Blocked**。

- [原片与本次试片对照](http://127.0.0.1:18080/character-turn-repair.html)
- 原项目52 / 原任务1550；本轮项目{r.state['projectId']} / 新任务{a['taskId']}，定向修复第{a['attempt']}次。
- 由业务队列执行，GPU并发1；真实Comfy执行 `{trace['comfyPromptId']}`。任务1550已成功且在新任务的 `dependency_task_id` 中记录为来源；本次提交前也核验了原任务状态，来源字段不应被理解为额外的跨项目调度保证。
- 人物19、旧版人物版本3、参考36；源参考当前Approved，人物版本及新视频的最终人工内容仍需复核。
- 图像源SHA256 `{r.state['source']['sha256']}`；原视频SHA256 `{r.state['baseVideoSha256']}`；新视频SHA256 `{a['sha256']}`。
- 新片文件：`{a['assetPath']}`，原生864×480、24 FPS、124帧，时长{checks['duration']}秒；20采样步。H3服务记录生成耗时{trace['durationMs']/1000:.3f}秒，采样显存峰值{trace['vramPeakMiB']}MiB。

## 实际修改与观察

上次提示词将转头限制为几度；本次明确要求整个头部朝画面左侧转动、停顿并返回镜头。继续使用相同首帧、人物版本、H3工作流、种子{a['request']['seed']}和视频规格，以便比较。新提示词移除上次单独的眨眼要求，增加单人面部与服装稳定约束，并没有沿用原有安静环境/无音乐的完整声音描述；新片{nativeAudio}原生音频，试听页默认静音，声音内容未验收。

实际25个采样时点与原图检查：{visual['note']}

本次动作通过的是“左转并回正”的试片检查。实际转幅接近侧脸，比提示中的20–25度更大；该角度的面部细节和自然度仍需人工核对。没有计算或宣称身份分数，也不凭同一seed保证身份。近景未包含全部手脚或鞋子，无法验收这些部位。

## 验证与证据

- 19项真实文件与来源检查Passed：业务任务与来源ID、Comfy执行记录、人物版本、实际首帧哈希、工作流、实际参数、原生输出哈希、FFprobe、124帧全片解码、HTTP Range、历史媒体及原待审检查点。
- 原片与新片分别在真实页面完整播放至5.167秒，两个播放器均无媒体错误，浏览器控制台无错误；人物原图放大加载1536×864。
- 按实际视频提取25个时点，证据 `attempt-{a['attempt']}\\contact-sheet.jpg`、`attempt-{a['attempt']}\\frames\\`；检查截图 `screenshots\\comparison-playing.png` 和 `screenshots\\reference-zoom.png`。
- 请求、预检、任务、Comfy图与历史、媒体检查、FFprobe、浏览器及检查记录均位于 `C:\\install\\AI\\Data\\CharacterTurnRepair20261027\\attempt-{a['attempt']}`。
- 同一已登记修复请求重复调用只读取现有任务，不生成新任务。最多允许两个定向修复，本次第1次已满足动作检查，没有提交第2次。

原1550视频及完成检查点、原双人场景待审检查点SHA256保持不变。没有修改审核状态、自动批准、生成新人物图、创建新人物版本、下载模型、调用付费云服务、公开发布或执行数据库迁移。

## 恢复与分支

恢复入口 `C:\\install\\AI\\Data\\CharacterTurnRepair20261027\\run.json`，当前最终完成后 `completed=true`；恢复时只核验已有任务，不重复提交。控制器 `tools/character_turn_repair.py`、真实来源验收 `tools/character_turn_verify.py`、对照页生成器 `tools/character_turn_page.py` 与模板保留在项目中。共享工作区已有未提交变更；本次不清理、重置或覆盖其他成果。分支 `{branch}`，HEAD `{head}`，未新增Git提交或推送。
'''
    reportPath=ROOT/'docs/CHARACTER_TURN_REPAIR_20261027.md';reportPath.write_text(report,encoding='utf-8')
    marker='character-turn-repair-20261027';brief=f'> 2026-10-27：林安左转回正定向修复已交付，原任务1550、新项目{r.state["projectId"]}/任务{a["taskId"]}。沿用人物版本3、已批准参考36、同H3工作流和种子；原生864×480/24FPS/124帧。19项媒体来源及两个真实浏览器完整播放Passed；25时点试片检查可见左转、停顿、回正，转幅接近侧脸，人物细节和自然度NeedReview、发布Blocked。仅1次定向修复，无新模型/新人物版本/人工批准/云调用；原片及双人剧情待审检查点保留。恢复Data/CharacterTurnRepair20261027/run.json，completed=true禁止重复提交。'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
        path=ROOT/name;old=path.read_text(encoding='utf-8-sig');link='CHARACTER_TURN_REPAIR_20261027.md' if name.startswith('docs/') else 'docs/CHARACTER_TURN_REPAIR_20261027.md'
        block='<!-- '+marker+':start -->\n'+brief+f' [验收报告]({link})、[视频对照](http://127.0.0.1:18080/character-turn-repair.html)。\n<!-- '+marker+':end -->'
        pattern='<!-- '+marker+':start -->[\\s\\S]*?<!-- '+marker+':end -->';updated=re.sub(pattern,lambda _:block,old) if re.search(pattern,old) else block+'\n\n'+old
        if path.read_text(encoding='utf-8-sig')!=old:raise RuntimeError('Concurrent documentation edit; inspect before continuing: '+name)
        path.write_text(updated,encoding='utf-8')
    r.state.update(stage='ReadyForUserPreview',completed=True,technical='Passed',previewInspection='Passed',contentReview='NeedReview',publication='Blocked',finishedAt=datetime.datetime.now().astimezone().isoformat());r.save()
    write(OUT/'delivery.json',dict(status='Passed',scope='Technical and targeted action preview; not human content approval',taskId=a['taskId'],baseTaskId=1550,projectId=r.state['projectId'],videoPath=str(DATA/a['assetPath']),sha256=a['sha256'],report=str(reportPath),mediaChecks=len(checks['checks']),contentReview='NeedReview',publication='Blocked',humanApprovals=0,newModels=0,newCloudCalls=0,attemptCount=len(r.state['attempts'])))
    print(f'Task {a["taskId"]} delivered after {len(checks["checks"])} media checks and real browser playback. Human content remains NeedReview.')
if __name__=='__main__':run()

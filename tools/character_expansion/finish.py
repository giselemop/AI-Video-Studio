"""Evidence-gated completion of the five-character image expansion."""
import datetime
import re
import subprocess
from batch import Batch,PEOPLE,SLOTS,FOLDER,ROOT,read,write,sha

def update(path,text):
    path=ROOT/path;source=path.read_text(encoding='utf-8-sig');start='<!-- character-expansion-five-20261026:start -->';end='<!-- character-expansion-five-20261026:end -->';block=start+'\n'+text.rstrip()+'\n'+end
    if start in source:source=re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda _:block,source,flags=re.S)
    else:source=block+'\n\n'+source
    path.write_text(source,encoding='utf-8')

def finish():
    r=Batch();r.access();r.preserve()
    if r.state['stage'] not in ['ReferencePacksReady','ReadyForUserPreview']:raise RuntimeError('Capture five inspected packs first')
    verification=read(FOLDER/'verification.json');browser=read(FOLDER/'browser-checks.json');review=read(FOLDER/'references-review.json')
    if not all(item['status']=='Passed' for item in [verification,browser,review]):raise RuntimeError('Media, API, browser and selected-image inspection must pass')
    if len(verification['outputs'])!=45 or browser['newCharacterCards']!=5 or browser['reviewPageLoadedPhotos']!=45:raise RuntimeError('Require all five new cards and 45 native photos')
    if browser.get('consoleErrors'):raise RuntimeError('Browser errors remain')
    q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json();runtime=r.api('/api/minimax/local/status')['queue']
    if q['queue_running'] or q['queue_pending'] or runtime['activeTasks'] or runtime['paused'] or runtime['gpuConcurrency']!=1:raise RuntimeError('Require idle enabled primary worker and GPU concurrency one')
    samples=read(FOLDER/'resource-samples.json')
    if not samples or max(s['running'] for s in samples)>1:raise RuntimeError('Observed GPU concurrency exceeds one')
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip();head=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()
    taskcounts={status:sum(item.get('status')==status for item in r.state['tasks'].values()) for status in ['Succeeded','Failed','Cancelled']}
    summary=dict(projectId=r.state['projectId'],technical='Passed',contentReview='NeedReview',publication='Blocked',characters=5,references=45,width=1536,height=864,newVideoTasks=0,newCloudCalls=0,newModels=0,gpuConcurrency=1,verificationChecks=len(verification['checks']),browserChecks=len(browser['checks']),taskStatusCounts=taskcounts,branch=branch,head=head,sampledMaxVramUsedMiB=max(s['usedMiB'] for s in samples),observedMaxComfyRunning=max(s['running'] for s in samples),oldVersionsPreserved=True,completedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write(FOLDER/'acceptance-summary.json',summary)
    names='、'.join(p['name'] for p in PEOPLE)
    short=f"> 2026-10-26：按已认可九图标准新增{names}五位虚构成年人物，项目{r.state['projectId']}，每人3近景＋6全身，共45张1536×864参考已入库。{summary['verificationChecks']}项媒体/来源/API检查、{summary['browserChecks']}项实际浏览器检查Passed。原林安/周言与全部旧版本保留；本轮未生成新视频，无新模型或云调用，GPU并发1。技术Passed，人物观感NeedReview，发布Blocked。恢复Data/CharacterExpansionFive20261026/run.json，completed=true仅核验不重提。见[五人预览](http://127.0.0.1:18080/character-library-five.html)、[人物库](http://127.0.0.1:18080/#character-library)、[执行记录](docs/CHARACTER_EXPANSION_FIVE_20261026.md)。"
    for path in ['项目状态.md','待办事项.md','变更记录.md']:update(path,short)
    english=f"> 2026-10-26: Added five fresh fictional adult characters in project{r.state['projectId']}, each with 3 face close-ups and 6 full-body references at 1536x864 (45 selected photos). {summary['verificationChecks']} media/provenance/API checks and {summary['browserChecks']} browser checks Passed. Technical Passed, content NeedReview, publication Blocked. Original two characters, old snapshots and media preserved. No new video/cloud/model tasks; GPU concurrency1. Data/CharacterExpansionFive20261026/run.json completed=true prevents duplicate generation. [Acceptance](docs/CHARACTER_EXPANSION_FIVE_20261026.md)."
    for path in ['PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:update(path,english)
    update('docs/ACCEPTANCE_REPORT.md',short.replace('(docs/CHARACTER_EXPANSION_FIVE_20261026.md)','(CHARACTER_EXPANSION_FIVE_20261026.md)'))
    update('docs/FIX_HISTORY.md','> 五位人物扩充：初始RealVis身份草图中出现配饰、衣领颜色偏差、头顶过紧或露齿笑，保留原草图，再以同一面孔做定向Klein整理。统一长发说明影响三个短发/低发髻人物，第二次修复去掉该说明并明确原始发型；每个头部位置最多两次定向修复，检查后才派生全身和侧面。所有候选与原生执行历史保留，选片与内容检查单独记录。既有应用代码、工作流、模型权重未更改。见[本轮记录](CHARACTER_EXPANSION_FIVE_20261026.md)。')
    rows='\n'.join('| '+p['name']+' | '+p['ageSetting']+' | '+str(r.state['people'][p['key']]['characterId'])+' | '+str(r.state['people'][p['key']]['versionId'])+' / v'+str(r.state['people'][p['key']]['version'])+' | 3 + 6 |' for p in PEOPLE)
    detail=f"""## 最终交付与验收

技术Passed，人物偏好与各角度身份观感NeedReview，发布Blocked。分支`{branch}`，HEAD `{head}`，未提交或推送；原脏工作保留。本轮应用后端/前端逻辑、工作流、模型权重和数据库结构没有变化，不需要重新部署应用。

| 人物 | 设定 | 角色ID | 库版本ID / 人物版本 | 近景 + 全身 |
| --- | --- | --- | --- | --- |
{rows}

按既有3近景＋6全身标准，共45张1536×864图片。新增独立身份先经真实RealVis文生图建立，保留所有原稿；Klein定向整理衣领、配饰、头顶与表情，再以同一正面身份和全身造型基准派生左右方向。前侧/侧面的角度为近似朝向，不是三维标定。

本轮{summary['verificationChecks']}项媒体/来源/API检查Passed：每张可完整解码，原生尺寸正确，DB任务与归档Comfy成功历史对应，实际执行提示词和实际拷贝身份/造型输入SHA符合，原生输出与登记副本SHA相同，HTTP Range有效，45个视角/景别精确解析。缺景别、缺图、重复/不完整参考包拒绝；相同版本保存去重；验收没有创建GPU任务。

实际浏览器{summary['browserChecks']}项Passed：人物库共7个人物，新5人均9/9；各9图可查看，单图可放大，预览页45张原图可加载，页面无控制台错误。见browser-checks.json及截图。

GPU并发采样最高{summary['observedMaxComfyRunning']}，采样使用显存最高{summary['sampledMaxVramUsedMiB']}MiB；这些是观察采样，不能当作精确单任务峰值。没有云调用、模型下载或新视频任务；没有据此宣称五个人的动态表现已验收。

原林安/周言、五个旧库快照及既有图片/视频全部保持SHA不变。备份backup/20261026_215405。运行检查点Data/CharacterExpansionFive20261026/run.json已completed=true；恢复脚本只核验不重复提交。selection.json保留选片，原稿及不合格候选继续保留。验收、任务回执、原生Comfy历史、来源追溯、资源采样、内容检查及预览截图均在同一Data目录。

[查看新增五人](http://127.0.0.1:18080/character-library-five.html) · [打开人物库](http://127.0.0.1:18080/#character-library)
"""
    path=ROOT/'docs/CHARACTER_EXPANSION_FIVE_20261026.md';source=path.read_text(encoding='utf-8');source=source.split('## 最终交付与验收')[0].replace('当前实施中。','当前已完成技术验收，供用户查看与选择。').rstrip()+'\n\n'+detail;path.write_text(source,encoding='utf-8')
    files=[path for path in (ROOT/'tools/character_expansion').iterdir() if path.is_file()]+[ROOT/'web/public/character-library-five.html',ROOT/'web/dist/character-library-five.html',ROOT/'docs/CHARACTER_EXPANSION_FIVE_20261026.md']
    write(FOLDER/'source-manifest.json',[dict(path=str(path.relative_to(ROOT)).replace('\\','/'),sha256=sha(path)) for path in files])
    r.save(stage='ReadyForUserPreview',completed=True,technical='Passed',contentReview='NeedReview',publication='Blocked')
    print('Five-character expansion finished after all acceptance gates; checkpoint is read-only',flush=True)
if __name__=='__main__':finish()

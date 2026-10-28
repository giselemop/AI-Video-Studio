"""Close only this bounded repair; preserve old failed-content evidence and media."""
from run import *
import py_compile,re
def main():
    r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Preserved; no new tasks');return
    r.access();r.preserve();s=r.state
    for name in ['sample-pixel-checks.json','sample-review.json','final-verification.json','caption-render-checks.json','admission-checks.json','browser-review.json']:
        if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Acceptance incomplete: '+name)
    browser=read(FOLDER/'browser-review.json')
    if not browser['normalBothEnded'] or not browser['halfBothEnded'] or not browser['stepCheckPassed'] or browser['consoleErrors']:raise RuntimeError('Browser evidence incomplete')
    if sha(media(browser['screenshot']))!=browser['screenshotSha256']:raise RuntimeError('Browser screenshot changed')
    tasks=[]
    for p in FOLDER.glob('task-*.json'):
        t=read(p)['task'];live=r.api('/api/tasks/'+str(t['id']))['task']
        if live['status']!='Succeeded' or live['projectId']!=s['projectId'] or live['resourceClass']!='CPU':raise RuntimeError('Actual CPU task incomplete')
        tasks.append(live)
    q=r.session.get('http://127.0.0.1:8188/queue').json();active=[t['id'] for t in r.api('/api/tasks?limit=500') if t['status'] in ['Running','Pending','Queued']]
    if active or q['queue_running'] or q['queue_pending']:raise RuntimeError('Active work; cannot finalize')
    write(FOLDER/'execution-summary.json',dict(status='Passed',projectId=s['projectId'],tasks=[{k:t.get(k) for k in ['id','taskType','resourceClass','status','durationMs']} for t in sorted(tasks,key=lambda t:t['id'])],newGpuTasks=0,newModels=0,cloudCalls=0,preservedFileHashes=len(s['preserved']),sourceAnchorFrameCount=151,oldProject43ContentStatus='Failed',newTargetEyeHairReview='Passed',overallActingStatus='NeedReview',publicationStatus='Blocked'))
    old=Run('http://127.0.0.1:18080',FOLDER/'original-access.json');old.access()
    for api,paused in [(r,s['pilotQueueStatus']['paused']),(old,s['originalQueueStatus']['paused'])]:api.api('/api/production/pause' if paused else '/api/production/resume',{})
    health=old.api('/api/health');a=old.api('/api/minimax/local/status')['queue']['paused'];bq=r.api('/api/minimax/local/status')['queue']['paused']
    if a!=s['originalQueueStatus']['paused'] or bq!=s['pilotQueueStatus']['paused'] or not health['database']['online'] or not health['comfy']['online'] or not health['ffmpeg']['available']:raise RuntimeError('Environment restoration failed')
    write(FOLDER/'final-environment.json',dict(status='Passed',originalQueuePaused=a,pilotQueuePaused=bq,activeTasks=[],comfyIdle=True,databaseOnline=True,comfyOnline=True,ffmpegAvailable=True))
    document(s)
    files=['server/DialogueComposeService.cs','server/GenerationQueue.DialogueComposite.cs','web/public/dialogue-eye-hair.html','web/public/dialogue-eye-hair.json','docs/DIALOGUE_EYE_HAIR_20261025.md','docs/DIALOGUE_STABLE_768_20261025.md','项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
    files += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'tools/dialogue_eye_hair').iterdir() if p.suffix in ['.py','.ps1']]
    rows=[]
    for name in files:
        p=ROOT/name
        if p.suffix=='.py':
            if p.stem in sys.stdlib_module_names:raise RuntimeError('Standard library collision')
            py_compile.compile(str(p),doraise=True)
        rows.append(dict(path=name,sha256=sha(p)))
    values=[]
    for line in (ROOT/'config/local.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('"\'')
        if re.search(r'password|token|api_?key|secret',key,re.I) and len(value)>=8:values.append(value)
    if any(any(secret in (ROOT/p).read_text(encoding='utf-8-sig') for secret in values) for p in files):raise RuntimeError('Configured secret detected; values suppressed')
    result=subprocess.run(['git','diff','--check','--',*files],cwd=ROOT,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Whitespace check failed')
    js=FOLDER/'viewer-syntax.js';js.write_text(re.search(r'<script>(.*?)</script>',(ROOT/'web/public/dialogue-eye-hair.html').read_text(encoding='utf-8'),re.S)[1],encoding='utf-8')
    subprocess.run([r'C:\Program Files\nodejs\node.exe','--check',str(js)],check=True,capture_output=True)
    deployed=Path(read(FOLDER/'deployment.json')['executable']).with_suffix('.dll');current=ROOT/'server/bin/Release/net8.0/VideoStudio.Server.dll'
    if sha(deployed)!=sha(current):raise RuntimeError('Deployed DLL differs from current build')
    write(FOLDER/'source-verification.json',dict(status='Passed',files=rows,pythonCompiled=True,viewerJavaScriptParsed=True,configuredSecretHits=0,diffCheckPassed=True,deployedDllMatchesCurrentBuild=True,deployedDllSha256=sha(deployed),branch='main',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),committed=False,pushed=False))
    r.save('ReadyForUserPreview',completed=True,technicalStatus='Passed',contentStatus='NeedReview',targetEyeHairStatus='Passed',publicationStatus='Blocked',previewUrl='http://127.0.0.1:18080/dialogue-eye-hair.html')
    print('Passed: local eye/hair repair sealed, original queues and media preserved')
def document(s):
    report=f'''# 女方侧脸眼睛和头发定向修复（2026-10-25）

用户指出项目43约7秒处女方眼睛、头发不正确。逐帧定位为7.9–8.1秒附近的强制侧脸眨眼，原内容复核 **Failed**；原先技术Passed只证明文件和时间轴，重复像素一致只证明可复现，不能证明五官、发际线正确。上轮样本内容验收漏检，此次新增连续帧与源参考区域检查。原版本和原验收历史全部保留，并追加本次纠正。

项目{s['projectId']}新版局部眼部/发际线复核和技术检查Passed；整体自然表演仍需用户复核，正式发布Blocked。全程本地CPU合成，4个实际任务1407–1410全部Succeeded，无GPU生成、无模型下载/更换、无云推理。原声、四句字幕、两个切点、原前两个镜头源及男方原表演保留。

新版：`{s['finalPath']}`，SHA256 `{s['finalSha256']}`。1366×768，24FPS，240帧，10秒。对比：http://127.0.0.1:18080/dialogue-eye-hair.html ，可定位7.917/7.958/8.000/8.042/8.083秒逐帧对比。

## 复现与原因

- 对照原参考图、人物驱动、双人合并、最终768p画面，缺陷在人像驱动输出已存在，排除最终缩放为首次引入阶段。原片未做覆盖或重新标记成功。
- 女方侧脸有头发/鼻梁遮挡，旧双眼比例与眼部残差对这张侧脸失效；native100帧测得基线眼比例1.856、修正后1.604、目标0.015，画面成为浅色眼块，未得到正常闭眼。该数值不是可信的生理眼裂测量，说明不能仅依赖该度量继续加大补偿。
- 头部/头发处于广泛的人像变形与贴回区域，移动的发缘与静态源轮廓拼接出双边。逐帧对照 `stage-comparison.png`、`final-dense-window.png` 可复现。

## 实施范围和取舍

新增独立 `dialogue-eye-hair-guard-v1` CPU合成分支，锁定已审核参考图SHA、1024×576/151帧/25FPS、女方嘴部椭圆区域和原第三句对白时段。女方双人镜头4–10秒的眼睛、头发和头部固定为原参考图，取消该镜头女方强制眨眼与头部动作；仅在原女方对白前80ms到结尾后160ms内淡入/淡出已有嘴部运动。男方保持原合成支持区域，左右人物不混合。旧模型、旧人物运行器、旧合成分支均不改写。

这是一版保守局部修复，女方头部和眼部更静。没有声称修好了自然侧脸眨眼、完整身体表演或精确音素同步。以后需要侧脸活动时，应先解决可见眼定位和发缘分割，再重新做小样，不能直接复用当前失效的双眼补偿。

## 测试和验收

1. 实际151帧合成轨迹：编码前女方嘴部之外与参考图逐像素一致，男方合成结果与原方法逐像素一致；每帧断言均执行。原生编码后眼睛/头发ROI对参考图均差小于4/255（有损编码范围），不能称为编码后像素不变。
2. 已查看女方说话与收口帧及7.83–8.33秒密集连续对照，浅色眼块和头发双边在样本中消除；嘴部发音动作保留。记录 `sample-review.json`。
3. 全片240帧不同解码帧、1366×768/24FPS/10秒、逐帧PTS检查通过；第53/96帧切点及对应源帧匹配。
4. 完整原声AAC包、解码PCM、PTS/DTS和priming完全一致；画面在最终换轨时包不变。原SRT SHA保持，四条字幕首/中/末12处渲染检查Passed。声音一致不证明细粒度口型准确。
5. 前96帧与旧版全画面、后144帧右半男方画面实际逐帧对比，平均绝对误差均小于3/255，仅包含后续有损编码差异。没有重做男方动作。
6. 真实API拒绝5个不合法合成请求（错误phase/帧数/嘴部ROI/策略/对白时段），两个旧合成分支CPU预检通过，测试没有生成任务。
7. 实际对比页正常、半速均完整播完；异常附近逐帧前进/返回、女方面部局部放大已复核，console错误0；见 `browser-review.json` 与截图。自动播放成功不能替代内容视觉检查。
8. 148个保留输入文件SHA和189个模型文件集合/大小/修改时间校验通过。原18080队列恢复未暂停，隔离18081队列恢复暂停，MySQL/ComfyUI/FFmpeg在线，无活跃任务。

证据：`C:/install/AI/Data/DialogueEyeHair20261025/`。`user-feedback.json`保留原片内容Failed与用户截图；`sample-pixel-checks.json`、`sample-review.json`、`final-verification.json`、`caption-render-checks.json`、`admission-checks.json`、`browser-review.json`、`execution-summary.json`、`final-environment.json`、`source-verification.json`分别记录边界。源码完成Python编译、JS语法、配置秘密值扫描、预期diff检查、发布DLL一致性检查。main / d6ec38d，无提交或推送，既有脏工作保留。
'''
    (ROOT/'docs/DIALOGUE_EYE_HAIR_20261025.md').write_text(report,encoding='utf-8')
    start='<!-- dialogue-eye-hair-20261025:start -->';end='<!-- dialogue-eye-hair-20261025:end -->'
    entry=start+'\n> 2026-10-25纠正：项目43女方7.9–8.1秒侧脸眼部浅色块/头发双边内容复核Failed，原技术Passed不等于画面正确。项目44保守修复已完成，1366×768/24FPS/240帧；女方双人镜头固定眼睛、头发和头部，仅保留原对白嘴部动作。目标眼发复核与技术Passed，完整自然度仍需复核，发布Blocked。原声/字幕/53与96帧切点/旧版和模型保留。对比http://127.0.0.1:18080/dialogue-eye-hair.html；恢复Data/DialogueEyeHair20261025/run.json，completed=true禁止重复提交。见[执行记录](docs/DIALOGUE_EYE_HAIR_20261025.md)。\n'+end+'\n\n'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md','docs/DIALOGUE_STABLE_768_20261025.md']:
        p=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():shutil.copy2(p,backup)
        old=p.read_text(encoding='utf-8-sig')
        if start in old:
            a=old.index(start);z=old.index(end,a)+len(end);old=old[:a]+old[z:].lstrip('\r\n')
        block=entry.replace('(docs/DIALOGUE_EYE_HAIR_20261025.md)','(DIALOGUE_EYE_HAIR_20261025.md)') if name.startswith('docs/') else entry
        p.write_text(block+old,encoding='utf-8')
if __name__=='__main__':main()

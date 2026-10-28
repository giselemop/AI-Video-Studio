"""Finalize only after real media, replay, browser and deployment acceptance."""
import datetime
import re
import subprocess
from run import Run,PEOPLE,SLOTS,FOLDER,ROOT,read,write,sha

def marker(path,text):
    path=ROOT/path;source=path.read_text(encoding='utf-8-sig');start='<!-- character-reference-pack-20261026:start -->';end='<!-- character-reference-pack-20261026:end -->'
    block=start+'\n'+text.rstrip()+'\n'+end
    if start in source:source=re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda _:block,source,flags=re.S)
    else:source=block+'\n\n'+source
    path.write_text(source,encoding='utf-8')

def finish():
    r=Run();r.access();r.preserve()
    if r.state['stage'] not in ['VideosReady','ReadyForUserPreview']:raise RuntimeError('Finish both recorded videos first')
    api=read(FOLDER/'api-regression.json');media=read(FOLDER/'media-verification.json');ui=read(FOLDER/'browser-ui-checks.json');playback=read(FOLDER/'browser-playback.json')
    if not all(item['status']=='Passed' for item in [api,media,ui,playback]):raise RuntimeError('Every acceptance report must pass')
    if len(media['outputs'])!=20 or len(playback['videos'])!=2 or not all(item['ended'] and item['width']==864 and item['height']==480 and item['error'] is None for item in playback['videos']):raise RuntimeError('18 references and 2 fully played clips are required')
    if not any(item['name']=='v2_completed_replays_create_no_new_tasks' and item['status']=='Passed' for item in api['checks']):raise RuntimeError('Complete v2 replay checks')
    runtime=r.api('/api/minimax/local/status');preview=r.session.get('http://127.0.0.1:18081/api/minimax/local/status',timeout=15).json();q=r.session.get('http://127.0.0.1:8188/queue',timeout=15).json()
    if runtime['queue']['activeTasks'] or runtime['queue']['paused'] or not preview['queue']['paused'] or preview['queue']['activeTasks'] or q['queue_running'] or q['queue_pending']:raise RuntimeError('Completed idle primary queue and preserved paused preview are required')
    build=ROOT.parent/'Data/Deploy/CharacterReferencePack20261026V2/VideoStudio.Server.dll';normal=ROOT/'server/publish/VideoStudio.Server.dll'
    if sha(build)!=sha(normal):raise RuntimeError('Normal startup build must match accepted deployment')
    samples=read(FOLDER/'resource-samples.json');good=[sample for sample in samples if 'running' in sample]
    if not good or max(sample['running'] for sample in good)>1:raise RuntimeError('Observed GPU concurrency must remain one')
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip();head=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()
    stats=dict(apiChecks=len(api['checks']),mediaChecks=len(media['checks']),browserUiChecks=len(ui['checks']),browserClipsPlayed=2,backendSelfTests=16,frontendUnitTests=7,observedMaxComfyRunning=max(s['running'] for s in good),sampledMaxGpuUsedMiB=max(s['usedMiB'] for s in good),sampledMinDiskFreeGiB=min(s['diskFreeGiB'] for s in good),resourceSampleErrors=len(samples)-len(good))
    videos=[item for item in media['outputs'] if item['kind']=='video']
    table='\n'.join('| '+p['name']+' | '+str(r.state['people'][p['key']]['versionId'])+' / v'+str(r.state['people'][p['key']]['version'])+' | 3 + 6 | '+str(next(v['taskId'] for v in videos if v['person']==p['key']))+' |' for p in PEOPLE)
    statuscounts={status:sum(record.get('status')==status for record in r.state['tasks'].values()) for status in ['Succeeded','Failed']}
    summary=dict(technical='Passed',contentReview='NeedReview',publication='Blocked',branch=branch,head=head,projectId=r.state['projectId'],characters=2,selectedReferences=18,imagesNative='1536x864',videosNative='864x480 / 24FPS / 124 frames',taskStatusCounts=statuscounts,normalStartupDllSha256=sha(normal),metrics=stats,newModels=0,newCloudCalls=0,previewQueuePreserved=True,priorArtifactsPreserved=True,completedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write(FOLDER/'acceptance-summary.json',summary)
    short=f"> 2026-10-26：人物九图参考包已补齐，项目47。林安v3、周言v2各3张面部近景＋6张全身，独立保存视角、景别和造型；旧版本与原视频保留。{stats['apiChecks']}项API、{stats['mediaChecks']}项媒体/来源、{stats['browserUiChecks']}项实际页面检查及两条全身短片完整播放Passed。文件技术Passed，人物一致性/表演NeedReview，发布Blocked。GPU并发1，无新模型、无云调用。恢复Data/CharacterReferencePack20261026/run.json，completed=true禁止重复提交。见[人物库](http://127.0.0.1:18080/#character-library)、[九图与样片](http://127.0.0.1:18080/character-reference-pack.html)、[本轮验收](docs/CHARACTER_REFERENCE_PACK_20261026.md)。"
    for path in ['项目状态.md','待办事项.md','变更记录.md']:marker(path,short)
    english=f"> 2026-10-26: Completed project47 reference packs: LinAn v3 and ZhouYan v2 each freeze three face close-ups and six full-body angles, with independent view/framing and immutable wardrobe/body snapshots. {stats['apiChecks']} live API, {stats['mediaChecks']} media/provenance, {stats['browserUiChecks']} browser UI checks and two complete browser playbacks Passed; content NeedReview and publication Blocked. GPU concurrency1; no new models/cloud calls. Existing versions/artifacts retained. Data/CharacterReferencePack20261026/run.json completed=true prevents duplicate generation. [Acceptance](docs/CHARACTER_REFERENCE_PACK_20261026.md)."
    for path in ['PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:marker(path,english)
    architecture='> 人物库继续复用entity_versions，不增加数据库结构。character-library-v2在参考中新增framing，并保存referencePack、viewConvention及体型比例；视角只表示方向。v1按原始序列化/哈希读取，新字段为null时不输出，旧请求指纹与幂等回放保持。新版按(view, framing)精确选图，提交与执行复核冻结快照、源SHA和工作流；试用模式继续独立于正式Shot/Episode。九图为3近景＋6全身，8个方向与3个景别可扩展。详见[实现与验收](CHARACTER_REFERENCE_PACK_20261026.md)。'
    for path in ['docs/系统架构.md','docs/ARCHITECTURE.md']:marker(path,architecture)
    marker('docs/技术决策.md','> 采用同一身份锚点＋正面全身造型基准派生多角度，Klein单图用于近景与全身正面，双ReferenceLatent分别绑定身份与完整服装用于其余全身方向。统一1536×864保证横屏首帧完整，全身服装要求从近景提示词移除以避免拼贴。九图保存在不可变造型版本中，不当作LoRA训练或三维人物。Windows torch storage访问异常后，本机标准启动增加--disable-mmap；未升级Comfy、依赖或权重。详见[实测记录](CHARACTER_REFERENCE_PACK_20261026.md)。')
    marker('docs/项目需求.md','> 已实施两个人物各9图、固定完整服装与体型、视角/景别分离、完整度提示、九图浏览放大和精确视频调用；新全身图实际生成两条短片。人物最终偏好与复杂动作需继续人工复核。详见[本轮验收](CHARACTER_REFERENCE_PACK_20261026.md)。')
    marker('docs/验收标准.md',short.replace('(docs/CHARACTER_REFERENCE_PACK_20261026.md)','(CHARACTER_REFERENCE_PACK_20261026.md)'))
    marker('docs/开发说明.md','> 人物库新版回归：后端--character-library-self-test(16)，前端node --test tests/character-library-model.test.mjs(7)。tools/character_reference_pack按持久幂等键生成，selection.json保留定向修复取舍，verify_api.py/verify_replays.py验证兼容与拦截，verify_delivery.py核对原生媒体和来源。run.py完成后只核验；不得清空run.json重提。崩溃前17张选中图的内存/history已丢失，以原生PNG执行图、DB、拷贝输入SHA与原生输出核验，并明确证据类别；恢复后逐任务立即归档历史。详见[本轮记录](CHARACTER_REFERENCE_PACK_20261026.md)。')
    marker('docs/ACCEPTANCE_REPORT.md',short.replace('(docs/CHARACTER_REFERENCE_PACK_20261026.md)','(CHARACTER_REFERENCE_PACK_20261026.md)'))
    marker('docs/FIX_HISTORY.md','> 2026-10-26定向修复：近景混入裤装/鞋子造成小人拼贴或半身构图，保留原图并重写仅含头肩与衣领的提示词，选定6张近景。任务1452因Windows torch storage访问异常Failed，保留任务与崩溃日志；恢复既有Comfy并添加--disable-mmap，第二次定向候选1453Succeeded。补充每任务即时历史归档；崩溃前图使用原生PNG实际执行图进行来源核验。UI缺图/重复组合显示具体原因，旧版JSON小数哈希与null字段兼容不改写旧记录。最终技术Passed，人物内容NeedReview，发布Blocked。详见[本轮验收](CHARACTER_REFERENCE_PACK_20261026.md)。')
    detail=f"""## 最终实施与验收

项目47，分支`{branch}`，HEAD `{head}`；本轮未提交或推送，原有脏工作保留。人物库和标准启动构建已更新，服务仅监听127.0.0.1。技术Passed；身份、表演与最终偏好NeedReview，发布Blocked。

| 人物 | 不可变版本ID / 人物版本 | 面部近景 + 全身 | 新全身视频任务 |
| --- | --- | --- | --- |
{table}

每套造型保存完整上衣、裤装、鞋子、体型和发型。近景为正面/左前侧/右前侧，全身为正面/左前侧/左侧/背面/右侧/右前侧。所有图片原生1536×864，视频864×480/24FPS/124帧，约5.17秒。画面左右遵循image-facing-v1，前侧与侧面为近似角度，未做精确三维标定。

### 验收证据

- 后端16项自测、前端7项选图/完整度/旧版/排序测试、Release发布、Vue构建Passed。Vite现有块大小与依赖注释提示保留，不影响构建。
- 实际API {stats['apiChecks']}项Passed：18个组合精确绑定、相同方向不同景别用不同参考、缺图与缺景别拒绝、重复/不完整九图拒绝、篡改快照/提示词/工作流拦截、v1哈希与旧任务回放，以及新版完成后回放与冲突不增加任务。
- 媒体/来源{stats['mediaChecks']}项Passed：18张选图及2条视频完整解码、实际尺寸、原生Comfy输出SHA、输入身份/造型SHA、实际执行提示词、上传副本、HTTP Range及旧5条视频保护。
- 实际页面{stats['browserUiChecks']}项Passed，九图查看/放大、完整度、视角/景别联动、旧版半身兼容、表单去重/缺图提示通过。两条新视频在浏览器完整播放，ended=true，控制台无错误；每条124帧由FFprobe计数及FFmpeg完整解码核验，未将浏览器未提供的帧计数当作实测。
- 观察Comfy最高并发{stats['observedMaxComfyRunning']}；视频期间采样GPU使用最高{stats['sampledMaxGpuUsedMiB']}MiB、磁盘可用最低{stats['sampledMinDiskFreeGiB']}GiB。为采样值，不是精确单任务峰值或持续可用性保证。

### 失败、修复与证据边界

原近景1431/1432出现小人拼贴或鞋子杂物，1433/1441构图偏半身；1439/1440一并换为统一紧近景。原图均保留，未将技术Succeeded改写为内容通过。一次只修复近景，保留合格全身图；每个逻辑位置最多两次定向修复。

1452在读取safetensors时发生Windows fatal access violation，任务真实Failed。保留原失败、崩溃日志与所有已有图片；启用已安装Comfy支持的--disable-mmap恢复，最后候选1453Succeeded。未安装或升级软件，没有新增权重或云推理。标准start.bat也保留该运行参数。

该次崩溃清除了此前内存/history，选中图片有17张缺少可恢复的原始/history回执。其原生PNG保留实际执行图，已结合数据库Succeeded/Comfy promptId、原生输出匹配、实际拷贝输入SHA验证，标注NativePngPromptAndDatabase；没有伪造历史回执，也没有为了补回执重生成旧图。恢复后的近景与两条视频逐任务立即归档原始历史。具体来源类别见media-verification.json。

两条视频的六处抽帧均保持完整头脚和相同衣裤鞋。周言有嘴部动作，尽管请求中要求不讲话，因此精确动作语义未判Passed，仍需人工复核。静态九图能够按镜头取用，不能据此保证完整转身、复杂肢体、跨场景长期身份一致、固定声线或口型。当前不是三维人物或专属LoRA。内容待人工复核，不自动进入正式Shot/Episode或发布。

### 部署、恢复与使用

活动构建Data/Deploy/CharacterReferencePack20261026V2；标准server/publish程序集SHA相同，旧标准构建备份Data/CharacterReferencePack20261026/previous-normal-publish。原18081辅助服务保持暂停，主队列启用、并发1、无剩余运行任务。数据库没有结构变更，实施前备份backup/20261026_112234保留。

恢复文件Data/CharacterReferencePack20261026/run.json已completed=true，后续只核验不重复提交；selection.json记录选片，失败与替代图继续保留。API/媒体/浏览器/资源/部署证据及acceptance-summary.json均在同目录。

[打开人物库](http://127.0.0.1:18080/#character-library) · [九图与两条新样片](http://127.0.0.1:18080/character-reference-pack.html) · [使用说明](人物模型库使用说明.md)
"""
    path=ROOT/'docs/CHARACTER_REFERENCE_PACK_20261026.md';source=path.read_text(encoding='utf-8').replace('当前：实施中。技术检查、参考图内容复核和视频动作效果分别记录，试用素材不自动获准发布。','当前：已完成技术验收，人物最终观感待人工复核，发布Blocked。')
    source=source.split('## 最终实施与验收')[0].rstrip()+'\n\n'+detail;path.write_text(source,encoding='utf-8')
    files=['server/CharacterLibraryService.cs','server/CharacterLibraryEndpoints.cs','server/CharacterLibrarySelfTest.cs','web/src/components/CharacterLibraryPanel.vue','web/src/components/characterLibraryModel.js','web/tests/character-library-model.test.mjs','web/dist/index.html','web/public/character-reference-pack.html','web/dist/character-reference-pack.html','config/workflow-contracts.json','start.bat','docs/CHARACTER_REFERENCE_PACK_20261026.md','docs/人物模型库使用说明.md']
    files += [str(path.relative_to(ROOT)).replace('\\','/') for path in (ROOT/'tools/character_reference_pack').iterdir() if path.is_file()]
    write(FOLDER/'source-manifest.json',[dict(path=name,sha256=sha(ROOT/name)) for name in files])
    r.save(stage='ReadyForUserPreview',completed=True,technical='Passed',contentReview='NeedReview',publication='Blocked')
    print('All acceptance gates Passed; checkpoint completed and documentation updated',flush=True)

if __name__=='__main__':finish()

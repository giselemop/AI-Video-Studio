"""Record final evidence from verified files; never generates or approves content."""
from pathlib import Path
import sys,json,subprocess,datetime,re
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,OUT,DATA,write,sha
MARK='character-story-20261027'

def prepend(path,body):
    start='<!-- '+MARK+':start -->';end='<!-- '+MARK+':end -->'
    old=path.read_text(encoding='utf-8-sig');old=re.sub(re.escape(start)+r'.*?'+re.escape(end)+r'\s*','',old,flags=re.S)
    path.write_text(start+'\n'+body+'\n'+end+'\n\n'+old,encoding='utf-8')

def run():
    read=lambda name:json.loads((OUT/name).read_text(encoding='utf-8-sig'))
    final=read('final-runtime.json');assert final['status']=='Passed'
    pilot=read('pilot.json');media=read('pilot-media-checks.json');preview=read('preview-media-checks.json');browser=read('browser-runtime-checks.json')
    assert media['status']==preview['status']==browser['status']=='Passed'
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    status=subprocess.check_output(['git','-c','core.quotepath=false','status','--short','--branch'],cwd=ROOT,text=True,encoding='utf-8');(OUT/'git-after.txt').write_text(status,encoding='utf-8')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True,encoding='utf-8').splitlines()
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    rows=[];failures=[];gpu=[]
    for slot,item in pilot['slots'].items():
        k=item['Keyframe'];v=item['Video'];rows.append(f'| {slot} | {item["shotId"]} / {item["planId"]} | {k["id"]} | {v["id"]} | {len(item.get("KeyframeHistory",[]))} / {len(item.get("VideoHistory",[]))} | Passed / NeedReview / Blocked |')
        for kind in ['Keyframe','Video']:
            for t in item.get(kind+'History',[])+[item[kind]]:
                gpu.append(t['id'])
                if t.get('inspection',{}).get('payload',{}).get('decision')=='Failed':failures.append(f'- 原任务{t["id"]}（{slot} / {kind}）：{t["inspection"]["payload"]["note"]}')
    checks=[]
    for label,file in [('后端规则','backend-self-test.json'),('本机图片工作流契约','workflow-contract-checks.json'),('引用/拒绝/文件变化','reference-policy-checks.json'),('现行接口','api-checks.json'),('选角/Shot/幂等集成复核','integration-checks.json'),('真实媒体与来源','pilot-media-checks.json'),('合成预览','preview-media-checks.json'),('本轮真实页面','browser-runtime-checks.json')]:
        d=read(file);checks.append(f'| {label} | {len(d.get("checks",[]))} | {d["status"]} | `{file}` |')
    body=f'''# 人物参考库与剧情流程实施验收 · 2026-10-27

技术 **Passed**；试片检查 **Passed**；人工内容 **NeedReview**；正式发布资格 **Blocked**。本轮自动实施和有限试片已交付，不能据此宣布最终人物一致性或艺术效果验收通过。

更新：{now}。运行入口：[人物参考库](http://127.0.0.1:18080/#character-library)、[剧情选角与试片](http://127.0.0.1:18080/#character-story)、[四镜头及合成播放](http://127.0.0.1:18080/character-story-preview.html)。

## 已完成能力与现状

- 保留Vue/.NET/MySQL及现有工作流。人物参考库准确解释为设定、参考图和不可变造型版本；区分人物身份和换装。同一人物换装建立新造型版本。
- 先RealVisXL候选近照，再确认正面身份；Klein从身份锚点派生全身造型，其他视角沿用两项基准。创建、候选比较、放大、单槽补图、来源参数、审核门禁和版本冻结已接入实际界面。
- 九图固定为面部正面/左前侧/右前侧3张，以及全身正面/左前侧/左侧/背面/右侧/右前侧6张，沿用1536×864。近景不混入裤装/鞋子提示；全身须完整头顶、双手和双鞋。左右遵守image-facing-v1，实际鼻尖朝画面左/右；前侧不能以纯侧面充数，背面不验证正脸身份。
- 完整度、素材审核、版本审核分别展示；旧版缺图不自动换图。新冻结记录包含设定、造型、参考ID/SHA、原任务与参数、模型/工作流、提示词、seed和审核。既有5个人物库版本1–5保持原SHA，旧库兼容检查16项通过。
- 项目选角→本集明确快照→原Shot不可变人物计划已实测。更新项目演员后，本集及历史Shot仍保留原版本。双人分别固定身份、造型、站位、动作；缺图、错版本、被拒绝素材和文件变化明确拒绝。
- 剧情关键帧是新增明确调用模式，人物库直接试片保留为实验。关键帧、H3实际首帧、来源参考及任务依赖独立留痕，未绕过原正式H3/发布门禁。H3为确认关键帧的单首帧路线，FL2VA未被宣称为Ref2VA。
- 所有真实生成经业务队列，GPU并发1。提交前校验模型、工作流、文件哈希、依赖、资源及已验证参数。保留质量选择，不自动降级、不换模型；同seed不保证身份。

## 有限真实GPU结果

项目{pilot['projectId']}，Episode{pilot['episodeId']}，林安版本4、周言版本5。共{len(gpu)}个真实GPU任务，包含6张关键帧候选及{len(gpu)-6}段视频（4个基础片＋定向修复）。H3均为864×480、24FPS、124帧、20steps，约5.167秒；baseline480是本轮明确选择的短片验收规格。

| 镜头 | Shot / 计划 | 当前关键帧任务 | 当前视频任务 | 关键帧 / 视频修复次数 | 技术 / 内容 / 发布 |
| --- | --- | --- | --- | --- | --- |
'''+ '\n'.join(rows)+f'''

合成预览任务 **{pilot['preview']['id']}**，{preview['frames']}帧、{preview['fps']}FPS、{preview['width']}×{preview['height']}、约{preview['duration']:.3f}秒。PostDubbing策略输出无原生音轨；原始H3音视频保留，未伪造原生声音验收。实际文件：`{pilot['preview']['assetPath']}`，SHA256 `{pilot['preview']['sha256']}`。

真实Comfy回执、实际执行图和请求原文：`C:\\install\\AI\\Data\\CharacterStoryTrace\\task_<ID>`。抽帧、FFprobe、完整音视频解码、SHA、Range206及完整浏览器播放均有证据。首帧一致性指关键帧输出SHA与Comfy实际输入文件SHA相同，不声称视频第0帧经模型重建/编码后逐像素相同。本集为切镜示例，每镜重新制作关键帧；连续动作尾帧接续未在本轮启用或验证。

## 失败与定向修复证据

'''+ '\n'.join(failures)+'''

失败输出保留，修复记录保留原因、实际改变的提示词/seed及原任务。关键帧失败项未进入对应视频；视频内容失败只重做该镜头，未整集重生成。每项最多两次，实际次数见上表。

四输入Klein首次双人任务1512复制为两位林安；核对实际四槽文件均正确，定向提示修复1514才恢复左女右男。该单例通过只证明本例可送审，不代表普遍可靠的多人身份绑定。双人1518实际主要为女方点头、男方转头回应，动作逐字命中和细微脸部仍待人工审核；没有虚构身份分数。各镜头阅读室书架排布有差异，未建立精确空间布局连续性，不把四段示例当作已通过电影连续性验收的正式成片。

## 数据库、恢复与保护

管理员执行010/011后，实际约束、审核表和外键已核验，readiness为Passed。010只扩展既有entity_versions类型，011补齐009原定义但本机缺失的审核日志表；没有改写素材为批准状态。结构变更前备份`backup/20261027_021612`及`backup/20261027_044259`已校验，后者SQL SHA256为`c8105a41e6211206d9b6b4a73bd9b63d53f8f253910bba5b72a1a941abb1af72`。

真实执行中重启API：1516原Comfy promptId保持，第一次尝试过期为Abandoned，第二次接管原执行并Succeeded；只有一个Comfy执行，没有重复GPU生成，没有手改任务状态或重启Comfy。证据`restart-recovery.json`。CPU预览1520在真实Pending状态取消，attempts0且无输出；幂等重复提交返回原ID，通用重试绕过被拒绝，见`queue-controls.json`。

旧人物版本、旧媒体及五人扩充原检查点SHA保持。五人53个原生成任务只读取，40张候选收集为NeedReview：许知夏7/9、陈屿8/9、苏晚晴8/9、赵明远9/9、沈玉兰8/9。仍缺5个合格前侧槽位，原始错误标注与纠正原因保留；五人没有被自动批准、没有新库版本、没有批量试片。测试用项目49/人物26/参考98明确标注，无模拟GPU结果或人工批准。

## 测试与真实页面

| 检查 | 项数 | 结果 | 证据文件（均在CharacterStory20261027） |
| --- | --- | --- | --- |
'''+ '\n'.join(checks)+'''

另有旧库兼容16项、前端参考选择7项、旧两片媒体20项通过。Vue生产构建通过，保留依赖注释和大包体积的构建警告；本轮未做无关打包重构。后端已构建并部署，发布DLL与构建/部署暂存SHA一致。

真实页面覆盖人物卡片/九图放大/旧版本缺图/候选来源、项目选角、本集快照、Shot绑定、静态检查与H3首帧核对、内容失败说明、任务状态、视频与合成播放、人工确认门禁。截图与逐项结果见`browser-runtime-checks.json`及`screenshots/`，早期页面结果保存在`browser-ui-checks.json`，其中迁移阻断是已解除的历史状态。

## 待审、受阻与未验证

- **Blocked：人工确认**。现有演员参考和新候选的最终身份/造型/手部/表演/跨镜头一致性尚未由用户批准。新候选“人工确认锚点→九图批准→冻结新版本”的最终内容批准不能由助手代签；代码与拒绝门禁已验证，真实人工批准路径仍待用户操作。
- **Blocked：正式发布**。本轮任务为送审预览，尚未取得正式生产/发布资格。
- **Failed（已保留并修复）**：原关键帧1511、1512及原转身视频1516；当前替代输出仅试片检查Passed，最终内容NeedReview。
- **Unverified**：H3 Ref2VA/直接多身份输入、普遍可靠的四参考身份绑定、精确角度与复杂肢体/长片、连续动作尾帧衔接、1376×768/1920×1088在本轮剧情链路的真实生成、完整人工锚点批准与新版九图入库。没有新模型下载、云付费、环境升级或公开发布。

## 修改范围、分支与恢复

'''+f'''分支`{branch}`，HEAD `{head}`，未提交、未推送；当前暂存文件数{len(staged)}。既有大量脏工作保留，完整状态见`git-before.txt`/`git-after.txt`，不能把全部diff归于本轮。增量源码/迁移/工作流/界面/工具的当前SHA见`source-manifest.json`。
'''+'''
本轮主要模块：CharacterStoryStore/Service/Endpoints/SelfTest、CharacterWorkshopService、CharacterLibraryService/Panel、CharacterWorkshopPanel、CharacterStoryPanel、GenerationQueue/TaskLeaseRepository、预检与FFmpeg、迁移010/011及tools/character_story。媒体与任务证据只在Data，模型权重不入仓库。

恢复时先读run.json和pilot.json、核对真实队列与已登记ID。自动实施completed=true后只读核验，不重复提交。保留前阶段报告`acceptance-before-resume.md`及原run快照；回退服务只在队列空闲后用`server-before`已校验二进制恢复。不要整体git reset、覆盖其他脏工作或随意还原旧SQL；010类型已有新记录，不能缩回约束。数据库灾难恢复应使用已验证备份并另行审查新数据差异。
'''
    report=ROOT/'docs/CHARACTER_STORY_ACCEPTANCE_20261027.md';report.write_text(body,encoding='utf-8')
    summary=f'> 2026-10-27：人物参考库与剧情流程增量开发及有限真实验证已交付。技术Passed，人工内容NeedReview，发布Blocked。010/011已由管理员执行并实测就绪；项目50/集34固定林安#4、周言#5，4个基础视频＋定向修复及预览任务{pilot["preview"]["id"]}完成技术检查。执行中重启1516沿用原Comfy执行，无重复生成。旧版本/媒体/五人原检查点保留；40张扩充候选待审、缺5个前侧槽位，未批准或批量试片。无新模型/云付费/发布；自动实施已完成，无周期重跑。见[验收与待审清单](docs/CHARACTER_STORY_ACCEPTANCE_20261027.md)、[四镜头播放](http://127.0.0.1:18080/character-story-preview.html)。'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:prepend(ROOT/name,summary)
    notes={
      'ACCEPTANCE_REPORT.md':'技术及有限四片/合成/执行中恢复Passed；最终内容NeedReview、发布Blocked。人工锚点/新版本批准待用户操作，五人候选未入库。',
      'FIX_HISTORY.md':'修复缺失审核表与类型约束（管理员010/011）；阻止缺图回退、通用重试绕过和重复Comfy提交。1511多臂、1512双女复制及1516转身不足均保留真实失败与定向修复。恢复1516沿用原promptId，CPU1520取消未执行。真实页面复测修复了项目/集切换后旧调用预览残留，并清除人工确认状态；原媒体与冻结记录不变。',
      '项目需求.md':'本轮人物设定、九图规范、不可变造型、原项目/Episode/Shot选角绑定、剧情关键帧/H3首帧预览及恢复已实施；技术与有限试片Passed，人工身份/造型最终批准及正式发布仍Blocked。没有把人物参考库称为训练完成的专属模型或3D。',
      '系统架构.md':'人物设定/参考/造型版本复用原entity_versions；选角、集快照、Shot计划沿用原项目/Episode/Shot。剧情关键帧和H3为明确ReviewPreview，不绕过正式生产门禁。',
      '技术决策.md':'不可变选角与来源SHA，身份/造型分离；四参考Klein只作为静态候选逐张审核，H3只接收已检查关键帧。真实双人首次失败后修复，不承诺普遍身份可靠或Ref2VA。',
      '验收标准.md':'九槽齐全不等于合格。技术、PreviewInspection、HumanReview和发布资格分开。每失败槽/镜头最多两次，只修失败项；内容最终待审。',
      '开发说明.md':'入口/api/character-workshop、/api/character-story及#character-story。010/011本机已就绪；tools/character_story的run/pilot登记真实任务及幂等键，completed后只读核验，不批量重跑。',
      '项目工作流与技术说明.md':'RealVisXL候选→人工身份→Klein造型与九图→审核冻结→项目/集选角→Shot剧情关键帧→检查→H3首帧视频→定向修复→FFmpeg送审。Comfy执行模型，业务保存任务/审核/版本。双人须检查静态，H3 Ref2VA未启用，声音策略明确。',
      'ARCHITECTURE.md':'Additive immutable cast/Shot snapshots reuse entity_versions and original Episode/Shot. Explicit story-keyframe review previews preserve formal H3/release gates. Local bounded GPU, restart recovery and preview technical checks Passed; final human content review pending.',
      'DATABASE.md':'Administrator applied migrations010 and011; live type constraint, review table and foreign keys verified. No parallel story system or fake asset approvals. Verified SQL backups retained; do not shrink the constraint after new typed records exist.',
      'COMFYUI_API.md':'Actual Klein four-input execution tested: first two-person candidate duplicated actorA, directed repair passed preview inspection. This is bounded evidence, not general identity binding or H3 Ref2VA. H3 uses the exact inspected keyframe hash. Task1516 recovered one existing Comfy prompt after API restart.'}
    for name,text in notes.items():prepend(ROOT/'docs'/name,'> 2026-10-27：'+text+' 详见[本轮验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。')
    for name in ['ARCHITECTURE.md','DATABASE.md','COMFYUI_API.md']:prepend(ROOT/name,'> 2026-10-27：010/011已实测就绪。人物参考与剧情首帧流程、有限GPU、执行中恢复和合成技术Passed；内容NeedReview、发布Blocked。见[完整验收](docs/CHARACTER_STORY_ACCEPTANCE_20261027.md)。')
    guide=ROOT/'docs/人物模型库使用说明.md';text=guide.read_text(encoding='utf-8')
    text=text.replace('新增剧情链路当前受迁移010、011所需的ALTER/CREATE权限及缺失审核表阻断，完整验收尚未完成','新增剧情链路已完成有限技术验收，最终人物内容与发布资格仍待审核')
    text=re.sub('当前若页面提示缺失迁移.*?相同seed不保证身份一致。','010/011已由管理员执行并核验。本轮4个基础剧情片及定向修复已完成技术检查，可在[统一试片入口](http://127.0.0.1:18080/character-story-preview.html)查看实际关键帧、视频及保留失败。四输入Klein首次双人失败、提示修复后才可试片，不能据此保证普遍身份可靠；H3 Ref2VA未启用，FL2VA首尾帧不等于多身份参考。相同seed不保证身份一致。',text,flags=re.S);guide.write_text(text,encoding='utf-8')
    plan=ROOT/'docs/CHARACTER_STORY_PIPELINE_20261027.md';text=plan.read_text(encoding='utf-8');text=re.sub('当前：局部开发已部署，整体Blocked。.*$', '当前：本地增量开发及有限四片、合成、真实恢复的技术验收Passed；人工最终内容NeedReview、发布Blocked。010/011已核验；详细结果见[阶段验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。',text,flags=re.S);plan.write_text(text,encoding='utf-8')
    sourceFiles=['server/CharacterStoryStore.cs','server/CharacterStoryService.cs','server/CharacterStoryEndpoints.cs','server/CharacterStorySelfTest.cs','server/CharacterWorkshopService.cs','server/CharacterLibraryService.cs','server/CharacterLibraryEndpoints.cs','server/CharacterIdentityEndpoints.cs','server/Program.cs','server/TaskSubmissionPreflightService.cs','server/GenerationQueue.cs','server/TaskLeaseRepository.cs','server/FfmpegService.cs','web/src/App.vue','web/src/components/CharacterLibraryPanel.vue','web/src/components/CharacterWorkshopPanel.vue','web/src/components/CharacterStoryPanel.vue','database/migrations/010_character_story_records.sql','database/migrations/011_character_reference_review_audit.sql','config/workflow-contracts.json','web/public/character-story-preview.html']
    sourceFiles+= [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tools/character_story').glob('*')) if p.is_file()]
    write(OUT/'source-manifest.json',dict(branch=branch,head=head,committed=False,pushed=False,stagedFiles=staged,files=[dict(path=f,sha256=sha(ROOT/f)) for f in sourceFiles],deployedDllSha256=final['deployedDllSha256'],backupDllSha256=final['backupDllSha256']))
    state=read('run.json');state.pop('blocker',None);state.update(stage='ReadyForHumanReview',completed=True,automaticWorkComplete=True,finalHumanAcceptanceComplete=False,technicalOverall='Passed',contentReview='NeedReview',publication='Blocked',newGpuTasks=len(gpu),newStoryBaseClips=4,previewTaskId=pilot['preview']['id'],branch=branch,head=head,committed=False,pushed=False,updatedAt=now,phases=dict(audit='Passed',schema='Passed',reference_display='Passed',candidate_development='Passed',reference_policy='Passed',anchor_final_human_confirmation='Blocked',casting_persistence='Passed',story_keyframe_gpu='Passed',four_clip_technical='Passed',restart_recovery='Passed',browser='Passed',final_human_content='Blocked'))
    write(OUT/'run.json',state);pilot.update(stage='ReadyForHumanReview',completed=True,automaticWorkComplete=True,contentReview='NeedReview',publication='Blocked',gpuSubmitted=len(gpu));pilot.pop('blocker',None);write(OUT/'pilot.json',pilot)
    print('Chinese authoritative records, technical docs, source manifest and real acceptance report updated. Technical Passed; human content pending; publication Blocked. No rerun scheduled.')
if __name__=='__main__':run()

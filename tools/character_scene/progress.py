"""Update only this run's documentation marker; preserve other task records."""
import json,re,datetime
from common import ROOT,OUT,write,sha

MARKER='character-scene-20261027'
def upsert(relative,body):
    path=ROOT/relative;original=path.read_text(encoding='utf-8-sig')
    block='<!-- '+MARKER+':start -->\n'+body.strip()+'\n<!-- '+MARKER+':end -->'
    pattern=r'<!-- '+MARKER+r':start -->[\s\S]*?<!-- '+MARKER+r':end -->'
    updated=re.sub(pattern,lambda _:block,original) if re.search(pattern,original) else block+'\n\n'+original
    if path.read_text(encoding='utf-8-sig')!=original:raise RuntimeError('Concurrent documentation edit; re-read '+str(path))
    path.write_text(updated,encoding='utf-8')

def run():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8'));assert state['generationHold']['active'] and not state['completed']
    common='2026-10-27：项目51/集36固定阅读室场景版本、分镜显式绑定与待审界面已部署。真实关键帧1522–1525共4张，技术Passed；1522/1523方向、1525手部Failed，1524仅PreviewInspection Passed。区域外46.5%背景像素与原1514完全一致，不能据此判定人物/剧情合格。用户明确“保持待审”，拒绝来源与旧版本保留；新补图、H3视频和合成Blocked，未自动续跑。24项后端、25项首轮API、45项当前回归、71项媒体来源、5组前端、13项浏览器检查Passed。main/d6ec38d，未新增提交，无新模型/云调用；独立人物修复任务不重复。'
    link='详见[场景连续性实施验收](docs/CHARACTER_SCENE_CONTINUITY_20261027.md)、[四张真实关键帧](http://127.0.0.1:18080/character-scene-preview.html)。恢复Data/CharacterScene20261027/run.json，generationHold.active=true；不得绕过用户待审指示。'
    for name in ['项目状态.md','变更记录.md']:
        upsert(name,'> '+common+' '+link)
    upsert('待办事项.md','> '+common+' '+link+'\n\n- Passed：场景版本、界面、来源检查、旧版与共享任务保全。\n- Failed：三张静态图内容；保留原图与定向修复计划，不生成视频。\n- Blocked：等待用户明确采用审核后的演员与匹配的新构图；当前保持待审，不安排重跑。')
    english='> 2026-10-27: Fixed-room scene snapshots and explicit Shot bindings delivered for project51/episode36. Four real keyframes1522–1525: file/provenance Passed; three content inspections Failed, one PreviewInspection Passed. 46.5% protected background is pixel-identical to original1514; no identity or semantic score implied. User explicitly requested review hold. No new repair image, H3 clip or composite submitted; content NeedReview/publication Blocked. Backend24, initial API25, current regression45, media71, frontend5 groups and browser13 checks Passed. main/d6ec38d, uncommitted. No new models/cloud calls; independent character-repair work preserved. [Acceptance](docs/CHARACTER_SCENE_CONTINUITY_20261027.md). Checkpoint Data/CharacterScene20261027/run.json, generationHold.active=true; do not auto-resume.'
    for name in ['PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:upsert(name,english)
    upsert('docs/ACCEPTANCE_REPORT.md','> '+common+' [本轮证据](CHARACTER_SCENE_CONTINUITY_20261027.md)。新视频参数/解码/动态连续性/播放均Blocked（未执行），不能用上轮检查替代。')
    upsert('docs/FIX_HISTORY.md','> 2026-10-27：场景五输入与遮罩保存路线真实执行，修复通用宽高补丁覆盖区域尺寸的问题；修复大场景快照导致任务列表MySQL1038排序内存不足，先取有序ID再读完整行，5/100/500条实际回归Passed。页面修复场景改动未冻结保护、拒绝版本调用、项目切换上下文及数值字段过期aria-disabled。1522/1523方向和1525手部真实失败保留，隔离旧头部姿态修复路线尚未真实验证。用户保持待审，新图/视频未续提。[详细证据](CHARACTER_SCENE_CONTINUITY_20261027.md)。')
    upsert('docs/人物模型库使用说明.md','## 固定场景与剧情关键帧（2026-10-27）\n\n在“剧情选角与试片”中，先选择项目与本集演员快照。“固定场景与机位版本”可放大已有构图、查看画面左右区域及来源；展开表单可从已检查的真实1536×864关键帧另存场景版本。已有场景锚点不同须另建场景。\n\n分镜中的“镜头场景版本”须明确选择，不自动采用新版本。选择后沿用冻结的场景/机位说明，并核对相同人物造型与左右站位；修改后另存镜头计划。切换旧计划可查看原绑定。拒绝素材会阻止调用；待审版本不代表已获人工批准。\n\n当前固定阅读室四张新图中三张失败，用户要求保持待审，不生成后续视频。新入口[四张关键帧](http://127.0.0.1:18080/character-scene-preview.html)，[完整记录](CHARACTER_SCENE_CONTINUITY_20261027.md)。人物库仍是设定、参考图和版本，不是训练模型或三维人物。')
    upsert('docs/项目工作流与技术说明.md','## 同机位场景连续性（2026-10-27）\n\n复用现有Scene资产，冻结已检查构图的来源任务、SHA256、两位演员造型、站位、机位和区域。现有Klein使用四个人物输入加一个构图输入，生成的双人区域羽化合成回原背景；区域外像素保持已有实证，区域内脸、手、方向仍需逐图检查。此方式限定同机位双人中景，切镜、换演员或造型要建立新基准。\n\n合格静态关键帧才可交给H3首帧路线，Ref2VA未启用。当前三张内容失败、人物来源被拒绝，且用户明确保持待审，所以没有新H3或合成结果。控制器保存幂等请求与审核暂停，不能靠改seed、换版本或重启绕过。[实施与边界](CHARACTER_SCENE_CONTINUITY_20261027.md)。')
    write(OUT/'documentation.json',dict(status='Passed',updatedAt=datetime.datetime.now().astimezone().isoformat(),report=str(ROOT/'docs/CHARACTER_SCENE_CONTINUITY_20261027.md'),reportSha256=sha(ROOT/'docs/CHARACTER_SCENE_CONTINUITY_20261027.md'),marker=MARKER,otherTaskRecordsPreserved=True))
    print('Chinese project records and technical compatibility documentation updated under this run marker only; review hold retained.')
if __name__=='__main__':run()

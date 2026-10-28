"""Prepare the review page, then finalize only after real media/browser checks."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

sys.path.insert(0,str(Path(__file__).parent))
from run_acceptance import Run, ROOT, DATA, FOLDER, PEOPLE, read, write

def url(path):return '/api/media?assetPath='+quote(path,safe='')

def gallery():
    report=read(FOLDER/'delivery.json');state=read(FOLDER/'run.json')
    if report['technical']!='Passed':raise RuntimeError('Media verification must pass first')
    outputs={o['name']:o for o in report['outputs']}
    parts=[]
    for person in PEOPLE:
        cards=[]
        for view,label in [('front','正面参考调用'),('threeQuarterRight','侧向参考调用')]:
            item=outputs[person['key']+'-video-'+view]
            ref=state['tasks'][person['key']+('-master' if view=='front' else '-threeQuarterRight')]['path']
            cards.append(f'<article><h3>{label}</h3><div class="reference"><img src="{url(ref)}" alt="{html.escape(person["name"])}库中参考图"><span>库中参考图 · 版本 #{item["versionId"]}</span></div><video controls muted preload="metadata" src="{url(item["assetPath"])}"></video><p>真实新生成任务 #{item["taskId"]} · 864×480 · 24 FPS · 124帧</p></article>')
        parts.append(f'<section><div class="section-title"><h2>{html.escape(person["name"])} · {html.escape(person["clothes"])}</h2><button type="button" data-person="{person["key"]}">同时播放{person["name"]}的两个镜头</button></div><div class="pair" data-pair="{person["key"]}">{"".join(cards)}</div></section>')
    extra=outputs['browser-linan-v2']
    source='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人物模型库调用验收</title><style>
    :root{color-scheme:dark;font-family:system-ui,"Microsoft YaHei",sans-serif}body{margin:0;background:#0b1220;color:#e8eef9}main{max-width:1280px;margin:auto;padding:32px 24px 60px}h1{font-size:30px;margin:12px 0}h2{font-size:22px}h3{font-size:16px}p{color:#b3c0d5;line-height:1.7}a{color:#93caff}.tag{display:inline-block;padding:5px 10px;border:1px solid #44765a;border-radius:6px;color:#b5e0c6}.review{border-color:#806a39;color:#ecd9a7}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{padding:18px;border:1px solid #34445e;border-radius:12px;background:#121d30}video{display:block;width:100%;aspect-ratio:1.8;background:#05080e;border-radius:8px;margin-top:14px}.reference{display:flex;gap:14px;align-items:center;color:#a7b9d4;font-size:13px}.reference img{width:145px;aspect-ratio:1.78;object-fit:cover;border-radius:6px}section{margin-top:30px}.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}button{border:1px solid #5f91c6;background:#1b3c65;color:#eaf4ff;border-radius:8px;padding:10px 16px;cursor:pointer}details{margin-top:30px;border:1px solid #34445e;padding:18px;border-radius:10px}details video{max-width:700px}@media(max-width:760px){.pair{grid-template-columns:1fr}main{padding:20px 14px}}
    </style></head><body><main><a href="/#character-library">打开人物模型库工作台</a><h1>人物模型库 · 调用验收</h1><span class="tag">技术检查 Passed</span> <span class="tag review">人物与自然度待复核</span><p>两个新建固定人物，每个人物分别使用库中的正面和侧向参考图生成镜头。这里播放本轮新生成的原始短片；每条约5.17秒。对照默认静音，可在播放器中打开原生声音。</p>'''+''.join(parts)+f'''<details><summary>查看从真实工作台提交的新版本验证 · 任务 #{extra['taskId']}</summary><p>林安 · v2（人物版本 #{extra['versionId']}） · 侧向参考。验证工作台选择版本、预览并提交的完整调用。</p><video controls muted preload="metadata" src="{url(extra['assetPath'])}"></video></details><p>本轮覆盖小幅表情、眨眼与轻点头。人物外观和表演效果需人工确认；没有自动批准正式成片或发布。</p></main><script>
    document.querySelectorAll('[data-person]').forEach(button=>button.addEventListener('click',()=>{{const videos=document.querySelector(`[data-pair="${{button.dataset.person}}"]`).querySelectorAll('video');videos.forEach(video=>{{video.currentTime=0;video.muted=true;video.play().catch(()=>{{}});}});}}));
    </script></body></html>'''
    for folder in [ROOT/'web/public',ROOT/'web/dist']:
        folder.mkdir(parents=True,exist_ok=True);(folder/'character-library-preview.html').write_text(source,encoding='utf-8')
    print('Review gallery prepared; media retained without new generation',flush=True)

def complete():
    run=Run('http://127.0.0.1:18080');run.access();run.preserve()
    media=read(FOLDER/'media-verification.json');api=read(FOLDER/'api-regression.json')
    browser=read(FOLDER/'browser-ui-checks.json');playback=read(FOLDER/'browser-playback.json')
    if media['status']!='Passed' or api['status']!='Passed' or any(c['status']!='Passed' for c in browser['checks']):raise RuntimeError('Verification failures remain')
    if len(playback['videos'])!=5 or not all(v['ended'] and v['readyState']>=2 for v in playback['videos']):raise RuntimeError('All five videos must complete real browser playback')
    if playback.get('consoleErrors'):raise RuntimeError('Browser errors remain')
    import requests
    queue=requests.get('http://127.0.0.1:8188/queue',timeout=10).json()
    if queue['queue_running'] or queue['queue_pending']:raise RuntimeError('Generation still active')
    samples=read(FOLDER/'resource-samples.json')['samples']
    if max(s.get('comfyRunning',0) for s in samples)>1:raise RuntimeError('Observed GPU concurrency violation')
    summary=dict(projectId=run.state['projectId'],technical='Passed',contentReview='NeedReview',publication='Blocked',videos=media['outputs'],apiChecks=len(api['checks']),mediaChecks=len(media['checks']),browserUiChecks=len(browser['checks']),newModels=0,newCloudCalls=0,observedMaxGpuMiB=max(s.get('gpuUsedMiB',0) for s in samples),observedMaxComfyRunning=max(s.get('comfyRunning',0) for s in samples),minimumObservedFreeDiskBytes=min(s['freeDiskBytes'] for s in samples),branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),head=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip())
    write(FOLDER/'acceptance-summary.json',summary)
    browserOutput=next(item for item in media['outputs'] if item['name']=='browser-linan-v2')
    run.save(stage='ReadyForUserPreview',completed=True,technicalStatus='Passed',contentReview='NeedReview',publication='Blocked',browserTaskId=browser['submittedTaskId'],browserTaskPath=browserOutput['assetPath'],browserTaskSha256=browserOutput['sha256'],newTaskSubmitted=False)
    reportPath=ROOT/'docs/CHARACTER_LIBRARY_20261026.md'
    reportSource=reportPath.read_text(encoding='utf-8').replace('- 正在实施。人物自然度和最终偏好保留人工审核；技术执行成功不自动批准发布。','- 技术实现与本轮验收 Passed。人物自然度和最终偏好仍待人工复核，发布 Blocked。')
    detailed='\n\n## 最终技术验收\n\n'
    detailed+=f'项目{run.state["projectId"]}，分支`{summary["branch"]}`，HEAD `{summary["head"]}`；本轮未提交或推送。原有未提交工作保留。\n\n'
    detailed+='| 人物/调用 | 任务 | 人物版本ID | 参考视角 | 成片规格 |\n| --- | --- | --- | --- | --- |\n'
    for item in media['outputs']:
        detailed+=f'| {item["name"]} | {item["taskId"]} | {item["versionId"]} | {item["view"]} | 864×480 / 24FPS / 124帧 |\n'
    detailed+=f'\n实际API检查{len(api["checks"])}项、媒体和来源检查{len(media["checks"])}项、实际UI检查{len(browser["checks"])}项及五条完整浏览器播放均Passed。媒体逐条完整解码，并验证HTTP Range 206、业务库快照、Comfy实际首帧/提示词/成功回执及输出SHA。\n'
    detailed+=f'\n观察到的Comfy运行并发最高{summary["observedMaxComfyRunning"]}；GPU使用采样最高{summary["observedMaxGpuMiB"]}MiB，磁盘可用空间采样最低{summary["minimumObservedFreeDiskBytes"]/1024**3:.1f}GiB。采样值不是单任务精确峰值。\n'
    detailed+='\n修复了MySQL JSON小数格式变化引起的哈希误判，按原有DECIMAL(5,2)声音字段精度计算稳定快照；未改写旧版本。另修复提交后回滚掩盖原始错误、卡片布局、历史版本显示及源角色删除/版本保存的竞争保护。\n'
    detailed+='\n本轮使用已安装的RealVisXL、Klein和H3，通过真实业务队列新生成四张人物参考及五条视频；没有新增模型、LoRA训练或云推理。仅验证小幅表情、眨眼、轻点头和两个参考角度；跨场景、完整转身、复杂肢体、长视频、固定角色声音及精细口型不属于本轮通过结论。人物身份与自然度仍由用户复核，未虚构身份识别评分。\n'
    detailed+='\n证据：`Data/CharacterLibrary20261026/`中的`run.json`、`api-regression.json`、`media-verification.json`、`task-input-traces.json`、逐任务Comfy历史与FFprobe、`browser-ui-checks.json`、`browser-playback.json`、`resource-samples.json`、`acceptance-summary.json`。技术结果可在[验收样片](http://127.0.0.1:18080/character-library-preview.html)查看，日常使用见[人物模型库使用说明](人物模型库使用说明.md)。\n'
    if '\n## 最终技术验收\n' in reportSource:reportSource=reportSource.split('\n## 最终技术验收\n')[0]
    reportPath.write_text(reportSource+detailed,encoding='utf-8')
    marker='character-library-20261026'
    paragraph=f'> 2026-10-26：两个人物模型库与视频调用已完成技术验收，项目{run.state["projectId"]}。林安/周言各两张新参考，复用不可变人物版本；四个双视角镜头及一条真实工作台提交的新版本视频全部Succeeded，均864×480/24FPS/124帧。{len(api["checks"])}项实际API与{len(media["checks"])}项媒体/来源核验Passed，五条真实浏览器完整播放Passed。人物自然度仍需人工复核，发布Blocked。无新模型、无云调用、GPU并发1；原媒体与模型保留。入口[人物库](http://127.0.0.1:18080/#character-library)、[验收样片](http://127.0.0.1:18080/character-library-preview.html)。恢复Data/CharacterLibrary20261026/run.json，completed=true禁止重复提交。见[实施与验收记录](docs/CHARACTER_LIBRARY_20261026.md)。'
    block=f'<!-- {marker}:start -->\n{paragraph}\n<!-- {marker}:end -->\n\n'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md']:
        path=ROOT/name;source=path.read_text(encoding='utf-8-sig')
        start=f'<!-- {marker}:start -->';end=f'<!-- {marker}:end -->'
        if start in source:
            before,rest=source.split(start,1);_,after=rest.split(end,1);source=before+after.lstrip('\n')
        path.write_text(block+source,encoding='utf-8')
    for name in ['docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
        path=ROOT/name;source=path.read_text(encoding='utf-8-sig')
        if f'<!-- {marker}:start -->' not in source:
            extra='\n\n'+block+'\n数值修复：MySQL JSON将1.00规范化为1.0，人物库按声音字段的DECIMAL(5,2)精度恢复规范形式再校验SHA，旧快照未重写；提交后读取错误保留原始异常。UI卡片布局、调用版本说明和重复提交状态已做真实页面复核。\n'
            path.write_text(source+extra,encoding='utf-8')
    print(json.dumps(dict(status='Passed',apiChecks=len(api['checks']),mediaChecks=len(media['checks']),videos=5),ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['gallery','complete']);args=parser.parse_args()
    globals()[args.stage]()

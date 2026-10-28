"""Build a reviewable seven-person gallery, never freezes or approves a library version."""
import html, urllib.parse
from run import Repair
from inventory import ROOT, OUT, write
from character_prompt_policy import SLOTS
from detail_sheets import sheet

VIEW={'front':'正面','threeQuarterLeft':'左前侧','threeQuarterRight':'右前侧','left':'左侧','right':'右侧','back':'背面'}

def selection(r):
 rows=[]
 for cid in range(19,26):
    name=next(c['character']['name'] for c in r.before['characters'] if c['character']['id']==cid)
    current={x['id']:x for x in r.api('/api/characters/'+str(cid)+'/references')}
    for view,framing in SLOTS:
        candidates=[(key,e) for key,e in r.state['tasks'].items() if key.startswith(f'{cid}-{view}-{framing}-') and e.get('visualStatus')=='Passed']
        if candidates:
            key,e=candidates[-1];rows.append(dict(characterId=cid,name=name,view=view,framing=framing,path=e['path'],sha256=e['sha256'],referenceId=e.get('referenceId'),taskId=e['id'],repairKey=key,source='new repair',visualStatus='Passed',note=e['inspection']['note']))
        else:
            ref=r.source(cid,view,framing)
            if not ref or current[ref['id']]['reviewStatus']=='Rejected':raise RuntimeError(f'Unresolved slot {cid} {view} {framing}')
            # Original selection is not silently reused if an explicit repair failed.
            if any(key.startswith(f'{cid}-{view}-{framing}-') for key in r.state['tasks']):raise RuntimeError(f'No passing repair {cid} {view} {framing}')
            rows.append(dict(characterId=cid,name=name,view=view,framing=framing,path=ref['assetPath'],sha256=ref['actualSha256'],referenceId=ref['id'],source='original preserved',visualStatus='NeedReview'))
 return rows

def run():
 r=Repair();rows=selection(r);write(OUT/'selected.json',rows)
 for cid in range(19,26):
    sheet('final-'+str(cid),[(f"{x['view']} {x['framing']} ref{x['referenceId']}",x['path']) for x in rows if x['characterId']==cid and x['framing']=='fullBody'])
 def image(row):return '/api/media?assetPath='+urllib.parse.quote(row['path'],safe='')
 parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>人物参考图修复与逐张验收</title><style>body{margin:0;background:#eef1f6;color:#202a38;font:16px/1.65 system-ui}main{max-width:1440px;margin:auto;padding:30px}h1{font-size:30px}section{background:white;padding:22px;margin:24px 0;border-radius:14px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}figure{margin:0;border:1px solid #d4dae4;border-radius:8px;overflow:hidden}figure img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#e5e5e5;cursor:zoom-in}figcaption{padding:10px}small{display:block;color:#566372}a{color:#205eb4}details{margin:12px 0}pre{white-space:pre-wrap;font-size:13px}dialog{width:94vw;max-width:1600px;max-height:94vh;border:0;border-radius:12px;padding:12px}dialog img{width:100%;max-height:84vh;object-fit:contain}dialog button{font-size:18px;padding:4px 18px}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:12px}}</style><main><h1>人物参考图 · 修复与逐张验收</h1><p>统一规则：character-anatomy-v2。7 位人物，每人 3 张近照 + 6 张全身，共 63 个槽位。</p><p>检查内容：身份与年龄、面部与头颈、肩臂手部、躯干腿脚、方向遮挡、服装与完整构图。助手目检与技术检查分别记录；新图仍待用户审核，不自动批准或冻结版本。原图与失败任务保留。</p><p><a href="/#character-library">返回人物参考库</a></p>''']
 for cid in range(19,26):
    person=[x for x in rows if x['characterId']==cid];parts.append('<section><h2>'+html.escape(person[0]['name'])+'</h2><div class="grid">')
    for row in person:
        label=VIEW[row['view']]+' · '+('面部近照' if row['framing']=='closeUp' else '全身')
        parts.append('<figure><img loading="lazy" src="'+image(row)+'" alt="'+html.escape(person[0]['name']+' '+label)+'"><figcaption>'+label+'<small>'+('本轮修复 · 任务 '+str(row['taskId']) if row.get('taskId') else '原图保留')+' · 参考 #'+str(row['referenceId'])+'</small><small>助手逐张目检，最终内容待用户复核</small></figcaption></figure>')
    parts.append('</div><details><summary>查看统一生成提示词</summary><div data-prompts="'+str(cid)+'"></div></details></section>')
 parts.append('''<dialog id="zoom"><button id="close">关闭原图</button><img alt="原图检查"></dialog><script>document.querySelectorAll('figure img').forEach(im=>im.addEventListener('click',()=>{document.querySelector('#zoom img').src=im.src;document.querySelector('#zoom img').alt=im.alt;zoom.showModal()}));document.querySelector('#close').onclick=()=>zoom.close();document.querySelectorAll('[data-prompts]').forEach(async el=>{const res=await fetch('/api/character-workshop/'+el.dataset.prompts);if(!res.ok)throw Error('Prompt preview '+res.status);const state=await res.json();for(const p of state.prompts){const d=document.createElement('details'),s=document.createElement('summary'),pre=document.createElement('pre');s.textContent=p.view+' '+p.framing;pre.textContent=p.prompt;d.append(s,pre);el.append(d)}});</script></main></html>''')
 target=ROOT/'web/public/character-reference-repair.html';target.write_text(''.join(parts),encoding='utf-8');print(target)
if __name__=='__main__':run()

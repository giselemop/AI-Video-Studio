"""A local, navigable five-character review page; no copies of old actors."""
from html import escape
from urllib.parse import quote
from batch import Batch,PEOPLE,SLOTS,FOLDER,ROOT,write

LABELS={'front':'正面','threeQuarterLeft':'左前侧','threeQuarterRight':'右前侧','left':'左侧','right':'右侧','back':'背面','closeUp':'面部近景','fullBody':'全身'}
def url(path):return '/api/media?assetPath='+quote(path,safe='')
def render():
    r=Batch();r.access();r.preserve();library=r.api('/api/character-library');cards=[];sections=[]
    for person in PEOPLE:
        entry=r.state['people'][person['key']];version=next(v for v in library['versions'] if v['id']==entry['versionId']);refs=version['payload']['references'];head=next(ref for ref in refs if ref['view']=='front' and ref['framing']=='closeUp')
        cards.append('<a class="person" href="#'+person['key']+'"><img src="'+url(head['assetPath'])+'" alt="'+person['name']+'正面近景"><strong>'+person['name']+'</strong><span>'+person['ageSetting']+'</span><small>'+person['clothes']+'</small></a>')
        figures=[]
        for view,framing in SLOTS:
            ref=next(ref for ref in refs if ref['view']==view and ref['framing']==framing);label=LABELS[view]+' · '+LABELS[framing]
            figures.append('<figure><a target="_blank" rel="noopener" href="'+url(ref['assetPath'])+'"><img loading="lazy" width="1536" height="864" src="'+url(ref['assetPath'])+'" alt="'+person['name']+' '+label+'"></a><figcaption>'+label+'</figcaption></figure>')
        sections.append('<section id="'+person['key']+'"><h2>'+person['name']+' <span>'+person['ageSetting']+' · v'+str(version['version'])+' · 9/9</span></h2><p>'+person['clothes']+'；'+person['hair']+'。</p><div class="photos">'+''.join(figures)+'</div><p class="back"><a href="#top">返回五人概览 ↑</a></p></section>')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新增五位人物 · 九图参考库</title><style>
    *{box-sizing:border-box}body{margin:0;color:#243044;background:#f3f5f7;font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1320px;margin:auto;padding:30px 24px 56px}h1{font-size:30px;margin:0 0 10px}h2{margin:0;font-size:25px}h2 span{font-size:14px;font-weight:500;color:#5a6f7c}p{margin:10px 0;color:#59687a}a{color:#22647a}.summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:24px 0}.person{display:flex;flex-direction:column;gap:4px;text-decoration:none;background:white;border:1px solid #dce4eb;border-radius:12px;overflow:hidden;padding-bottom:14px}.person img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#e5e5e5}.person strong{font-size:20px;margin:7px 12px 0}.person span{font-size:13px;margin:0 12px;color:#566775}.person small{font-size:12px;margin:0 12px;color:#5c6e7d}section{scroll-margin-top:20px;background:white;padding:22px;border:1px solid #dce4eb;border-radius:14px;margin-top:28px}.photos{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:20px}figure{margin:0;border:1px solid #dfe5ea;border-radius:8px;overflow:hidden}figure img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:contain}figcaption{font-size:14px;padding:8px;text-align:center}.back{text-align:right;font-size:13px}.note{font-size:14px;border-left:3px solid #b39350;background:#fffaf0;padding:8px 14px}footer{font-size:13px;color:#637386;margin-top:24px}@media(max-width:850px){.summary{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:550px){main{padding:22px 12px}.summary,.photos{grid-template-columns:repeat(2,minmax(0,1fr))}section{padding:14px}h1{font-size:26px}}
    </style></head><body><main id="top"><h1>新增五位人物</h1><p>沿用九图标准：每人3张面部近景＋6张全身，共45张新参考。点击人物查看完整九图，点击单图查看原图。</p><p><a href="/#character-library">打开人物模型库</a> · <a href="/character-reference-pack.html">查看原有林安与周言</a></p><div class="note">五位均为虚构成年人物。请比较人物长相、年龄观感、发型和各方向服装；最终人物偏好待你确认。</div><div class="summary">'''+''.join(cards)+'</div>'+''.join(sections)+'''<footer>原图1536×864。左右按画面朝向标注；静态参考没有进行精确三维标定。原有人物与旧版本保留。</footer></main></body></html>'''
    for target in [ROOT/'web/public/character-library-five.html',ROOT/'web/dist/character-library-five.html']:target.write_text(page,encoding='utf-8')
    write(FOLDER/'preview.json',dict(url=r.base+'/character-library-five.html',characters=5,references=45))
    print('Five-character local review page written',flush=True)
if __name__=='__main__':render()

"""Build a local review page using accepted library references and fresh clips."""
from html import escape
from urllib.parse import quote
from run import Run,PEOPLE,SLOTS,ROOT,FOLDER,write

LABELS={'front':'正面','threeQuarterLeft':'左前侧','threeQuarterRight':'右前侧','left':'左侧','right':'右侧','back':'背面','closeUp':'面部近景','fullBody':'全身'}
OUTFITS={'linan':'象牙白针织衫 · 深灰长裤 · 白色运动鞋','zhouyan':'藏蓝衬衫 · 米色长裤 · 深棕皮鞋'}
def url(path):return '/api/media?assetPath='+quote(path,safe='')
def render():
    r=Run();r.access();r.preserve();library=r.api('/api/character-library');sections=[]
    for person in PEOPLE:
        entry=r.state['people'][person['key']];version=next(v for v in library['versions'] if v['id']==entry['versionId']);figures=[]
        for view,framing in SLOTS:
            ref=next(ref for ref in version['payload']['references'] if ref['view']==view and ref['framing']==framing)
            label=LABELS[view]+' · '+LABELS[framing]
            figures.append('<figure><a href="'+url(ref['assetPath'])+'" target="_blank" rel="noopener"><img loading="lazy" width="1536" height="864" src="'+url(ref['assetPath'])+'" alt="'+escape(person['name']+' '+label)+'"></a><figcaption>'+label+'</figcaption></figure>')
        video=r.state['tasks'][person['key']+'-fullBody-video']
        sections.append('<section aria-labelledby="'+person['key']+'"><header><h2 id="'+person['key']+'">'+person['name']+' <span>v'+str(version['version'])+' · 9/9</span></h2><p>'+OUTFITS[person['key']]+'</p></header><div class="photos">'+''.join(figures)+'</div><div class="clip"><div><h3>从正面全身参考生成的视频</h3><p>约5.17秒的小幅动作验证。请检查人物、发型、衣服与鞋子在运动中是否稳定。</p></div><video aria-label="'+person['name']+'全身参考调用视频" controls preload="metadata" playsinline src="'+url(video['path'])+'"></video></div></section>')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人物九图参考包 · 验收</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#202b3b;font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1320px;margin:auto;padding:36px 24px 64px}h1{font-size:32px;margin:0 0 12px}h2{margin:0;font-size:25px}h2 span{font-size:15px;font-weight:500;color:#496772}h3{margin-top:0}p{color:#536171;margin:8px 0}nav{display:flex;gap:20px;margin:18px 0 28px}a{color:#22647a}section{background:white;padding:24px;margin-top:28px;border:1px solid #dfe5ea;border-radius:16px}.photos{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:22px}figure{margin:0;border:1px solid #dfe5ea;border-radius:8px;overflow:hidden;background:#fafafa}img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:contain}figcaption{padding:8px 12px;text-align:center;font-size:14px}.clip{display:grid;grid-template-columns:1fr 2fr;gap:24px;align-items:center;margin-top:28px;padding-top:24px;border-top:1px solid #e4e8ec}video{display:block;width:100%;background:#18212c;border-radius:8px}.note{border-left:4px solid #b18b3e;padding:8px 16px;background:#fffaf0}footer{margin-top:26px;color:#677482;font-size:14px}@media(max-width:760px){main{padding:24px 12px}section{padding:14px}.photos{grid-template-columns:repeat(2,minmax(0,1fr))}.clip{grid-template-columns:1fr}h1{font-size:26px}}
    </style></head><body><main><h1>人物九图参考包</h1><p>林安、周言各3张面部近景与6张全身图。点击图片可查看原图。</p><div class="note">技术验收通过，人物一致性与表演效果待人工复核。静态多视角参考尚不能保证视频中的完整转身或复杂动作。</div><nav><a href="/#character-library">打开人物模型库</a><a href="#linan">林安</a><a href="#zhouyan">周言</a></nav>'''+''.join(sections)+'''<footer>左右按画面朝向标注：鼻尖朝画面左为左侧，朝画面右为右侧。图片1536×864；调用视频864×480 / 24FPS。旧版人物与视频均保留。</footer></main></body></html>'''
    for target in [ROOT/'web/public/character-reference-pack.html',ROOT/'web/dist/character-reference-pack.html']:
        target.write_text(page,encoding='utf-8')
    write(FOLDER/'preview-page.json',dict(url=r.base+'/character-reference-pack.html',characters=2,references=18,videos=2))
    print('Local nine-reference and two-clip review page written',flush=True)
if __name__=='__main__':render()

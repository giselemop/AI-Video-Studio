"""Create a read-only before/after page for the actual cutaway edit."""
import json
from character_wide_cutaway import ROOT,DATA,OUT,sha,write

def main():
    s=json.loads((OUT/'run.json').read_text(encoding='utf-8'));final=s['editTasks']['final'];checks=json.loads((OUT/'final-checks.json').read_text(encoding='utf-8'))
    if final.get('status')!='Succeeded' or checks['status']!='Passed' or sha(DATA/final['assetPath'])!=final['sha256']:raise RuntimeError('Actual final edit must be verified')
    data=dict(finalTaskId=final['id'],finalSha256=final['sha256'],originalTaskId=s['sourceVideoTaskId'],originalSha256=s['sourceVideoSha256'],imageTaskId=s['images'][-1]['id'],imagePath=s['images'][-1]['assetPath'],videoTaskId=s['video']['id'],cutStartFrame=s['cutStartFrame'],cutEndFrame=s['cutEndFrame'],review=s['finalInspection'],contentReview='NeedReview',publication='Blocked')
    html=(ROOT/'tools/character_wide_review.template.html').read_text(encoding='utf-8').replace('__PAYLOAD__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    for folder in [ROOT/'web/public',ROOT/'web/dist']:
        path=folder/'character-wide-cutaway.html'
        if path.exists() and path.read_text(encoding='utf-8')!=html:raise RuntimeError('Existing page differs; preserve it')
        if not path.exists():path.write_text(html,encoding='utf-8')
    write(OUT/'page.json',dict(url='http://127.0.0.1:18080/character-wide-cutaway.html',sha256=sha(ROOT/'web/public/character-wide-cutaway.html')))
    print('Real before/after edit page created; content remains NeedReview.')

if __name__=='__main__':main()

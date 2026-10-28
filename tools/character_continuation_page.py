"""Create a user-facing page only for this run's verified real final artifact."""
import json
from character_continuation import ROOT,DATA,OUT,OLD,sha,write

def main():
    s=json.loads((OUT/'run.json').read_text(encoding='utf-8'));old=json.loads(OLD.read_text(encoding='utf-8'));final=s['finalVideo']
    technical=json.loads((OUT/'final-technical-checks.json').read_text(encoding='utf-8'))
    if final.get('status')!='Succeeded' or technical['status']!='Passed' or sha(DATA/final['assetPath'])!=final['sha256']:raise RuntimeError('Final artifact must be real, unchanged and technically verified')
    data=dict(finalTaskId=final['taskId'],finalSha256=final['sha256'],projectId=s['projectId'],episodeId=s['episodeId'],videoTaskIds=[s['sourceVideoTaskId']]+[x['videoTaskId'] for x in s['shots']],narrationTaskIds=[x['taskId'] for x in s['narration']],musicTaskId=s['music']['taskId'],referencePath=old['sourceReference']['assetPath'],inspection=s['finalInspection'],contentReview='NeedReview',publication='Blocked')
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c');html=(ROOT/'tools/character_continuation_review.template.html').read_text(encoding='utf-8').replace('__PAYLOAD__',payload)
    for directory in [ROOT/'web/public',ROOT/'web/dist']:
        target=directory/'character-story-15s.html'
        if target.exists() and target.read_text(encoding='utf-8')!=html:raise RuntimeError('Existing page differs; preserve it')
        if not target.exists():target.write_text(html,encoding='utf-8')
    write(OUT/'preview-page.json',dict(url='http://127.0.0.1:18080/character-story-15s.html',sha256=sha(ROOT/'web/public/character-story-15s.html'),taskId=final['taskId']))
    print('Real 15-second sound-enabled review page created; final content remains NeedReview.')

if __name__=='__main__':main()

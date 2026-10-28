"""Create the read-only page only for verified actual full-body output."""
import json
from character_fullbody_scene import ROOT, DATA, OUT, sha, write

def main():
    s=json.loads((OUT/'run.json').read_text(encoding='utf-8'))
    report=json.loads((OUT/'final-checks.json').read_text(encoding='utf-8'))
    final=s['editTasks']['final'];video=s['videos'][-1];frame=s['images'][-1]
    if (report['status']!='Passed' or report['taskId']!=final['id']
            or sha(DATA/final['assetPath'])!=final['sha256']
            or video['inspection']['decision']!='Failed'
            or video['rangeInspection']['decision']!='Passed'
            or frame['inspection']['decision']!='Passed'):
        raise RuntimeError('The actual full-body video and completed edit must be inspected and verified')
    data=dict(finalTaskId=final['id'],finalSha256=final['sha256'],previousTaskId=s['baseTaskId'],
        previousSha256=s['baseSha256'],imageTaskId=frame['id'],imagePath=frame['assetPath'],
        imageSha256=frame['sha256'],videoTaskId=s['editTasks']['insert']['id'],
        sourceVideoTaskId=video['id'],sourceVideoSha256=video['sha256'],
        referencePath=s['cutReference']['assetPath'],referenceSha256=s['cutReference']['sha256'],
        referenceFrame=s['cutReference']['frame'],contentReview='NeedReview',publication='Blocked')
    payload=json.dumps(data,ensure_ascii=False).replace('<',r'\u003c')
    html=(ROOT/'tools/character_fullbody_review.template.html').read_text(encoding='utf-8').replace('__PAYLOAD__',payload)
    for folder in [ROOT/'web/public',ROOT/'web/dist']:
        target=folder/'character-fullbody-story.html'
        if target.exists() and target.read_text(encoding='utf-8')!=html:
            raise RuntimeError('Existing page differs; preserve it for review')
        if not target.exists():target.write_text(html,encoding='utf-8')
    write(OUT/'page.json',dict(url='http://127.0.0.1:18080/character-fullbody-story.html',
                              sha256=sha(ROOT/'web/public/character-fullbody-story.html')))
    print('Actual full-body story comparison page created for review.')

if __name__=='__main__':main()

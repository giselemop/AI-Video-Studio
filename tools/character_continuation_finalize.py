"""Complete only after actual media, browser and protected-state verification."""
import json,msvcrt
from character_continuation import Continuation,ROOT,DATA,OUT,sha,write

def main():
 with (OUT/'controller.lock').open('a+b') as lock:
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    p=Continuation();s=p.state;p.preserve();p.idle()
    for name in ['api-checks.json','mix-preflight-checks.json','final-technical-checks.json']:
        assert json.loads((OUT/name).read_text(encoding='utf-8'))['status']=='Passed',name
    assert json.loads((OUT/'audio-checks.json').read_text(encoding='utf-8'))['technicalStatus']=='Passed'
    for shot in s['shots']:
        assert shot['status']=='Succeeded' and shot['inspection']['payload']['decision']=='Passed' and sha(DATA/shot['assetPath'])==shot['sha256']
        assert json.loads((DATA/shot['technicalCheckPath']).read_text(encoding='utf-8'))['status']=='Passed'
    failed=s['shots'][0]['videoHistory'][0];assert failed['videoTaskId']==1561 and failed['inspection']['payload']['decision']=='Failed' and sha(DATA/failed['assetPath'])==failed['sha256']
    for item in [*s['narration'],s['music'],s['silentPreview'],s['finalVideo']]:assert item['status']=='Succeeded' and sha(DATA/item['assetPath'])==item['sha256']
    browser=json.loads((OUT/'browser-playback.json').read_text(encoding='utf-8'))
    assert browser['ended'] and browser['error'] is None and not browser['consoleErrors'] and abs(browser['duration']-15)<.1 and not browser['muted']
    assert (OUT/'screenshots/shot2-task-status.png').is_file() and (OUT/'screenshots/final-playback.png').is_file()
    page=ROOT/'web/public/character-story-15s.html';assert sha(page)==sha(ROOT/'web/dist/character-story-15s.html')
    assert json.loads((DATA/'CharacterScene20261027/run.json').read_text(encoding='utf-8'))['generationHold']['active']
    assert s.get('finalInspection') and s.get('finalInspectionScope')=='PreviewInspection'
    s.update(completed=True,stage='CompletedForReview',technicalStatus='Passed',contentReview='NeedReview',publication='Blocked');p.save()
    write(OUT/'final-checks.json',dict(status='Passed',finalTaskId=s['finalVideo']['taskId'],sourceVideoTaskIds=[s['sourceVideoTaskId']]+[x['videoTaskId'] for x in s['shots']],narrationTaskIds=[x['taskId'] for x in s['narration']],musicTaskId=s['music']['taskId'],failedOriginalShot2=failed['videoTaskId'],queueIdle=True,protectedFilesUnchanged=True,twoPersonHoldActive=True,browserPlayback=True,contentReview='NeedReview',publication='Blocked'))
    print('Completed for review; actual media, sources, browser and idle queue verified.')

if __name__=='__main__':main()

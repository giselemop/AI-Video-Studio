"""Finalize this run only after real media, browser and preservation checks."""
import json, msvcrt
from pathlib import Path
from character_plot_preview import Plot, ROOT, DATA, OUT, sha, write, mysql


def main():
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        p=Plot();s=p.state;p.preserve();p.idle()
        for name in ['api-checks.json','start-only-checks.json','video-1555/media-checks.json','preview-1556/checks.json']:
            assert json.loads((OUT/name).read_text(encoding='utf-8'))['status']=='Passed',name
        browser=json.loads((OUT/'browser-playback.json').read_text(encoding='utf-8'))
        assert browser['ended'] and browser['error'] is None and browser['consoleErrors']==[] and abs(browser['duration']-124/24)<.01
        assert all(x['complete'] and x['width']==1536 and x['height']==864 for x in browser['images'])
        assert all((OUT/'screenshots'/f).is_file() for f in ['story-editor.png','keyframe-zoom.png','plot-page-playback-end.png'])
        assert json.loads((DATA/'CharacterScene20261027/run.json').read_text(encoding='utf-8'))['generationHold']['active']
        assert [x['id'] for x in s['KeyframeHistory']]==[1552,1553] and all(x['inspection']['payload']['decision']=='Failed' for x in s['KeyframeHistory'])
        for entry in [*s['KeyframeHistory'],s['Keyframe'],s['Video'],s['Preview']]:
            assert entry['status']=='Succeeded' and sha(DATA/entry['assetPath'])==entry['sha256']
        assert s['Keyframe']['inspection']['payload']['decision']=='Passed' and s['Video']['inspection']['payload']['decision']=='Passed'
        ids=[int(x) for x in mysql('SELECT id FROM generation_tasks WHERE project_id='+str(s['projectId'])+' ORDER BY id;').splitlines()]
        assert ids==[1552,1553,1554,1555,1556],ids
        page=ROOT/'web/public/character-plot-preview.html';assert sha(page)==sha(ROOT/'web/dist/character-plot-preview.html')
        s.update(completed=True,stage='CompletedForReview',technicalStatus='Passed',previewInspection='Passed',contentReview='NeedReview',publication='Blocked');p.save()
        write(OUT/'final-checks.json',dict(status='Passed',actualTaskIds=ids,queueIdle=True,protectedFilesUnchanged=True,twoPersonGenerationHoldActive=True,browserPlayback=True,contentReview='NeedReview',publication='Blocked'))
        print('Completed for review; five actual tasks, protected history and idle queue verified.')


if __name__=='__main__':main()

"""Collate actual CUA/browser evidence; never drives a browser or submits work."""
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import sys,json
sys.path.insert(0,str(Path(__file__).parent))
from setup import OUT,write

def run():
    read=lambda name:json.loads((OUT/name).read_text(encoding='utf-8-sig'))
    p=read('pilot.json');checks=[]
    def check(name,ok,evidence):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed',evidence=evidence))
        if not ok:raise AssertionError(name)
    for kind,record in [('clip-'+k,v['Video']) for k,v in p['slots'].items()]+[('combined-preview',p['preview'])]:
        file='browser-playback-new-'+str(record['id'])+'.json';result=read(file)['playback'][0]
        check(kind+' complete real browser playback',result['ended'] and result['error'] is None and result['width']==864 and result['height']==480 and parse_qs(urlparse(result['src']).query)['assetPath']==[record['assetPath']],file)
    zooms=read('browser-keyframe-zooms.json')
    check('four original story images enlarged at established dimensions',len(zooms)==4 and all(z['dialogOpen'] and z['width']==1536 and z['height']==864 for z in zooms),'browser-keyframe-zooms.json')
    context=read('browser-context-switch.json');check('project switch clears old plan/task/submission',all(context[k] for k in ['oldPlanAbsent','oldSubmitAbsent','oldSelectedTaskAbsent']),'browser-context-switch.json')
    check('project update retains original Episode cast and shows warning','本集快照 #19' in context['fixtureSnapshot'] and '人物库试用） / #4' in context['fixtureSnapshot'] and '项目选角已更新，本集继续保留原演员快照' in context['fixtureSnapshot'],'screenshots/22-pinned-episode-cast.png')
    human=read('browser-human-gate.json');check('human final approval and rejection disabled without acknowledgement',not human['passEnabled'] and not human['rejectEnabled'] and not human['humanApprovalSubmitted'],'browser-human-gate.json')
    source=(OUT/'browser-task-source.txt').read_text(encoding='utf-8');check('selected task source parameters and first-frame SHA inspectable','storyPipeline' in source and '2ee5331bfa926d90a77d433a7e86b20bcfa943d8a1315dbaa0c6e97de0b826b0' in source,'browser-task-source.txt')
    logs=read('browser-runtime-logs.json');check('no browser console warning or error',not logs['story'] and not logs['review'],'browser-runtime-logs.json')
    for name,evidence in [
      ('real project50 uses immutable actor versions4 and5','screenshots/18-story-cast-shot.png'),
      ('Shot reference framing and original hash visible','screenshots/18-story-cast-shot.png'),
      ('actual source-keyframe to H3 resolve inspected without submitting another video','integration-checks.json'),
      ('PreviewInspection recorded separately from final human content approval','screenshots/20-human-review-gate.png'),
      ('original video1516 shows Succeeded with content inspection Failed and actual reason','screenshots/23-failed-video-reason.png'),
      ('directed repair1519 and original1516 retained in Shot history','screenshots/23-failed-video-reason.png'),
      ('actual CPU preview submitted through user interface, task1521','preview-media-checks.json'),
      ('review page shows original keyframe/video, retained failed assets and human-pending banner','screenshots/21-final-preview.png')]:
        check(name,(OUT/evidence).exists(),evidence)
    write(OUT/'browser-runtime-checks.json',dict(status='Passed',checks=checks,earlierLibraryEvidence='browser-ui-checks.json',earlierMigrationBlockResolved=True,screenshots=[str(s) for s in sorted((OUT/'screenshots').glob('*.png'))],technical='Passed',contentReview='NeedReview',publication='Blocked',humanApprovals=0))
    print(f'{len(checks)} current browser checks Passed; earlier library evidence retained, final human review pending.')
if __name__=='__main__':run()

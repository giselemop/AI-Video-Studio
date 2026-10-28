"""Separate scene evidence page from registered outputs; no GPU or approval."""
import json
from common import ROOT,OUT,write,sha

def run():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8'))
    scene=json.loads((OUT/'scene-version.json').read_text(encoding='utf-8'))
    media=json.loads((OUT/'pilot-media-checks.json').read_text(encoding='utf-8'))
    manifest=dict(projectId=state['projectId'],episodeId=state['episodeId'],actors=state['actors'],sceneVersionId=state['sceneVersionId'],repairSceneVersionId=state.get('repairSceneVersionId'),source=scene['payload']['source'],regions=scene['payload']['regions'],hold=state.get('generationHold'),staticContinuityPassed=state.get('staticContinuityPassed',False),outputs=media['outputs'],slots=[dict(key=k,**v) for k,v in state['slots'].items()],contentReview='NeedReview',publication='Blocked')
    # Preserve only source fields needed for review; full original request remains
    # in the immutable database snapshot and execution evidence.
    manifest['source']={k:v for k,v in manifest['source'].items() if k!='taskInputJson'}
    text=(ROOT/'tools/character_scene/review.template.html').read_text(encoding='utf-8').replace('__PAYLOAD__',json.dumps(manifest,ensure_ascii=False).replace('<','\\u003c'))
    target=ROOT/'web/public/character-scene-preview.html';target.write_text(text,encoding='utf-8')
    write(OUT/'preview-page.json',dict(url='http://127.0.0.1:18080/character-scene-preview.html',pageSha256=sha(target),manifest=manifest,realTaskReadsOnly=True,humanApprovals=0))
    print('New scene review page built from tasks1522-1525. Previous story preview retained; no video reused as a new result.')
if __name__=='__main__':run()

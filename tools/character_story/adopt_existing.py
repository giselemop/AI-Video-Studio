"""Adopt already-generated expansion outputs as NeedReview candidates only.
Five known missing/bad quarter slots remain empty; never regenerate or freeze.
"""
from pathlib import Path
import requests,json,sys
sys.path.insert(0,str(Path(__file__).parent))
from setup import DATA,OUT,write,sha
FOLDER=DATA/'CharacterExpansionFive20261026'
SLOTS=[('front','closeUp'),('threeQuarterLeft','closeUp'),('threeQuarterRight','closeUp'),('front','fullBody'),('threeQuarterLeft','fullBody'),('left','fullBody'),('back','fullBody'),('right','fullBody'),('threeQuarterRight','fullBody')]
MISSING={('xuzhixia','threeQuarterLeft'),('xuzhixia','threeQuarterRight'),('chenyu','threeQuarterRight'),('suwanqing','threeQuarterRight'),('shenyulan','threeQuarterLeft')}
def run():
    original=FOLDER/'run.json';originalHash=sha(original);state=json.loads(original.read_text(encoding='utf-8'));selection=json.loads((FOLDER/'selection.json').read_text(encoding='utf-8'))
    assert state['stage']=='AwaitingPackInspection' and not state.get('completed',False)
    session=requests.Session();auth=session.get('http://127.0.0.1:18080/api/auth/status').json();assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];session.headers['X-CSRF-Token']=auth['csrfToken']
    rows=[]
    for person,record in state['people'].items():
        for view,framing in SLOTS:
            if framing=='fullBody' and (person,view) in MISSING:continue
            logical=person+'-'+view+'-'+framing;key=selection.get(logical,logical);task=state['tasks'][key]
            assert task['status']=='Succeeded' and sha(DATA/task['path'])==task['sha256']
            reason='从原已成功任务收集为待审核候选，未自动批准或入库。'
            if person in ['chenyu','suwanqing'] and view=='threeQuarterLeft' and framing=='fullBody':reason='原请求为右前侧，实际图片鼻尖朝画面左且可见前胸；按实际图纠正为左前侧。保留原任务、原请求及缺失右前侧记录，待人工复核。'
            response=session.post('http://127.0.0.1:18080/api/character-workshop/'+str(record['characterId'])+'/collect',json=dict(taskId=task['id'],view=view,framing=framing,changeReason=reason),timeout=60)
            if not response.ok:raise RuntimeError(str(task['id'])+' '+response.text[:500])
            rows.append(dict(characterId=record['characterId'],taskId=task['id'],logicalSlot=logical,sourceKey=key,referenceId=response.json()['id'],sha256=task['sha256'],status='NeedReview'))
            write(OUT/'adopted-candidates.json',dict(completed=False,rows=rows,missing=[dict(person=p,view=v,framing='fullBody') for p,v in sorted(MISSING)],newGpuTasks=0,libraryVersionsCreated=0))
    assert len(rows)==40 and sha(original)==originalHash
    write(OUT/'adopted-candidates.json',dict(completed=True,rows=rows,missing=[dict(person=p,view=v,framing='fullBody') for p,v in sorted(MISSING)],originalCheckpointUnchanged=True,originalCheckpointSha256=originalHash,newGpuTasks=0,libraryVersionsCreated=0,humanApprovals=0,contentReview='NeedReview',publication='Blocked'))
    print('40 existing actual outputs adopted as NeedReview candidates; five known quarter slots remain missing; no new GPU task or immutable version.')
if __name__=='__main__':run()

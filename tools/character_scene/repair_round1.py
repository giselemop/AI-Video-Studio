"""Apply the diagnosed first correction only; replay preserves existing tasks."""
from pathlib import Path
import sys,msvcrt
sys.path.insert(0,str(Path(__file__).parent))
from common import OUT,write
from pilot import Pilot

FIXES={
 'search':('仅修1522：隔离场景旧头部姿态并扩大人物区域，seed+100；女方背离右侧男方望向画面左外侧书架，男方近正面，四手下垂。','POSE CORRECTION: The woman on picture LEFT must look AWAY from the man, toward the OUTER LEFT bookshelf. Her nose and eyes point picture LEFT; the back of her head is on picture RIGHT. Do NOT make her look right toward the man. The man on picture RIGHT remains nearly frontal toward camera. Exactly two arms and two hands per person, all FOUR hands hanging DOWN beside hips. Keep body sizes and clothes. Cropped medium two-shot, no full-body miniatures, no hand gestures, extra hands or translucent arms.'),
 'notice':('仅修1523：隔离旧头部姿态、扩大人物区域并seed+100，明确两人鼻尖同向画面左，女方不回看男方，保持站位和四手下垂。','GAZE CORRECTION: BOTH people look in the SAME direction toward the OUTER LEFT edge of the picture and the left bookshelf. BOTH noses point picture LEFT, parallel gazes. The left woman must NOT look right toward the man. The right man follows her gaze toward picture LEFT, NOT mutual eye contact. Front three-quarter left heads, both identities recognizable. Exactly FOUR hands total, all hands DOWN beside hips. Same cream sweater/gray trousers and navy shirt/beige trousers. Original cropped medium-shot body scale.'),
 'respond':('仅修1525：隔离旧头姿、扩大人物区域并seed+100，左女右男各两臂两手全部下垂于髋部两侧，不抬手不指向，保留相向回应起始姿态。','ANATOMY CORRECTION: The woman has exactly TWO arms and TWO hands, BOTH arms hanging DOWN. Her two hands are beside her two hips; NO raised arm, NO pointing hand, NO hand near her chest, NO extra hand near her hips. The man also has exactly two relaxed arms and two hands DOWN. Exactly FOUR hands total. Keep left/right positions and calm mutual eye contact, mouths CLOSED and heads neutral before a tiny nod. Keep original cropped medium-shot body scale and all clothes.')}

def run():
    p=Pilot();write(OUT/'workflow-scan-masked.json',p.api('/api/workflows/scan',{}))
    item=p.state['slots']['search'];body=dict(planId=item['planId'],profile='baseline480',seed=2026102831,idempotencyKey=p.key('negative-budget-reset'))
    response=p.s.post(p.base+'/api/character-story/generate/Keyframe',json=body,timeout=90)
    assert response.status_code==422 and any(word in response.text for word in ['修复','重做']),response.text
    wrong=dict(body,repairOfTaskId=1523,changeReason='wrong-shot negative check',promptAdjustment='gaze left',idempotencyKey=p.key('negative-other-shot-repair'))
    other=p.s.post(p.base+'/api/character-story/generate/Keyframe',json=wrong,timeout=90);assert other.status_code==422 and '其他镜头' in other.text,other.text
    write(OUT/'revision-budget-checks.json',dict(status='Passed',checks=[dict(name='new scene/plan version cannot reset initial-generation budget',status='Passed',http=response.status_code),dict(name='other Shot cannot be repair source',status='Passed',http=other.status_code)],gpuCreatedByChecks=0))
    for slot,(note,prompt) in FIXES.items():
        if p.state['slots'][slot]['Keyframe'].get('repairAttempt',0)>=1:print('Preserved existing repair for '+slot);continue
        p.repair(slot,'Keyframe',note,prompt)
if __name__=='__main__':
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);run()

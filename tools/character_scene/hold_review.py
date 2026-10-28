"""Persist the user's explicit review hold; no task submission or approval."""
import json,msvcrt,datetime
from common import OUT,write

def run():
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        path=OUT/'run.json';state=json.loads(path.read_text(encoding='utf-8'))
        state.update(stage='AwaitingHumanReview',completed=False,staticContinuityPassed=False)
        if not state.get('generationHold',{}).get('active'):
            state['generationHold']=dict(active=True,reason='用户明确回复“保持待审”；保留拒绝记录与既有人物版本，暂停新增图像和视频任务。',userReply='保持待审',recordedAt=datetime.datetime.now().astimezone().isoformat(),resumeRequires='Explicit user instruction and explicitly chosen reviewed actor/scene versions; do not silently replace versions4/5.')
        write(path,state)
    print('User review hold checkpointed. Existing four images and all plan/version history retained; no generation or human approval.')
if __name__=='__main__':run()

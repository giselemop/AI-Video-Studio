"""Revise this run's starting still without changing the original shot plan.

The plan request is checkpointed and idempotent. Checks do not queue GPU work.
"""
import copy, json, msvcrt
from character_plot_preview import Plot, OUT, mysql, write


def main():
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        p=Plot(); s=p.state; p.preserve(); p.idle()
        frame=s['Keyframe']
        assert frame['id']==1553 and frame['inspection']['payload']['decision']=='Failed'
        assert [e['id'] for e in s['KeyframeHistory']]==[1552]
        if not s.get('StartPlanPending') and s['planId']==44:
            s.setdefault('PlanHistory',[]).append(dict(planId=s['planId'],sha256=s['planSha256'],body=s['planBody'],reason='保留已有关键帧计划；明确分离静态起始状态和后续视频动作。'))
            body=copy.deepcopy(s['planBody'])
            body.update(keyframeStartOnly=True,idempotencyKey=p.key('shot-plan-start-only'))
            body['actors'][0]['action']='One woman alone beside a window. Head facing almost toward the camera, relaxed eyebrows, calm neutral closed mouth, not smiling or frowning. No other person or silhouette.'
            s['StartPlanPending']=body; p.save()
        if s.get('StartPlanPending'):
            body=s['StartPlanPending']
            record=p.api('/api/character-story/shots/'+str(s['shotId']),body)
            s.update(planId=record['id'],planSha256=record['sha256'],planBody=body,stage='StartOnlyPlanFrozen')
            s.pop('StartPlanPending');p.save()
        assert s['planId']!=44 and s['planBody']['keyframeStartOnly'] is True
        before=int(mysql('SELECT COUNT(*) FROM generation_tasks;'))
        count=int(mysql("SELECT COUNT(*) FROM generation_tasks WHERE JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.storyPipeline.shotId'))='257' AND JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.parameters.storyPipeline.kind'))='Keyframe';"))
        assert count==2, 'Unexpected prior attempt count; do not submit a repair.'
        request=dict(planId=s['planId'],profile='baseline480',seed=frame['body']['seed']+100,repairOfTaskId=1553,changeReason='起始表情不合格，分离静态起始状态和后续动作。',promptAdjustment='One woman alone, calm neutral expression, mouth closed.',idempotencyKey=p.key('start-check-resolve'))
        resolved=p.api('/api/character-story/resolve/Keyframe',request)
        params=resolved['task']['parameters']; marker=params['storyPipeline']; prompt=params['positive']
        checks=[]
        def check(name,ok):
            checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
            if not ok:
                write(OUT/'start-only-checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
        check('new immutable plan keeps approved original reference36',marker['planId']==s['planId'] and marker['inputSha256']==s['sourceReference']['assetSha256'])
        check('only starting state enters still prompt','calm neutral closed mouth' in prompt and 'As she recognizes the friend' not in prompt and 'turns her whole head' not in prompt)
        check('one identity image input',list(params['inputSlots'])==['firstFrame'])
        same=p.api('/api/character-story/shots/'+str(s['shotId']),s['planBody'])
        check('new plan request idempotent',same['id']==s['planId'] and same['sha256']==s['planSha256'])
        old_plan=next(x for x in p.api('/api/character-story/shots/'+str(s['shotId']))['plans'] if x['id']==44)
        check('previous plan remains readable and unchanged',old_plan['sha256']==s['PlanHistory'][0]['sha256'])
        old_resolved=p.api('/api/character-story/resolve/Keyframe',dict(planId=44,profile='baseline480',seed=1,idempotencyKey=p.key('old-prompt-check')))
        check('previous plan retains its original prompt','As she recognizes the friend' in old_resolved['task']['parameters']['positive'])
        wrong=dict(request,repairOfTaskId=1550,idempotencyKey=p.key('wrong-repair-check'))
        rejected=p.s.post(p.base+'/api/character-story/generate/Keyframe',json=wrong,timeout=90)
        check('unrelated task cannot be used as repair source',rejected.status_code==422)
        check('negative tests created no generation task',int(mysql('SELECT COUNT(*) FROM generation_tasks;'))==before)
        write(OUT/'start-only-resolved-check.json',resolved)
        write(OUT/'start-only-checks.json',dict(status='Passed',checks=checks,priorKeyframeCount=count,gpuSubmitted=0,humanApprovals=0))
        print(json.dumps(dict(planId=s['planId'],checks=len(checks),priorKeyframes=count,status='Passed'),ensure_ascii=False))


if __name__=='__main__': main()

"""Register inspected replacements and reject specific failed candidates; never approve."""
from run import Repair
from inventory import OUT, write

if __name__=='__main__':
 r=Repair();actions=[]
 for cid,rid,note in [(21,64,'Source task1479 has two opposite faces on one head; replaced by an inspected single-profile candidate.'),(20,53,'Requested left front-quarter is too close to profile; a new inspected left front-quarter is available.'),(22,69,'Requested left front-quarter is too close to profile; a new inspected left front-quarter is available.')]:
    ref=next(x for x in r.api(f'/api/characters/{cid}/references') if x['id']==rid)
    if ref['reviewStatus']=='Approved':
        actions.append(dict(referenceId=rid,status='Preserved human approval; repair available separately'));continue
    if ref['reviewStatus']!='Rejected':r.api(f'/api/characters/{cid}/references/{rid}/review',dict(decision='Rejected',note='Assistant visual defect inspection under the user-authorized repair; no human approval claimed. '+note))
    actions.append(dict(referenceId=rid,status='Rejected',reason=note))
 for key,e in r.state['tasks'].items():
    if e['visualStatus']=='Passed':
        marker=e['body']['parameters']['characterReferenceRepair'];cid=marker['characterId'];rid=marker.get('sourceReferenceId')
        if rid:
            ref=next(x for x in r.api(f'/api/characters/{cid}/references') if x['id']==rid)
            if ref['reviewStatus'] not in ('Rejected','Approved'):
                note=f"Assistant visual inspection: replaced by task {e['id']} after correcting head/body direction or anatomy. Original retained. This is a rejection of the candidate, not a human approval of the replacement."
                r.api(f'/api/characters/{cid}/references/{rid}/review',dict(decision='Rejected',note=note));actions.append(dict(referenceId=rid,status='Rejected',replacementTaskId=e['id']))
        r.collect(key)
 write(OUT/'reference-actions.json',dict(actions=actions,newHumanApprovals=0,immutableVersionsCreated=0))

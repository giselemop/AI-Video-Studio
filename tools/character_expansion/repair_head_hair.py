"""Second and final head-only revision for a specific hairstyle mismatch."""
from normalize_heads import body
from batch import Batch,PEOPLE,FOLDER,read,write,logical

HAIR={
 'chenyu':'The ORIGINAL SHORT black haircut ends above the ears and at the upper nape. Keep the original short textured crown. The neck and the area around the sweatshirt collar are clear of hair, exactly like the reference.',
 'suwanqing':'The ORIGINAL black hair is completely pulled back into ONE compact LOW BUN at the nape. All hair is securely gathered behind the head. The neck and shoulders are clear of loose hair, exactly like the reference.',
 'shenyulan':'The ORIGINAL SHORT salt-and-pepper PIXIE haircut ends above the ears and above the collar. Preserve the short swept fringe. The neck and the cardigan collar area are clear of hair, exactly like the reference.'
}
if __name__=='__main__':
    r=Batch();r.access();r.preserve()
    if r.state.get('completed') or r.state['stage'] not in ['AwaitingHeadsInspection','RefiningHeadHair']:raise RuntimeError('Inspect normalized heads before the second targeted repair')
    if any('-fullBody' in key for key in r.state['tasks']):raise RuntimeError('Do not replace identity after full-body derivation')
    r.save(stage='RefiningHeadHair');selection=read(FOLDER/'selection.json')
    for person in PEOPLE:
        if person['key'] not in HAIR:continue
        request=body(r,person);request['parameters']['positive']=request['parameters']['positive'].replace('Long hair may continue below the bottom crop. ','')+' '+HAIR[person['key']]
        request['parameters']['seed']=20261028001+PEOPLE.index(person)*100;request['stage']='Five-Characters-Head-Hair-Repair-2'
        key=logical(person,'front','closeUp');candidate=key+'-repair2';r.once(candidate,request);selection[key]=candidate;write(FOLDER/'selection.json',selection)
    r.save(stage='AwaitingHeadsInspection');write(FOLDER/'head-hair-repair-reasons.json',dict(reason='Generic long-hair continuation sentence caused unintended long hair in three identities. Remove it and positively describe each original short haircut or low bun. Use original raw identity, retain failed candidates; no third automatic head revision.',targets=list(HAIR),attempt=2,humanApproval=False))
    print('Three targeted hairstyle candidates ready for actual inspection',flush=True)

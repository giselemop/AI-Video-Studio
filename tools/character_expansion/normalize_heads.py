"""Identity-preserving collar, accessory, expression and crown-framing repair."""
import argparse
from batch import Batch,PEOPLE,FOLDER,read,write,logical

def body(r,person):
    original=r.state['tasks'][logical(person,'front','closeUp')]
    workflow=next(w for w in r.api('/api/workflows') if w['name']=='character_pack_klein4b_single_api')
    prompt='Exactly the SAME adult person as the reference: preserve facial identity, age, facial geometry, eyes, nose, skin lines, hair color and hairstyle. A SINGLE seamless realistic head-and-shoulders studio portrait, exactly frontal head, centered nose, both eyes equally visible. Pull the camera back slightly to include the COMPLETE crown of the head with clear empty margin above it. The head occupies about 75 percent of image height; crop at collarbone. Long hair may continue below the bottom crop. Calm neutral expression, CLOSED LIPS, no visible teeth. Only the '+person['collar']+' is visible along the bottom edge. Remove ALL jewelry, necklaces, earrings, chains and pendants; bare ears and bare neck. Plain LIGHT GRAY seamless studio background, soft even light, natural realistic skin. Exactly one person and one continuous portrait, no collage, inset, extra body, text or logos.'
    return dict(projectId=r.state['projectId'],taskType='Keyframe',workflowId=workflow['id'],inputImagePath=original['path'],stage='Five-Characters-Head-Normalization',maxRetries=0,parameters=dict(workflowVersion='character-pack-klein4b-single-1536-v1',inputSlots=dict(firstFrame=original['path']),positive=prompt,seed=20261027001+PEOPLE.index(person)*100,width=1536,height=864,steps=4,cfg=1))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');args=parser.parse_args();r=Batch();r.access();r.preserve()
    if r.state.get('completed') or r.state['stage'] not in ['AwaitingHeadsInspection','RefiningHeads']:raise RuntimeError('Complete raw identities before head-only normalization')
    r.save(stage='RefiningHeads')
    selection=read(FOLDER/'selection.json') if (FOLDER/'selection.json').exists() else {}
    for person in PEOPLE[:1] if args.pilot else PEOPLE:
        key=logical(person,'front','closeUp');candidate=key+'-repair1';r.once(candidate,body(r,person));selection[key]=candidate;write(FOLDER/'selection.json',selection)
    r.save(stage='AwaitingHeadsInspection')
    write(FOLDER/'head-repair-reasons.json',dict(scope='One bounded identity-preserving revision per original front close-up',reason='Original RealVis drafts contain accessories, mismatched collars, tight crown framing or an open-mouth smile. Retain all raw identities; selected nine-pack uses corrected collar, no accessories, complete crown and neutral lips.',humanApproval=False))
    print('Normalized head candidates retained; inspect before using as downstream anchors',flush=True)

"""Keep profile candidates; replace only wrongly side-on front-quarter slots."""
import argparse
from batch import Batch,PEOPLE,FOLDER,read,write,logical

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--slot',action='append',required=True,help='personKey:threeQuarterLeft or personKey:threeQuarterRight');parser.add_argument('--attempt',type=int,choices=[1,2],default=1);args=parser.parse_args()
    r=Batch();r.access();r.preserve()
    if r.state.get('completed') or r.state['stage'] not in ['AwaitingPackInspection','RepairingQuarters']:raise RuntimeError('Finish the original candidate stage first; use a single state writer')
    r.save(stage='RepairingQuarters');selection=read(FOLDER/'selection.json');reasons=read(FOLDER/'quarter-repair-reasons.json') if (FOLDER/'quarter-repair-reasons.json').exists() else {}
    for slot in args.slot:
        person_key,view=slot.split(':');person=next(p for p in PEOPLE if p['key']==person_key)
        if view not in ['threeQuarterLeft','threeQuarterRight']:raise ValueError('Only inspected front-quarter slots')
        key=logical(person,view,'fullBody');candidate=key+'-repair'+str(args.attempt)
        request=r.image_body(person,view,'fullBody');request['parameters']['seed']+=args.attempt*80000;request['stage']='Five-Characters-Front-Quarter-Repair-'+str(args.attempt)
        pose=r.selected(person,view,'closeUp');request['inputImagePath']=pose['path'];request['parameters']['inputSlots']['firstFrame']=pose['path']
        request['parameters']['positive']='Image1 already shows the CORRECT face angle and nose direction. Preserve the head orientation and face angle of image1 EXACTLY, including visibility of both eyes. Image2 supplies the complete wardrobe, shoes and body proportions. Rebuild ONE full-length standing studio photograph of exactly the same adult person. Match a GENTLE three-quarter diagonal body angle to the face direction in image1. Show a WIDE FRONT of the chest, BOTH shoulder lines and the FRONT waist clearly. Both feet point diagonally toward the camera. Entire crown, both hands, BOTH complete shoes and floor below remain in frame with generous empty margin. Arms relaxed down, closed lips, same hairstyle and age. Wear exactly: '+person['outfit']+'. '+person['body']+'. Plain light-gray background, soft even lighting. Exactly one continuous realistic photograph, one person, no inset, collage, text, logos or accessories.'
        reasons[candidate]=dict(originalTaskId=r.state['tasks'][key]['id'],poseSourceTaskId=pose['id'],reason='Actual candidate is too close to a profile or faces the wrong direction. Use the inspected matching face close-up as pose/identity input and the same front full-body wardrobe master; keep a gentle front-quarter torso.',attempt=args.attempt);write(FOLDER/'quarter-repair-reasons.json',reasons)
        r.once(candidate,request);selection[key]=candidate;write(FOLDER/'selection.json',selection)
    r.save(stage='AwaitingPackInspection');print('Front-quarter repair candidates ready for actual inspection',flush=True)

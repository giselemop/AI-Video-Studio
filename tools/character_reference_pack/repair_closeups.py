"""Targeted close-up repair: remove full-body/footwear instructions, retain failures."""
import argparse
import copy
from run import Run,PEOPLE,FOLDER,read,write

def candidate(person,view):
    r=Run();r.access();r.preserve()
    key=person['key']+'-'+view+'-closeUp';body=copy.deepcopy(r.state['tasks'][key]['body']);body.pop('idempotencyKey',None)
    angle={
      'front':'Face points directly at the camera, centered nose, equal visibility of both eyes, symmetrical frontal head orientation.',
      'threeQuarterLeft':'Turn the head about 40 degrees toward the LEFT edge of the image. The nose points left, both eyes remain visible.',
      'threeQuarterRight':'Turn the head about 40 degrees toward the RIGHT edge of the image. The nose points right, both eyes remain visible.'
    }[view]
    collar='ivory knit crew-neck collar' if person['key']=='linan' else 'navy blue shirt collar'
    body['parameters']['positive']='A SINGLE seamless photographic headshot of exactly the same adult person in the reference image. Preserve the original face identity, facial geometry, eyes, eyebrows, age, skin texture, black hair and hair parting. Tight head-and-shoulders framing: the complete head and hair occupy about 80 percent of image height; crop at the collarbone. '+angle+' Calm neutral closed-mouth expression, natural realistic skin. Only the '+collar+' is visible at the bottom edge. Plain light gray studio background, soft even light. Exactly one face and one continuous portrait, no inset, no collage, no extra figures, no text or logos.'
    body['parameters']['seed']+=500
    body['stage']='Character-Pack-CloseUp-Repair-1'
    return r,key,body

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');args=p.parse_args()
    r=Run()
    if r.state['stage']!='AwaitingPackInspection':raise RuntimeError('Finish original references first; retain a single writer for run.json')
    selected=read(FOLDER/'selection.json') if (FOLDER/'selection.json').exists() else {}
    targets=[(PEOPLE[0],'front')] if args.pilot else [(person,view) for person in PEOPLE for view in ['front','threeQuarterLeft','threeQuarterRight']]
    for person,view in targets:
        r,key,body=candidate(person,view)
        repaired=key+'-repair1'
        r.once(repaired,body)
        selected[key]=repaired;write(FOLDER/'selection.json',selected)
    print('Targeted close-up candidates retained; actual inspection required before publication to library',flush=True)

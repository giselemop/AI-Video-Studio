"""A bounded, isolated revision with preserved original request and media."""
import argparse
import copy
from batch import Batch,PEOPLE,FOLDER,read,write,logical

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--person',required=True);p.add_argument('--view',required=True);p.add_argument('--framing',required=True,choices=['closeUp','fullBody']);p.add_argument('--attempt',required=True,type=int,choices=[1,2]);p.add_argument('--reason',required=True);p.add_argument('--instruction',required=True);args=p.parse_args()
    r=Batch();r.access();r.preserve()
    if r.state.get('completed'):raise RuntimeError('Completed run is read-only; retain accepted library versions')
    if r.state['stage'] not in ['AwaitingHeadsInspection','AwaitingMastersInspection','AwaitingPackInspection']:raise RuntimeError('Finish the current generation stage before a targeted repair; single writer required')
    person=next(p for p in PEOPLE if p['key']==args.person);key=logical(person,args.view,args.framing)
    if args.view=='front' and any(k.startswith(person['key']+'-') and key not in k and k!=logical(person,'front','closeUp') for k in r.state['tasks']):
        if args.framing=='closeUp':raise RuntimeError('Cannot replace identity after derived views exist')
        if any(k.startswith(person['key']+'-') and '-fullBody' in k and '-front-fullBody' not in k for k in r.state['tasks']):raise RuntimeError('Do not change the wardrobe master after derived views exist')
    body=copy.deepcopy(r.state['tasks'][key]['body']);body.pop('idempotencyKey',None)
    body['parameters']['positive']+=' '+args.instruction;body['parameters']['seed']+=args.attempt*80000
    body['stage']='Five-Characters-Targeted-Repair-'+str(args.attempt)
    candidate=key+'-repair'+str(args.attempt)
    revisions=read(FOLDER/'repair-reasons.json') if (FOLDER/'repair-reasons.json').exists() else {}
    revisions[candidate]=dict(originalKey=key,reason=args.reason,instruction=args.instruction,attempt=args.attempt);write(FOLDER/'repair-reasons.json',revisions)
    r.once(candidate,body)
    selection=read(FOLDER/'selection.json') if (FOLDER/'selection.json').exists() else {};selection[key]=candidate;write(FOLDER/'selection.json',selection)
    print('Repair candidate retained and selected provisionally; inspect actual image before library capture',flush=True)

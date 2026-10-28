"""One directed warm-response candidate; retain all first takes and select explicitly."""
from run import *
PROMPT=('Photorealistic live-action two-shot of the exact same adult woman LEFT and man RIGHT on the sofa. '
    'At first the man looks at his phone. Just before answering his own Mandarin audio, he briefly raises his eyes and gently turns his face a little to screen LEFT toward the woman. '
    'He speaks with precise small lips and a relaxed jaw, playful restrained satisfaction rather than anger. His brow softens. '
    'As his reply finishes he meets her gaze for a moment with a very slight warm CLOSED-LIP half-smile, then relaxes naturally. '
    'The woman stays silent during this whole excerpt, lips gently touching, eyes toward him at screen RIGHT. '
    'She gives a subtle responsive closed-lip smile, one small soft cheek reaction and a natural blink, no frozen grin. '
    'Small continuous coordinated face and head motions, no sudden pose jumps. Preserve separate identities, exact clothes, phone, hands, room and warm window light, fixed camera.')
def generate(r):
    r.access();s=r.state;wf=next(x for x in s['workflows'] if x['name']=='wide');body=copy.deepcopy(s['wideDriverTaskIdInput'])
    body['stage']='Sync-Wide-Warm-Response-Repair1'
    graph=read(ROOT.parent/'Workflows'/wf['fileName']);body['parameters'].update(positive=PROMPT,negative=graph['5']['inputs']['negative']+', angry, cold stare, deeply furrowed brow, clenched jaw, fixed toothy grin, staring only at phone throughout')
    # Keep source, audio, seed, guidance, dimensions and sampling fixed; change the directed performance prompt only.
    asset(r,'wideRepairDriver',r.once('wideRepairDriverTaskId',body));r.save('AwaitingWideRepairInspection')
def act(r):
    r.access();s=r.state
    if read(FOLDER/'wide-repair-driver-review.json')['status']!='SelectedForActing':raise RuntimeError('Inspect actual directed repair first')
    for role,direction in [('Female','left-right'),('Male','right-left')]:
        key='wideRepair'+role;source=s['inputs']['wideReference'];driver=s['wideRepairDriverPath'];manifest=FOLDER/(key+'-acting.json')
        values=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),durationSeconds=57/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,
            repairProfile='dialogue-blink-v1',eyeResidualGain=1,faceDirection=direction,driverOrigin='Fresh local same-seed directed warm-response repair, same original audio; not human footage',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
        if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen repair acting differs')
        if not manifest.exists():write(manifest,values)
        body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='Sync-Acting-'+key,parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile='dialogue-blink-v1',engineVersion=sha(ROOT/'tools/dialogue_visual/acting.py')))
        result=r.once(key+'TaskId',body);asset(r,key,result)
        for suffix,needle in [('Receipt','local_visual_acting_receipt'),('Mask','dialogue_face_support')]:
            path=next(x['assetPath'] for x in result['results'] if x.get('available') and needle in x.get('assetPath',''));r.save(**{key+suffix+'Path':path,key+suffix+'Sha256':sha(media(path))})
def canvas(r):
    r.access();s=r.state;files={}
    source=s['inputs']['wideReference'];files['source']=dict(path=str(media(source)),sha256=sha(media(source)))
    for label,role in [('left','Female'),('right','Male')]:
        for suffix,target in [('',label),('Receipt',label+'Receipt'),('Mask',label+'Mask')]:
            path=s['wideRepair'+role+suffix+'Path'];files[target]=dict(path=str(media(path)),sha256=sha(media(path)))
    composite(r,'wideRepairMerge',dict(profile='dialogue-sync-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=57,files=files))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Canvas-wideRepair',parameters=dict(files=[s['wideRepairMergePath']],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=54/24,originalAudioVolume=0,outputName='wide_repair_canvas.mp4'))
    asset(r,'wideRepairCanvas',r.once('wideRepairCanvasTaskId',body));r.save('AwaitingWideRepairSelection')
def select(r):
    r.preserve();review=read(FOLDER/'wide-repair-review.json')
    if review['status']!='SelectedRepair':raise RuntimeError('Inspect actual first/repair candidates before selection')
    s=r.state
    if s.get('wideRepairSelected'):print('Selected repair already retained');return
    for name in ['wide-driver-contact.png','wide-canvas-contact.png','audit-canvas.json']:
        source=FOLDER/name;target=FOLDER/('initial-'+name)
        if source.exists() and not target.exists():shutil.copy2(source,target)
    changes={}
    for part in ['Driver','Female','FemaleReceipt','FemaleMask','Male','MaleReceipt','MaleMask','Merge','Canvas']:
        for suffix in ['Path','Sha256','TaskId','TaskIdInput','TaskIdStarted']:
            old='wide'+part+suffix;new='wideRepair'+part+suffix
            if old in s and new in s:
                changes['wideInitial'+part+suffix]=s[old];changes[old]=s[new]
    r.save('WideRepairSelected',wideRepairSelected=True,**changes)
    print('Directed repair selected; all initial paths/tasks retained separately')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['generate','act','canvas','select'],required=True);a=p.parse_args();r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Completed; no new tasks');sys.exit(0)
    globals()[a.stage](r)

"""Second directed candidate: new audio mouth motion, approved existing upper performance."""
from run import *
def prepare(r):
    import cv2
    r.access();r.preserve();s=r.state;old=read(DATA/'DialogueVisual20261025/run.json');source=old['inputs']['driver3']
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Approved-Pose-Excerpt',parameters=dict(files=[source],singlePass=True,targetWidth=832,targetHeight=480,targetFps=25,trimStartSeconds=56/25,targetDurationSeconds=57/25,originalAudioVolume=0,outputName='approved_pose_57frames.mp4'))
    asset(r,'widePose',r.once('widePoseTaskId',body))
    reference=FOLDER/'hybrid-reference.png'
    if not reference.exists():
        cap=cv2.VideoCapture(str(media(s['wideBaselinePath'])));ok,image=cap.read();cap.release()
        if not ok:raise RuntimeError('Approved baseline first frame absent')
        image=cv2.resize(image,(1024,576),interpolation=cv2.INTER_LANCZOS4)
        if not cv2.imwrite(str(reference),image):raise RuntimeError('Reference frame preparation failed')
    values=[source,s['wideBaselinePath'],s['widePosePath'],rel(reference)]
    frozen=dict(status='Passed',files=[dict(path=p,sha256=sha(media(p))) for p in values],referenceOperation='Deterministic excerpt first-frame downscale from approved1346; not newly generated still',
        poseOrigin='Existing self-generated1299 at nativeframe56,57frames25fps',poseOriginalStartSeconds=4+56/25,audioOriginalStartSeconds=150/24,poseVsAudioWindowOffsetSeconds=-.01,
        scope='Existing pose/expression cadence reused explicitly; fresh audio lip drive retained')
    path=FOLDER/'hybrid-inputs.json'
    if path.exists() and read(path)!=frozen:raise RuntimeError('Frozen hybrid preparation differs')
    if not path.exists():write(path,frozen)
    r.save('HybridInputsPrepared',wideHybridSourcePath=rel(reference),wideHybridSourceSha256=sha(reference))
def act(r):
    r.access();r.preserve();s=r.state
    for role,direction in [('Female','left-right'),('Male','right-left')]:
        key='wideHybrid'+role;manifest=FOLDER/(key+'-acting.json');source=s['wideHybridSourcePath'];driver=s['wideDriverPath']
        values=dict(sourcePath=str(media(source)),sourceSha256=sha(media(source)),drivingPath=str(media(driver)),drivingSha256=sha(media(driver)),posePath=str(media(s['widePosePath'])),poseSha256=s['widePoseSha256'],durationSeconds=57/25,drivingStartSeconds=0,animationRegion='all',drivingMultiplier=1,
            repairProfile='dialogue-hybrid-v1',eyeResidualGain=1,faceDirection=direction,driverOrigin='Fresh local1350 audio mouth motion; original approved1299 pose/expression driver; not human footage',licenseAcknowledgement='ExperimentalNonCommercialInsightFaceWeights')
        if manifest.exists() and read(manifest)!=values:raise RuntimeError('Frozen hybrid request differs')
        if not manifest.exists():write(manifest,values)
        body=dict(projectId=s['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,stage='Sync-Acting-'+key,parameters=dict(manifest=rel(manifest),manifestSha256=sha(manifest),repairProfile='dialogue-hybrid-v1',engineVersion=sha(ROOT/'tools/dialogue_sync/hybrid.py')))
        result=r.once(key+'TaskId',body);asset(r,key,result)
        for suffix,needle in [('Receipt','local_visual_acting_receipt'),('Mask','dialogue_face_support')]:
            path=next(x['assetPath'] for x in result['results'] if x.get('available') and needle in x.get('assetPath',''));r.save(**{key+suffix+'Path':path,key+suffix+'Sha256':sha(media(path))})
def canvas(r):
    r.access();s=r.state;files={}
    for label,key in [('source','wideHybridSourcePath'),('left','wideHybridFemalePath'),('right','wideHybridMalePath'),('leftReceipt','wideHybridFemaleReceiptPath'),('rightReceipt','wideHybridMaleReceiptPath'),('leftMask','wideHybridFemaleMaskPath'),('rightMask','wideHybridMaleMaskPath')]:
        p=s[key];files[label]=dict(path=str(media(p)),sha256=sha(media(p)))
    composite(r,'wideHybridMerge',dict(profile='dialogue-hybrid-compose-v1',phase='merge',width=1024,height=576,fps=25,frames=57,files=files))
    body=dict(projectId=s['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,stage='Sync-Canvas-wideHybrid',parameters=dict(files=[s['wideHybridMergePath']],singlePass=True,targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=54/24,originalAudioVolume=0,outputName='wide_hybrid_canvas.mp4'))
    asset(r,'wideHybridCanvas',r.once('wideHybridCanvasTaskId',body));r.save('AwaitingHybridInspection')
def select(r):
    r.preserve();s=r.state
    if read(FOLDER/'hybrid-review.json')['status']!='SelectedHybrid':raise RuntimeError('Inspect actual hybrid before selecting')
    if s.get('wideHybridSelected'):print('Hybrid selected already');return
    for name in ['wide-driver-contact.png','wide-canvas-contact.png','audit-canvas.json']:
        source=FOLDER/name;target=FOLDER/('initial-'+name)
        if source.exists() and not target.exists():shutil.copy2(source,target)
    changes={}
    for part in ['Female','FemaleReceipt','FemaleMask','Male','MaleReceipt','MaleMask','Merge','Canvas']:
        for suffix in ['Path','Sha256','TaskId','TaskIdInput','TaskIdStarted']:
            old='wide'+part+suffix;new='wideHybrid'+part+suffix
            if old in s and new in s:changes['wideInitial'+part+suffix]=s[old];changes[old]=s[new]
    r.save('HybridSelected',wideHybridSelected=True,**changes);print('Hybrid selected, initial candidate retained; audio driver still1350')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','act','canvas','select'],required=True);a=p.parse_args();r=Run('http://127.0.0.1:18081',FOLDER/'run.json')
    if r.state.get('completed'):r.preserve();print('Completed; no new tasks');sys.exit(0)
    globals()[a.stage](r)

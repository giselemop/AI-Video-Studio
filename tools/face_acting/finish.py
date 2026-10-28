"""Assemble only reviewed references/takes and packet-copy the unchanged original dialogue."""
import argparse
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image,ImageDraw
from run import ROOT,DATA,FOLDER,OLD,API,Run,read,write,sha,media,preserve,once,result


def selected_references(run):
    if run.state.get('referenceHashes'):
        preserve(run);print('Existing selected scene references preserved');return
    decision=read(FOLDER/'reference-selection.json')
    source=cv2.imread(str(media(run.state['sourceReference'])))
    for role in ['female','male']:
        choice=decision[role]
        if choice['decision']!='SelectedForVideo':raise RuntimeError('Actual same-person reference review required')
        path=media(choice['path'])
        if sha(path)!=choice['sha256']:raise RuntimeError('Selected reference changed')
        x,y,size,_=run.state['geometry'][role]['roi']
        patch=cv2.resize(cv2.imread(str(path)),(size,size),interpolation=cv2.INTER_LANCZOS4)
        mask_path=choice.get('mask',run.state['geometry'][role]['mask'])
        if choice.get('maskSha256') and sha(media(mask_path))!=choice['maskSha256']:raise RuntimeError('Selected expression mask changed')
        mask=cv2.resize(cv2.imread(str(media(mask_path)),cv2.IMREAD_GRAYSCALE),(size,size),interpolation=cv2.INTER_LINEAR).astype(np.float32)/255
        original=source[y:y+size,x:x+size].copy()
        source[y:y+size,x:x+size]=np.rint(original*(1-mask[:,:,None])+patch*mask[:,:,None]).astype(np.uint8)
    master=FOLDER/'selected-master.png'
    cv2.imwrite(str(master),source)
    boxes=[(160,0,688,305),(640,0,1168,305),(160,0,1344,684)]
    image=Image.fromarray(cv2.cvtColor(source,cv2.COLOR_BGR2RGB))
    for index,box in enumerate(boxes,1):
        image.crop(box).resize((832,480),Image.Resampling.LANCZOS).save(FOLDER/f'reference-{index}.png')
    run.save('ReadyForTwoSecondPilot',selectedMasterPath=str(master.relative_to(DATA)),selectedMasterSha256=sha(master),
        referenceHashes={str(i):sha(FOLDER/f'reference-{i}.png') for i in range(1,4)})
    print('Corrected master and three scene crops ready; original scene and upper identity features retained',flush=True)


def canvas(run,index,attempt):
    path=run.state[f'shot{index}Attempt{attempt}Path']
    shot=run.state['shots'][index-1]
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage=f'Face-Acting-Shot-{index}-Attempt-{attempt}-24FPS-Canvas',parameters=dict(files=[path],singlePass=True,
        targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=shot['durationSeconds'],originalAudioVolume=0,
        outputName=f'face_acting_shot_{index}_canvas.mp4'))
    detail=once(run,f'canvas{index}Attempt{attempt}TaskId',body);path=result(detail,'.mp4')
    run.save(**{f'canvas{index}Attempt{attempt}Path':path})
    return path


def pilot(run,attempt):
    run.access();path=canvas(run,1,attempt)
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-Two-Second-Pilot-Cut',parameters=dict(files=[path],singlePass=True,
        targetWidth=1280,targetHeight=720,targetFps=24,targetDurationSeconds=2,trimStartSeconds=5/24,
        originalAudioVolume=0,outputName='face_acting_pilot_picture_2s.mp4'))
    detail=once(run,f'pilotCutAttempt{attempt}TaskId',body);picture=result(detail,'.mp4')
    baseline=read(DATA/'SkinPilot20261024/run.json')['outputs']['original']
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-Two-Second-Original-Audio',parameters=dict(files=[picture],videoSha256=sha(media(picture)),
        audioStreamCopyFrom=baseline,audioStreamCopySha256=sha(media(baseline)),outputName='face_acting_pilot_same_voice_2s.mp4'))
    detail=once(run,f'pilotAudioAttempt{attempt}TaskId',body);path=result(detail,'.mp4')
    run.save('AwaitingPilotInspection',pilotPath=path,pilotSha256=sha(media(path)),pilotAttempt=attempt)
    print(path,flush=True)


def restore(run,index,attempt,strength):
    run.access()
    review=read(FOLDER/f'shot-{index}-review.json')
    if review['decision']!='SelectedForFinishing':raise RuntimeError('Inspect actual shot before detail restoration')
    selected=review['attempt']
    source=run.state[f'shot{index}Attempt{selected}Path']
    if source!=review['path'] or sha(media(source))!=review['sha256']:
        raise RuntimeError('Reviewed native take changed')
    path=canvas(run,index,selected)
    status=run.api('/api/video-restore/status')
    if not status['ready']:raise RuntimeError(status['message'])
    body=dict(projectId=run.state['projectId'],taskType='VideoRestore',resourceClass='GPU',maxRetries=0,
        stage=f'Face-Acting-Shot-{index}-QHD-Detail-Attempt-{attempt}',parameters=dict(input=path,sourceSha256=sha(media(path)),
        engineVersion=status['engineVersion'],strength=strength,cutFrames=[],outputProfile='qhd1440',targetWidth=2560,targetHeight=1440))
    detail=once(run,f'restore{index}Attempt{attempt}TaskId',body);path=result(detail,'.mp4')
    run.save('AwaitingQhdInspection',**{f'restore{index}Attempt{attempt}Path':path})
    print(path,flush=True)


def assemble(run):
    run.access();files=[]
    for index in range(1,4):
        review=read(FOLDER/f'qhd-{index}-review.json')
        if review['decision']!='SelectedForAssembly':raise RuntimeError('Actual per-shot QHD review required')
        path=run.state[f'restore{index}Attempt{review["attempt"]}Path']
        if sha(media(path))!=review['sha256']:raise RuntimeError('Reviewed QHD take changed')
        files.append(path)
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-QHD-Three-Shot-Captioned-Assembly',parameters=dict(files=files,targetWidth=2560,targetHeight=1440,
        targetFps=24,targetDurationSeconds=10,originalAudioVolume=0,subtitlePath='DialogueThreeShot20261023/audio/dialogue.srt',
        outputName='face_acting_three_shot_2k_picture.mp4'))
    detail=once(run,'pictureTaskId',body);picture=result(detail,'.mp4')
    original=run.state['originalPath']
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-QHD-Original-Audio-Packets',parameters=dict(files=[picture],videoSha256=sha(media(picture)),
        audioStreamCopyFrom=original,audioStreamCopySha256=sha(media(original)),allowResolutionDifference=True,
        outputName='face_acting_three_shot_same_dialogue_2k_10s.mp4'))
    detail=once(run,'finalTaskId',body);final=result(detail,'.mp4')
    run.save('AwaitingFinalVerification',finalPath=final,finalSha256=sha(media(final)))
    print(final,flush=True)


def pilot_qhd(run):
    run.access()
    final=run.state['finalPath']
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-Final-QHD-Two-Second-Cut',parameters=dict(files=[final],singlePass=True,
        targetWidth=2560,targetHeight=1440,targetFps=24,targetDurationSeconds=2,trimStartSeconds=5/24,
        originalAudioVolume=0,outputName='face_acting_pilot_2k_picture_2s.mp4'))
    detail=once(run,'pilotQhdPictureTaskId',body);picture=result(detail,'.mp4')
    source=read(DATA/'SkinPilot20261024/run.json')['outputs']['original']
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',maxRetries=0,
        stage='Face-Acting-QHD-Pilot-Original-Audio-Packets',parameters=dict(files=[picture],videoSha256=sha(media(picture)),
        audioStreamCopyFrom=source,audioStreamCopySha256=sha(media(source)),allowResolutionDifference=True,
        outputName='face_acting_pilot_same_voice_2k_2s.mp4'))
    detail=once(run,'pilotQhdAudioTaskId',body);path=result(detail,'.mp4')
    run.save(pilotQhdPath=path,pilotQhdSha256=sha(media(path)))
    print(path,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['references','pilot','restore','assemble','pilot-qhd'])
    parser.add_argument('--shot',type=int,default=1);parser.add_argument('--attempt',type=int,default=1);parser.add_argument('--strength',type=float,default=.3)
    args=parser.parse_args();run=Run(API,FOLDER/'run.json');preserve(run)
    if run.state.get('stage')=='ReadyForUserPreview':print('Ready; no new task');return
    if args.stage=='references':selected_references(run)
    elif args.stage=='pilot':pilot(run,args.attempt)
    elif args.stage=='restore':restore(run,args.shot,args.attempt,args.strength)
    elif args.stage=='assemble':assemble(run)
    else:pilot_qhd(run)


if __name__=='__main__':main()

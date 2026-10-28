"""Queue-only SDXL reference, H3 20/30 comparison and selected 10s delivery."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
FOLDER=DATA/'RealisticI2V20261022'
sys.path.insert(0,str(ROOT/'tools/minimax'))
from download_assets import download_lock
from run_local_acceptance import Acceptance,TaskFailure
from run_quality import artifact
FFMPEG=r'C:\install\FFmpeg\bin\ffmpeg.exe'
FFPROBE=r'C:\install\FFmpeg\bin\ffprobe.exe'

REFERENCE_PROMPT=(
 'Unretouched live action film photograph, natural documentary photography. One fictional adult East Asian woman, age 22, '
 'black hair in a ponytail, plain navy blue hoodie over a white T-shirt, black trousers, a simple cream canvas backpack. '
 'She is standing beside a low wooden park bench in a quiet university courtyard. '
 'One single closed red hardcover notebook lies flat on the bench seat in front of her. '
 'She looks down at the notebook and leans forward slightly, with both empty hands visible near the notebook. '
 'Medium shot from head to knees, three-quarter side view, eye level, her face, both hands and the entire notebook clearly visible, '
 'balanced composition with the woman and bench filling the frame. Soft warm afternoon daylight, natural skin texture, '
 'realistic fabric, red brick library and green trees gently out of focus in the background, restrained natural colors, 50mm lens.')
NEGATIVE=(
 'cartoon, illustration, anime, CGI, 3d render, doll, waxy skin, airbrushed skin, beauty filter, overprocessed, oversaturated, '
 'oversharpening, fisheye, distorted anatomy, malformed hands, fused fingers, extra fingers, extra limbs, '
 'duplicate notebook, two notebooks, multiple people, face out of frame, cropped head, cropped hands, watermark, text, logo')
REFERENCE_WIDE_PROMPT=(
 'Wide live-action campus photograph, full-body composition. A low wooden park bench with its horizontal seat fully visible. '
 'One closed bright red hardcover notebook lies flat on the right end of the bench seat. '
 'One adult East Asian woman stands beside the right end of the bench, looking down at the red notebook. '
 'Her head, both empty hands, knees and the entire notebook are inside the frame. '
 'She wears a plain unbranded navy blue hoodie, black trousers and a simple cream canvas backpack, black hair in a ponytail. '
 'Her hands rest naturally near her hips before reaching for the notebook. '
 'Camera three meters away, eye-level 35mm lens, balanced wide framing. Soft afternoon sunlight, natural skin and cloth, '
 'red brick university building and green trees in the background, realistic unretouched photography.')
REFERENCE_STANDING_PROMPT=(
 '(full body photograph:1.2), (one woman standing upright:1.4), (both hands empty:1.25). '
 'A single closed red hardcover book rests flat on the seat of a low brown wooden park bench. '
 'The woman stands on the paved ground beside the bench, feet on the ground, arms hanging relaxed at her sides, looking down toward the book. '
 'The bench is empty except for the one closed red book. '
 'She is an adult East Asian woman with a black ponytail, plain navy hooded sweatshirt, black trousers and cream backpack. '
 'Wide eye-level photo from three meters away, her entire body, both hands and the bench seat clearly in frame. '
 'Soft afternoon daylight, natural skin texture and fabric, green trees and red brick building in the background, realistic documentary film still.')
VIDEO_PROMPT=(
 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
 'integrated_multimodal_description: [Shot 1] A realistic live-action medium shot in the quiet university courtyard in Picture 1. '
 'Preserve the adult woman identity, hairstyle, navy hoodie, cream backpack, wooden bench, single closed red notebook and afternoon light exactly as shown. '
 'A locked-off eye-level camera keeps the same framing for one uninterrupted shot. '
 'She performs one slow, complete action: she looks at the single red notebook on the bench, gently closes one hand around its edge, '
 'lifts it completely clear of the bench, and holds it steadily near her waist. The book stays closed and rigid, with the same size and red cover. '
 'Her fingers stay in contact with the book as she lifts it. Her other hand rests naturally. '
 'At the end she remains still holding the same notebook. Keep her face, hand and notebook visible. '
 'Restrained natural facial expression, subtle breathing, consistent sunlight and fabric texture. No walking, no waving, no camera motion, no scene cuts. '
 'No on-screen text. All narration is off screen; she does not speak.\n\n'
 'overall_soundscape: Soft outdoor wind and faint distant birds, natural low volume, no speech.\n\nnon_diegetic_music: None.')
SEATED_VIDEO_PROMPT=(
 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
 'integrated_multimodal_description: [Shot 1] A realistic live-action campus shot from Picture 1. '
 'The same adult East Asian woman remains seated on the red wooden bench, wearing the same dark teal hoodie and black trousers. '
 'Preserve her face, black ponytail, clothing, bench, background and soft afternoon sunlight. '
 'The single closed red notebook lies beside her on the bench, on the right side of the image. '
 'She looks down at it, reaches with her left hand to the red notebook, grasps its edge, '
 'and slowly lifts the entire notebook clear of the seat onto her lap. '
 'Her fingers remain in contact with the same rigid closed book throughout. '
 'She stops with the one red notebook resting in her hand on her lap. '
 'Keep her face, hand and book visible, consistent size and cover, natural gentle movement. '
 'One continuous locked-off camera shot, no standing, no walking, no waving, no camera movement, no cuts. '
 'All narration is off screen; she does not speak. No text.\n\n'
 'overall_soundscape: Quiet outdoor wind and distant birds, no speech.\n\nnon_diegetic_music: None.')


def sha(path):
    file=Path(path).resolve(strict=True)
    if not file.is_relative_to(DATA.resolve()) or not file.is_file():raise RuntimeError('Media must stay inside Data')
    with file.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'))


class RealisticRun(Acceptance):
    def poll(self,task_id,limit=30600):
        deadline=time.monotonic()+limit
        while time.monotonic()<deadline:
            detail=self.api(f'/api/tasks/{task_id}')
            status=detail['task']['status']
            sample=dict(epoch=time.time(),taskId=task_id,status=status,progress=detail['task'].get('progress'))
            try:
                gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],encoding='utf-8',timeout=10)
                used,free,util=[int(v.strip()) for v in gpu.strip().split(',')]
                sample.update(usedVramMiB=used,freeVramMiB=free,utilizationPercent=util)
                import psutil
                sample['systemAvailableMiB']=round(psutil.virtual_memory().available/1024**2)
            except (OSError,subprocess.SubprocessError):sample['resourceSampleUnavailable']=True
            with (FOLDER/'resources.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(sample)+'\n')
            if status=='Succeeded':return detail
            if status in ['Failed','Cancelled']:
                raise TaskFailure(task_id,status,f"Task {task_id} {status}: {str(detail['task'].get('errorMessage') or '')[:2600]}")
            time.sleep(5)
        raise RuntimeError(f'Task {task_id} unresolved; query it before retrying')


def once(run,field,stage,endpoint,body):
    if not run.state.get(field):
        if run.state.get(field+'SubmissionStarted'):raise RuntimeError('Submission response unresolved: '+field)
        if endpoint=='/api/tasks':
            check=run.api('/api/tasks/preflight',body)
            (FOLDER/(field+'-preflight.json')).write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8')
            if not check['passed']:raise RuntimeError(str(check['issues']))
        run.save(stage,**{field+'SubmissionStarted':True,field+'Input':body})
        response=run.api(endpoint,body,key=field,timeout=600)
        values={field:response.get('id') or response.get('taskId')}
        if endpoint=='/api/minimax/local/video':values['newH3TasksSubmitted']=True
        run.save(**values)
        if not run.state[field]:raise RuntimeError('No task ID returned')
        print(f'{field}={run.state[field]}',flush=True)
    elif run.state.get(field+'Input')!=body:
        raise RuntimeError('Frozen submitted inputs changed: '+field)
    detail=run.poll(run.state[field])
    (FOLDER/(field+'-result.json')).write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
    return detail


def prepare(run):
    run.access()
    old=json.loads((DATA/'Qwen3Video20261022/run.json').read_text(encoding='utf-8'))
    prior=json.loads((DATA/'SeedVR2Enhancement20261022/run.json').read_text(encoding='utf-8'))
    sources=[dict(path=old[k+'Path'],sha256=old[k+'Sha256']) for k in ['sourceAudio','shot1Video','shot2Video','finalVideo']]
    sources.append(dict(path=prior['finalVideoPath'],sha256=prior['finalVideoSha256']))
    for source in sources:
        if sha(DATA/source['path'])!=source['sha256']:raise RuntimeError('Previous source changed')
    if run.state.get('sources') and run.state['sources']!=sources:raise RuntimeError('Frozen source list changed')
    if not run.state.get('projectId'):
        name='纯本地写实首帧20与30步_'+run.state['runId'][:8]
        matches=[p for p in run.api('/api/projects') if p['name']==name]
        if matches:project=matches[0]['id']
        elif run.state.get('projectSubmissionStarted'):raise RuntimeError('Project response unresolved')
        else:
            run.save('CreatingProject',projectSubmissionStarted=True)
            project=run.api('/api/projects',dict(name=name,description='Pure local SDXL reference and H3 20/30 native1080 I2V comparison. Selected 10s Qwen narration preview.',defaultWidth=1920,defaultHeight=1080,defaultFps=24))['id']
        run.save(projectId=project)
    run.save(sources=sources,sourceAudioPath=sources[0]['path'],sourceAudioSha256=sources[0]['sha256'],
        previousBPath=prior['exportTaskIdPath'],newH3TasksSubmitted=any(run.state.get(k) for k in ['video20TaskId','video30TaskId','continuationTaskId']),
        newFinalVideoCreated=bool(run.state.get('finalVideoPath')))


def reference(run,number):
    if number==5:return book_reference(run)
    if number==4:
        authorization=json.loads((FOLDER/'pose-authorization.json').read_text(encoding='utf-8'))
        if authorization.get('decision')!='ApprovedOnePoseReference' or authorization.get('maxNewCandidates')!=1:
            raise RuntimeError('Prompt-only repair budget exhausted; explicit one-candidate pose authorization is required')
    workflows={w['name']:w['id'] for w in run.api('/api/workflows')}
    key='reference'+str(number)+'TaskId'
    body=dict(projectId=run.state['projectId'],taskType='Image',resourceClass='GPU',workflowId=workflows['realvisxl_openpose_reference_api' if number==4 else 'realvisxl_reference_api'],
        stage='RealisticReference',maxRetries=0,parameters=dict(workflowVersion='realvisxl-reference-1536-v1',
            positive={1:REFERENCE_PROMPT,2:REFERENCE_WIDE_PROMPT,3:REFERENCE_STANDING_PROMPT,4:REFERENCE_STANDING_PROMPT}[number],
            negative=NEGATIVE if number==1 else NEGATIVE+', close-up, headshot, cropped body, Nike, printed clothing'+(', sitting, seated, reading, writing, pen, open book, holding a book' if number==3 else ''),seed=2026102202+number,width=1536,height=864,steps=35,cfg=5.5,
            sampler_name='dpmpp_sde',scheduler='karras',denoise=1))
    if number==4:
        pose='ReferenceGuides/RealisticI2V20261022/standing-pose.png'
        body['parameters'].update(workflowVersion='realvisxl-openpose-reference-1536-v1',inputSlots=dict(pose=pose),
            positive=('(One closed red hardcover notebook lying flat on an empty wooden park bench:1.3). '
                'One adult East Asian woman standing beside the bench, both hands empty, her right hand near the red notebook. '
                'Plain navy hoodie, black trousers, cream canvas backpack, black ponytail. '
                'Wide full-body documentary photograph, face and both hands visible, feet on paved ground. '
                'She looks down at the notebook. Natural skin and fabric, soft afternoon sunlight, '
                'quiet university courtyard, green trees and red brick library, realistic unretouched photo.'),
            negative=NEGATIVE+', sitting, seated, reading, writing, pen, open book, holding a book, close-up, cropped feet, crowded scene')
    detail=once(run,key,'GeneratingReference'+str(number),'/api/tasks',body)
    path=artifact(detail,('.png',));image=Image.open(DATA/path)
    if image.size!=(1536,864):raise RuntimeError('Reference output dimensions differ')
    run.save(**{key+'Path':path,key+'Sha256':sha(DATA/path)})
    print(json.dumps(dict(reference=number,taskId=run.state[key],imagePath=path)),flush=True)


def book_reference(run):
    authorization=json.loads((FOLDER/'resume-authorization.json').read_text(encoding='utf-8'))
    if authorization.get('decision')!='ContinueToDelivery':raise RuntimeError('Resume authorization missing')
    layout=json.loads((FOLDER/'book-layout.json').read_text(encoding='utf-8'))
    for prefix in ['source','layout','mask']:
        if sha(DATA/layout[prefix+'Path'])!=layout[prefix+'Sha256']:raise RuntimeError('Book layout source changed')
    workflow=next(w['id'] for w in run.api('/api/workflows') if w['name']=='realvisxl_book_reference_api')
    body=dict(projectId=run.state['projectId'],taskType='Image',resourceClass='GPU',workflowId=workflow,
        stage='RealisticReferenceBookHarmonization',maxRetries=0,parameters=dict(
            workflowVersion='realvisxl-book-reference-1536-v1',
            inputSlots=dict(firstFrame=layout['layoutPath'],editMask=layout['maskPath']),
            positive='One closed red hardcover notebook resting flat on a wooden bench seat, white paper edges, subtle worn cover texture, natural sunlight and contact shadow, realistic photograph',
            negative='open book, bag, multiple books, letters, text, logo, deformed book, cartoon, floating object',
            seed=2026102207,width=1536,height=864,steps=24,cfg=5.0,denoise=.28))
    detail=once(run,'reference5TaskId','HarmonizingBookReference','/api/tasks',body)
    path=artifact(detail,('.png',));im=Image.open(DATA/path)
    if im.size!=(1536,864):raise RuntimeError('Harmonized reference dimensions differ')
    graph=json.loads(im.info['prompt'])
    if graph['4'].get('is_changed')!=[layout['layoutSha256']] or graph['5'].get('is_changed')!=[layout['maskSha256']]:
        raise RuntimeError('Actual layout or mask binding differs')
    import numpy as np
    protected=np.asarray(Image.open(DATA/layout['maskPath']).convert('L'))==0
    original=np.asarray(Image.open(DATA/layout['sourcePath']).convert('RGB'))
    result=np.asarray(im.convert('RGB'))
    if not np.array_equal(original[protected],result[protected]):raise RuntimeError('Unmasked subject/background pixels changed')
    (FOLDER/'reference5-execution-graph.json').write_text(json.dumps(graph,indent=2),encoding='utf-8')
    run.save(reference5TaskIdPath=path,reference5TaskIdSha256=sha(DATA/path),reference5Review='局部编辑已完成，检查红本与人物后选片',
        unmaskedPixelPreservation='Passed',comparisonPrompt=SEATED_VIDEO_PROMPT,shotRevision='SeatedBookPickup')
    print(json.dumps(dict(reference=5,taskId=run.state['reference5TaskId'],imagePath=path,unmaskedPixels='Passed')),flush=True)


def selected_reference(run):
    review=json.loads((FOLDER/'reference-review.json').read_text(encoding='utf-8'))
    if review.get('decision')!='SelectedForI2V':raise RuntimeError('Select a reviewed actual SDXL reference first')
    number=review['selectedCandidate'];key='reference'+str(number)+'TaskId'
    path=run.state[key+'Path'];digest=run.state[key+'Sha256']
    if review['sha256']!=digest or review['path']!=path or sha(DATA/path)!=digest:raise RuntimeError('Selected reference binding changed')
    run.save(referencePath=path,referenceSha256=digest,referenceTaskId=run.state[key])
    return path,digest


def extract(folder,path,indices):
    folder.mkdir(exist_ok=True)
    contact=Image.new('RGB',(960,540),(15,20,30))
    for i,index in enumerate(indices):
        file=folder/f'frame-{index:03}.png'
        if not file.exists():subprocess.run([FFMPEG,'-v','error','-i',str(DATA/path),'-vf',f'select=eq(n\\,{index})','-frames:v','1','-n',str(file)],check=True)
        image=Image.open(file).convert('RGB');image.thumbnail((480,270));contact.paste(image,((i%2)*480,(i//2)*270))
        ImageDraw.Draw(contact).text(((i%2)*480+7,(i//2)*270+7),f'frame {index}',fill='white')
    contact.save(folder/'contact.png')


def video(run,steps,continuation=False):
    if continuation:
        review=json.loads((FOLDER/'comparison-review.json').read_text(encoding='utf-8'))
        if review.get('decision')!='SelectedFor10s':raise RuntimeError('Review both native samples before continuation')
        steps=review['selectedSteps'];field='continuationTaskId'
        source_key='video'+str(steps)+'TaskId'
        if review['sourceSha256']!=run.state[source_key+'Sha256']:raise RuntimeError('Reviewed video changed')
        frame=FOLDER/f'video-{steps}/frame-123.png'
        path=frame.relative_to(DATA).as_posix();digest=sha(frame)
        prompt=('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
            'integrated_multimodal_description: [Shot 1] Continue the live-action medium shot from the supplied actual last frame. '
            'Preserve the exact adult woman identity, ponytail, dark teal hoodie, black trousers, red notebook, bench and campus light. She stays seated. '
            'She keeps the single closed red notebook securely supported exactly as shown in the supplied frame, '
            'with both hands maintaining their current contact positions. She gently raises her gaze toward the path and pauses attentively. '
            'One small natural head movement and subtle breathing only. The hands and notebook stay still, with consistent fingers, '
            'book shape, clothing and background. The book never returns to the bench. Locked-off camera, no cuts, no walking or waving. '
            'The narration is off screen; no lip synchronization is requested. No on-screen text.\n\n'
            'overall_soundscape: Soft wind and faint distant birds, no speech.\n\nnon_diegetic_music: None.')
        seed=2026102231
    else:
        path,digest=selected_reference(run);field='video'+str(steps)+'TaskId';prompt=run.state.get('comparisonPrompt',VIDEO_PROMPT);seed=2026102220
    if sha(DATA/path)!=digest:raise RuntimeError('Video reference changed')
    body=dict(projectId=run.state['projectId'],profile='native1080',textToVideo=False,inputImagePath=path,prompt=prompt,seed=seed,steps=steps)
    run.save(**{field+'ReferenceSha256':digest})
    detail=once(run,field,'GeneratingContinuation' if continuation else 'Generating'+str(steps)+'Steps','/api/minimax/local/video',body)
    output=artifact(detail,('.mp4',));metadata=probe(DATA/output);v=next(s for s in metadata['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1920,1080,'24/1',124):raise RuntimeError('Native source dimensions, rate or frame count differ')
    graph=json.loads(metadata['format']['tags']['prompt'])
    if graph['10']['inputs']['steps']!=steps or graph['7']['inputs']['noise_seed']!=seed or graph['6']['inputs']['prompt']!=prompt:raise RuntimeError('Actual sampler or prompt differs')
    if graph['5'].get('is_changed')!=[digest]:raise RuntimeError('Actual first-frame digest differs')
    if (graph['6']['inputs']['width'],graph['6']['inputs']['height'],graph['16']['inputs']['height'],graph['16']['inputs']['y'])!=(1920,1088,1080,4):raise RuntimeError('Native canvas or crop differs')
    folder=FOLDER/('continuation' if continuation else 'video-'+str(steps));folder.mkdir(exist_ok=True)
    (folder/'probe.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (folder/'execution-graph.json').write_text(json.dumps(graph,indent=2),encoding='utf-8')
    extract(folder,output,[0,40,80,123])
    run.save(**{field+'Path':output,field+'Sha256':sha(DATA/output)})
    print(json.dumps(dict(taskId=run.state[field],steps=steps,videoPath=output,contact=str(folder/'contact.png'))),flush=True)


def assemble(run):
    review=json.loads((FOLDER/'comparison-review.json').read_text(encoding='utf-8'))
    if review.get('decision')!='SelectedFor10s':raise RuntimeError('Comparison review missing')
    field='video'+str(review['selectedSteps'])+'TaskId'
    paths=[run.state[field+'Path'],run.state['continuationTaskIdPath']]
    for key in [field,'continuationTaskId']:
        if sha(DATA/run.state[key+'Path'])!=run.state[key+'Sha256']:raise RuntimeError('Selected source changed')
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='RealisticI2V10sPreview',maxRetries=0,
        parameters=dict(singlePass=True,files=paths,targetWidth=1920,targetHeight=1080,targetFps=24,targetDurationSeconds=10,
            originalAudioVolume=0,audioTracks=[dict(path=run.state['sourceAudioPath'],volume=1,startSeconds=.12,tempo=1.32)],
            outputName='realistic_i2v_qwen_10s.mp4'))
    detail=once(run,'finalTaskId','Assembling10s','/api/tasks',body)
    output=artifact(detail,('.mp4',));metadata=probe(DATA/output);v=next(s for s in metadata['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1920,1080,'24/1',240):raise RuntimeError('Final delivery specification differs')
    (FOLDER/'final-probe.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    subprocess.run([FFMPEG,'-v','error','-i',str(DATA/output),'-f','null','-'],check=True)
    run.save('AwaitingPlaybackInspection',finalVideoPath=output,finalVideoSha256=sha(DATA/output),selectedSteps=review['selectedSteps'],technicalStatus='Passed',newFinalVideoCreated=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','reference','video','continue','assemble','check'],required=True)
    parser.add_argument('--candidate',type=int,choices=[1,2,3,4,5],default=1)
    parser.add_argument('--steps',type=int,choices=[20,30],default=20)
    args=parser.parse_args()
    with download_lock(FOLDER,'.realistic-run.lock','Another realistic I2V runner is active'):
        run=RealisticRun('http://127.0.0.1:18080',FOLDER/'run.json')
        try:
            prepare(run)
            if args.stage=='check' or run.state['stage']=='ReadyForUserPreview':
                fields=['reference1TaskId','reference2TaskId','reference3TaskId','reference4TaskId','reference5TaskId','video20TaskId','video30TaskId','continuationTaskId','finalTaskId']
                for field in fields:
                    if not run.state.get(field):continue
                    if run.api(f'/api/tasks/{run.state[field]}')['task']['status']!='Succeeded':raise RuntimeError('Recorded task not successful')
                    path=run.state.get(field+'Path') if field!='finalTaskId' else run.state.get('finalVideoPath')
                    digest=run.state.get(field+'Sha256') if field!='finalTaskId' else run.state.get('finalVideoSha256')
                    if path and sha(DATA/path)!=digest:raise RuntimeError('Recorded output changed')
                print(json.dumps(dict(stage=run.state['stage'],newTaskSubmitted=False)),flush=True);return
            if args.stage=='reference':reference(run,args.candidate)
            elif args.stage=='video':video(run,args.steps)
            elif args.stage=='continue':video(run,args.steps,continuation=True)
            elif args.stage=='assemble':assemble(run)
            else:run.save('Prepared')
        except Exception as error:
            status='Failed' if isinstance(error,TaskFailure) and error.status=='Failed' else 'Blocked'
            run.save(status,technicalStatus=status,error=str(error)[:3500]);raise


if __name__=='__main__':main()

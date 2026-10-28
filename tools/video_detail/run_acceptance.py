"""Resumable, queue-only detail restoration acceptance for the existing 10s campus film."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/minimax'))
from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
sys.path.insert(0, str(ROOT / 'tools/qwen3_tts'))
from run_video import sha, probe, FFMPEG

DATA = ROOT.parent / 'Data'
FOLDER = DATA / 'SeedVR2Enhancement20261022'


class DetailAcceptance(Acceptance):
    def poll(self, task_id, limit=6000):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            detail = self.api(f'/api/tasks/{task_id}')
            status = detail['task']['status']
            raw = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], encoding='utf-8')
            used, free, utilization = [int(v.strip()) for v in raw.strip().split(',')]
            sample = dict(epoch=time.time(), taskId=task_id, status=status, usedVramMiB=used, freeVramMiB=free, utilizationPercent=utilization)
            with (FOLDER / 'resources.jsonl').open('a', encoding='utf-8') as out: out.write(json.dumps(sample) + '\n')
            if status == 'Succeeded': return detail
            if status in ['Failed', 'Cancelled']:
                raise TaskFailure(task_id, status, f"Task {task_id} {status}: {str(detail['task'].get('errorMessage') or '')[:2500]}")
            time.sleep(5)
        raise RuntimeError(f'Task {task_id} remains unresolved; do not resubmit')


def once(run, field, stage, body):
    if not run.state.get(field):
        if run.state.get(field + 'SubmissionStarted'):
            raise RuntimeError('Submission outcome unresolved: ' + field)
        check = run.api('/api/tasks/preflight', body)
        (FOLDER / (field + '-preflight.json')).write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding='utf-8')
        if not check['passed']: raise RuntimeError('Preflight rejected: ' + str(check['issues']))
        run.save(stage, **{field + 'SubmissionStarted':True, field + 'Input':body})
        result = run.api('/api/tasks', body, key=field, timeout=600)
        run.save(**{field:result.get('id') or result.get('taskId')})
        if not run.state[field]: raise RuntimeError('No task ID returned')
        print(f'{field}={run.state[field]}', flush=True)
    detail = run.poll(run.state[field])
    (FOLDER / (field + '-result.json')).write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding='utf-8')
    video = run.result(detail, ('.mp4',))
    if video is None: raise RuntimeError('Task produced no available video')
    path = video['assetPath']
    metadata = probe(DATA / path)
    (FOLDER / (field + '-probe.json')).write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    v = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    wanted = 49 if 'sample' in field.lower() else 240
    if (v['width'], v['height'], v['avg_frame_rate'], int(v['nb_frames'])) != (1920,1080,'24/1',wanted):
        raise RuntimeError('Actual output dimensions/rate/frame count differ')
    subprocess.run([FFMPEG,'-v','error','-i',str(DATA/path),'-f','null','-'], check=True)
    run.save(**{field+'Path':path,field+'Sha256':sha(DATA/path)})
    return path


def prepare(run):
    run.access()
    prior = json.loads((DATA/'Qwen3Video20261022/run.json').read_text(encoding='utf-8'))
    sources = []
    for prefix in ['shot1Video', 'shot2Video', 'sourceAudio', 'finalVideo']:
        path, digest = prior[prefix+'Path'], prior[prefix+'Sha256']
        if sha(DATA/path) != digest: raise RuntimeError('Original changed: '+prefix)
        sources.append(dict(path=path,sha256=digest))
    if run.state.get('sources') and run.state['sources'] != sources: raise RuntimeError('Frozen sources differ')
    if not run.state.get('projectId'):
        name = '视频细节优化对照_' + run.state['runId'][:8]
        found = [p for p in run.api('/api/projects') if p['name'] == name]
        if found: project = found[0]['id']
        elif run.state.get('projectSubmissionStarted'): raise RuntimeError('Project submission unresolved')
        else:
            run.save('CreatingProject', projectSubmissionStarted=True)
            project = run.api('/api/projects', dict(name=name,description='Existing 10s Qwen3 campus film: one-pass export and SeedVR2 restoration. Private A/B preview.', defaultWidth=1920,defaultHeight=1080,defaultFps=24))['id']
        run.save(projectId=project)
    run.save(error=None, sources=sources, originalVideoPath=sources[3]['path'], sampleStartSeconds=6, sampleFrames=49,
        sourceAudioPath=sources[2]['path'], sourceAudioSha256=sources[2]['sha256'], contentStatus='NeedReview', publicationStatus='Blocked')
    return sources


def export(run, sources, sample=False):
    body = dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='VideoDetailPreview',maxRetries=0,
        parameters=dict(singlePass=True,files=[s['path'] for s in sources[:2]],targetWidth=1920,targetHeight=1080,targetFps=24,
            targetDurationSeconds=49/24 if sample else 10,trimStartSeconds=6 if sample else 0,originalAudioVolume=0,
            audioTracks=[dict(path=sources[2]['path'],volume=1,startSeconds=.12,tempo=1.32)],
            outputName='detail_sample_49frames.mp4' if sample else 'detail_one_pass_10s.mp4'))
    return once(run,'sampleExportTaskId' if sample else 'exportTaskId','ExportingSample' if sample else 'Exporting10s',body)


def restore(run, source, full=False):
    status = run.api('/api/video-restore/status')
    if not status['ready']: raise RuntimeError(status['message'])
    body = dict(projectId=run.state['projectId'],taskType='VideoRestore',resourceClass='GPU',stage='VideoDetailRestoration',maxRetries=0,
        parameters=dict(input=source,sourceSha256=sha(DATA/source),engineVersion=status['engineVersion'],strength=.65,cutFrames=[124] if full else []))
    return once(run,'fullRestoreTaskId' if full else 'sampleRestoreTaskId','Restoring10s' if full else 'RestoringSample',body)


def remux(run, sample):
    videoField='sampleRestoreTaskId' if sample else 'fullRestoreTaskId'
    audioField='sampleExportTaskId' if sample else 'exportTaskId'
    body=dict(projectId=run.state['projectId'],taskType='Concat',resourceClass='CPU',stage='VideoDetailAudioPreservation',maxRetries=0,
        parameters=dict(files=[run.state[videoField+'Path']],videoSha256=run.state[videoField+'Sha256'],
            audioStreamCopyFrom=run.state[audioField+'Path'],audioStreamCopySha256=run.state[audioField+'Sha256'],targetFps=24,
            outputName='seedvr2_sample_complete_audio.mp4' if sample else 'seedvr2_10s_complete_audio.mp4'))
    return once(run,'sampleFinalTaskId' if sample else 'fullFinalTaskId','PreservingSampleAudio' if sample else 'PreservingFullAudio',body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['export','sample','full','remux','check'],required=True)
    args = parser.parse_args()
    with download_lock(FOLDER,'.detail-acceptance.lock','Another detail runner is active'):
        run = DetailAcceptance('http://127.0.0.1:18080',FOLDER/'run.json')
        try:
            sources = prepare(run)
            if args.stage == 'check' or run.state.get('stage') == 'ReadyForUserPreview':
                for field in ['exportTaskId','sampleExportTaskId','sampleRestoreTaskId','fullRestoreTaskId','sampleFinalTaskId','fullFinalTaskId']:
                    if run.state.get(field):
                        if run.api(f'/api/tasks/{run.state[field]}')['task']['status'] != 'Succeeded' or sha(DATA/run.state[field+'Path']) != run.state[field+'Sha256']:
                            raise RuntimeError('Recorded output no longer valid')
                print(json.dumps(dict(stage=run.state['stage'],newTaskSubmitted=False)),flush=True)
                return
            if args.stage=='remux':
                remux(run,True);remux(run,False)
                run.save('AwaitingPlaybackInspection',technicalStatus='Passed')
                return
            path = export(run,sources)
            if args.stage == 'sample':
                sample = export(run,sources,sample=True)
                restore(run,sample)
                run.save('AwaitingSampleInspection')
            elif args.stage == 'full':
                review = json.loads((FOLDER/'sample-visual-review.json').read_text(encoding='utf-8'))
                if review.get('decision') != 'ProceedConservativeFullPreview' or review.get('sourceSha256') != run.state['sampleRestoreTaskIdSha256']:
                    raise RuntimeError('Inspect the actual restored sample before full preview')
                restore(run,path,full=True)
                run.save('AwaitingPlaybackInspection',technicalStatus='Passed')
            else: run.save('ExportReady')
        except Exception as error:
            status = 'Failed' if isinstance(error,TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status,technicalStatus=status,error=str(error)[:3500])
            raise


if __name__ == '__main__': main()

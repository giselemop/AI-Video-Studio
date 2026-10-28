"""Assemble only inspected fresh story shots through the real CPU queue."""
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

from download_assets import download_lock
from run_campus_story import DATA, FOLDER, REPORT, once, sha, completed_story_check
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact

FFPROBE = r'C:\install\FFmpeg\bin\ffprobe.exe'


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE, '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(path)], encoding='utf-8'))


def timestamp(seconds):
    milliseconds = round(seconds*1000)
    return f'{milliseconds//3600000:02}:{milliseconds//60000%60:02}:{milliseconds//1000%60:02},{milliseconds%1000:03}'


def assemble(run):
    run.access()
    files, tracks, subtitles, sources = [], [], [], []
    for n in range(1, 6):
        review = json.loads((FOLDER/f'shot-{n:02}/review.json').read_text(encoding='utf-8'))
        if review.get('status') != 'SelectedForContinuation':
            raise RuntimeError(f'Shot {n} requires actual visual inspection before assembly')
        path = run.state[f'shot{n}VideoPath']
        if sha(DATA/path) != run.state[f'shot{n}VideoSha256']:
            raise RuntimeError('A selected video changed')
        source_probe = probe(DATA/path)
        video = next(s for s in source_probe['streams'] if s['codec_type'] == 'video')
        if (video['width'], video['height'], video['avg_frame_rate'], int(video['nb_frames'])) != (1920, 1080, '24/1', 124):
            raise RuntimeError('A story source differs from native1080/24/124')
        files.append(path)
        sources.append({'shot': n, 'taskId': run.state[f'shot{n}TaskId'], 'path': path, 'sha256': sha(DATA/path)})
        voice = run.state[f'narration{n}Path']
        voice_probe = probe(DATA/voice)
        duration = float(voice_probe['format']['duration'])
        if not 0.1 < duration < 4.8:
            raise RuntimeError('Narration no longer fits its shot')
        start = (n-1)*124/24 + .35
        tracks.append({'path': voice, 'volume': 1, 'startSeconds': start})
        subtitles.append(f'{n}\n{timestamp(start)} --> {timestamp(start+duration)}\n{run.state["shotPlan"][n-1]["narration"]}\n')
    captions = FOLDER/'story.srt'
    caption_bytes = ('\n'.join(subtitles)).encode('utf-8')
    if captions.exists() and captions.read_bytes() != caption_bytes:
        raise RuntimeError('Existing captions differ; preserved')
    captions.write_bytes(caption_bytes)
    params = {'files': files, 'targetWidth': 1920, 'targetHeight': 1080, 'targetFps': 24,
        'targetDurationSeconds': 620/24, 'audioTracks': tracks, 'originalAudioVolume': .12,
        'subtitlePath': captions.relative_to(DATA).as_posix(), 'outputName': 'campus_story_lost_notebook_1080p24.mp4'}
    payload = {'projectId': run.state['projectId'], 'taskType': 'Concat', 'resourceClass': 'CPU',
        'stage': 'H3-Campus-Story-Preview', 'maxRetries': 0, 'parameters': params}
    frozen = {'assemblyInput': payload, 'assemblySources': sources, 'subtitleSha256': sha(captions)}
    if run.state.get('assemblyTaskId') and any(run.state.get(k) != v for k,v in frozen.items()):
        raise RuntimeError('Submitted assembly inputs differ; query the existing task')
    if not run.state.get('assemblyTaskId'):
        check = run.api('/api/tasks/preflight', payload)
        (FOLDER/'assembly-preflight.json').write_text(json.dumps(check, indent=2), encoding='utf-8')
        if not check['passed']:
            raise RuntimeError('Real assembly preflight rejected the inputs')
    run.save(**frozen)
    result = once(run, 'assemblyTaskId', 'AssemblingStory', '/api/tasks', payload, timeout=3600)
    final_path = artifact(result, ('.mp4',))
    final_probe = probe(DATA/final_path)
    video = next(s for s in final_probe['streams'] if s['codec_type'] == 'video')
    if (video['width'], video['height'], video['avg_frame_rate'], int(video['nb_frames'])) != (1920, 1080, '24/1', 620):
        raise RuntimeError('Final actual story is not 1920x1080/24/620 frames')
    if abs(float(video['duration'])-620/24) > .02 or not any(s['codec_type']=='audio' for s in final_probe['streams']):
        raise RuntimeError('Final actual story duration/audio failed')
    subprocess.run([r'C:\install\FFmpeg\bin\ffmpeg.exe','-v','error','-i',str(DATA/final_path),'-f','null','-'],check=True)
    for source in sources:
        if sha(DATA/source['path']) != source['sha256']:
            raise RuntimeError('A generated source was modified during assembly')
    (FOLDER/'final-probe.json').write_text(json.dumps(final_probe,indent=2),encoding='utf-8')
    preview = 'http://127.0.0.1:18080/h3-campus-story-preview.html?' + urlencode({'video': final_path})
    run.save('AwaitingFinalPlaybackInspection', technicalStatus='Passed', finalVideoPath=final_path,
        finalVideoSha256=sha(DATA/final_path), finalDurationSeconds=620/24, previewUrl=preview,
        contentStatus='NeedReview', publicationStatus='Blocked', error=None)
    print(json.dumps({'videoPath':final_path,'previewUrl':preview}))


if __name__ == '__main__':
    with download_lock(FOLDER, '.h3-campus-story.lock', 'Another story runner is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            if not completed_story_check(run):
                assemble(run)
        except Exception as error:
            status = 'Failed' if isinstance(error,TaskFailure) and error.status=='Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            raise

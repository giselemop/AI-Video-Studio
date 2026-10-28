"""A fresh local H3 campus story, with immutable inputs and resumable service-queue tasks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image
from download_assets import download_lock
from run_local_acceptance import Acceptance, TaskFailure
from run_quality import artifact, video_probe

DATA = Path(r'C:\install\AI\Data')
FOLDER = DATA / 'H3CampusStory20261021'
REPORT = FOLDER / 'run.json'
FRAME_PROMPT = (
    'Live-action movie still, medium wide eye-level shot in a quiet university courtyard in warm afternoon '
    'daylight. In the foreground one young adult East Asian woman, age 22, black ponytail, plain navy blue '
    'hoodie, black trousers, white sneakers, cream canvas backpack, stands beside a wooden bench. '
    'Her face is in three-quarter view, she looks down toward a single closed red hardcover notebook '
    'lying flat on the near end of the bench. Both her hands are relaxed at her sides. '
    'In the distant background one young adult man in a beige jacket, dark jeans and black backpack '
    'walks away along the path, seen from behind. A simple red brick library facade and a few green trees '
    'are softly out of focus. Natural proportions, believable hands, cinematic photographic realism, '
    'coherent courtyard, clear separation of foreground and background, horizontal composition.'
)
NEGATIVE = ('child, teenager, crowd, multiple women, twins, duplicate people, extra limbs, deformed hands, '
            'floating objects, text, watermark, logo, collage, cartoon, illustration, oversaturated, blurry face')
SHOTS = [
    {'number': 1, 'title': '发现', 'narration': '午后，林夏在长椅上发现了一本笔记。',
     'action': 'The woman takes a small step closer to the bench, notices the red notebook and stops. She looks down at the notebook with a curious expression. The distant man keeps walking slowly away. A very slow small camera push-in, one continuous shot.'},
    {'number': 2, 'title': '拿起', 'narration': '她拿起本子，抬头寻找它的主人。',
     'action': 'The woman bends slightly toward the bench, gently picks up the single closed red notebook with her right hand, straightens up and holds it against her torso. The notebook leaves the bench and remains in her hand. She raises her gaze along the path. One continuous stabilized shot.'},
    {'number': 3, 'title': '叫住失主', 'narration': '前面的同学，似乎还没有发现。',
     'action': 'Holding the red notebook visibly in her right hand, the woman takes two brisk steps toward the man and raises her left hand in a small wave. The man in the beige jacket notices her and turns back to face her. Keep both people separate and their clothing unchanged. The camera pans gently to follow the action, one continuous shot.'},
    {'number': 4, 'title': '归还', 'narration': '林夏追上去，把笔记本递给了他。',
     'action': 'The man in the beige jacket takes a small step toward the woman. She extends the closed red notebook toward him. He accepts it with both hands, and she releases it. By the end the single notebook is held by the man and the woman has empty hands. Medium two-person shot, calm natural movement, no camera shake.'},
    {'number': 5, 'title': '告别', 'narration': '一句谢谢，让普通的午后多了些温暖。',
     'action': 'The man holds the red notebook securely against his chest and gives a grateful nod. The woman smiles and makes a small friendly wave. They turn naturally and begin to walk in opposite directions along the courtyard path. A gentle camera pull-back ends the scene, one continuous shot.'}
]
REPAIR_PROMPTS = {
    1: ('(one young adult East Asian woman:1.35), black ponytail, (plain navy blue hoodie:1.3), '
        'cream backpack, black trousers. Medium shot, the woman fills the left half of the frame, '
        'standing next to a wooden park bench, looking down. (One closed red hardcover notebook '
        'lies on the bench beside her:1.35). Her empty hands rest at her sides. '
        'Photorealistic film still, eye level, soft afternoon sunlight, quiet university courtyard, '
        'simple brick wall and green trees in the blurred background, natural proportions.'),
    2: ('Photograph, medium shot of one adult woman with a black ponytail, wearing a plain blue hoodie '
        'and cream backpack, standing beside a wooden bench. She looks at a single bright red closed '
        'notebook on the bench. The woman is large and clearly visible in the center of the frame. '
        'Hands empty, relaxed posture, natural anatomy, afternoon campus courtyard, soft background, '
        'realistic movie still, restrained daylight colors.')
}


def sha(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(DATA.resolve()) or not resolved.is_file():
        raise RuntimeError('Story media must stay inside the controlled Data directory')
    return hashlib.sha256(resolved.read_bytes()).hexdigest()


def completed_story_check(run):
    if run.state.get('stage') != 'ReadyForUserPreview':
        return False
    task_id, path = run.state.get('assemblyTaskId'), run.state.get('finalVideoPath')
    if not task_id or not path or not run.state.get('finalVideoSha256'):
        raise RuntimeError('Completed story record is incomplete; no new task submitted')
    run.access()
    if run.api(f'/api/tasks/{task_id}')['task']['status'] != 'Succeeded':
        raise RuntimeError('Existing assembly is not successful; query it before any new submission')
    if sha(DATA/path) != run.state['finalVideoSha256']:
        raise RuntimeError('Existing story video changed; preserved without regeneration')
    print(json.dumps({'stage': 'ReadyForUserPreview', 'existingAssemblyTaskId': task_id,
        'videoPath': path, 'resumeCheck': 'Passed', 'newTaskSubmitted': False}), flush=True)
    return True


def once(run, field, stage, endpoint, body, timeout=1800):
    if not run.state.get(field):
        marker = field + 'SubmissionStarted'
        if run.state.get(marker):
            raise RuntimeError('Submission outcome unresolved: ' + field + '; query existing tasks first')
        run.save(stage, **{marker: True})
        result = run.api(endpoint, body, key=field, timeout=600)
        task_id = result.get('id') or result.get('taskId')
        if not task_id:
            raise RuntimeError('Task submission has no ID; no retry')
        run.save(**{field: task_id})
        print(field + '=' + str(task_id), flush=True)
    return run.poll(run.state[field], limit=timeout)


def prepare(run):
    run.access()
    frozen = {'title': '遗落的笔记本', 'shotPlan': SHOTS, 'firstFramePrompt': FRAME_PROMPT,
              'negative': NEGATIVE, 'outputWidth': 1920, 'outputHeight': 1080, 'fps': 24,
              'framesPerShot': 124, 'steps': 20, 'shotCount': 5,
              'plannedDurationSeconds': 620 / 24, 'routeDefault': 'native1080',
              'sourceResolutionChangeRequiresUserChoice': True}
    if run.state.get('projectId') and any(run.state.get(k) != v for k, v in frozen.items()):
        raise RuntimeError('Existing story plan changed; preserved')
    run.save(**frozen, error=None)
    if not run.state.get('projectId'):
        name = 'H3校园剧情_遗落的笔记本_' + run.state['runId'][:8]
        matches = [p for p in run.api('/api/projects') if p['name'] == name]
        if len(matches) == 1:
            run.save(projectId=matches[0]['id'])
        elif run.state.get('projectSubmissionStarted'):
            raise RuntimeError('Project submission outcome unresolved; no duplicate project')
        else:
            run.save('CreatingStoryProject', projectSubmissionStarted=True)
            created = run.api('/api/projects', {'name': name,
                'description': 'Local H3 fictional campus story preview. Fresh video shots, narrative and captions; experimental content needs human review, not a publication-approved Episode.',
                'defaultWidth': 1920, 'defaultHeight': 1080, 'defaultFps': 24})
            run.save(projectId=created['id'])
    (FOLDER / 'story-plan.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')


def frames(run):
    workflows = {w['name']: w['id'] for w in run.api('/api/workflows')}
    for index in (0, 1):
        field = f'candidate{index}TaskId'
        detail = once(run, field, 'GeneratingStoryKeyframes', '/api/tasks', {
            'projectId': run.state['projectId'], 'taskType': 'Image', 'resourceClass': 'GPU',
            'workflowId': workflows['06_scene_keyframe_quality_api'], 'stage': 'H3-Campus-Story-Keyframe', 'maxRetries': 0,
            'parameters': {'width': 864, 'height': 480, 'prompt': FRAME_PROMPT, 'negative': NEGATIVE,
                           'seed': 2026102101 + index, 'steps': 28, 'cfg': 6}})
        path = artifact(detail, ('.png',))
        with Image.open(DATA / path) as image:
            assert image.size == (864, 480)
            image.load()
        run.save(**{f'candidate{index}Path': path, f'candidate{index}Sha256': sha(DATA / path)})
    run.save('AwaitingStoryFirstFrameInspection')
    print(json.dumps({k: v for k, v in run.state.items() if k.endswith('Path')}), flush=True)


def narration(run):
    paths = []
    for shot in SHOTS:
        number = shot['number']
        detail = once(run, f'narration{number}TaskId', 'GeneratingStoryNarration', '/api/audio/tts', {
            'projectId': run.state['projectId'], 'text': shot['narration'], 'voiceId': '', 'speed': 1, 'pitch': 0})
        path = artifact(detail, ('.wav',))
        paths.append(path)
        run.save(**{f'narration{number}Path': path})
    run.save('StoryNarrationReady', narrationPaths=paths)
    print(json.dumps({'narrationPaths': paths}), flush=True)


def repair_frame(run, revision):
    index = revision + 1
    if run.state.get('videoTaskIds') or any(run.state.get(f'shot{n}TaskId') for n in range(1, 6)):
        raise RuntimeError('Video input is already frozen; no new first-frame repair')
    rejections = json.loads((FOLDER / 'frame-rejections.json').read_text(encoding='utf-8'))
    required = [0, 1] if revision == 1 else [2]
    if not all(str(i) in rejections for i in required):
        raise RuntimeError('Prior candidate failure must be inspected before targeted repair')
    prompt = REPAIR_PROMPTS[revision]
    field = f'candidate{index}TaskId'
    if run.state.get(field) and run.state.get(f'candidate{index}Prompt') != prompt:
        raise RuntimeError('Existing repaired candidate inputs differ')
    run.save(**{f'candidate{index}Prompt': prompt, f'candidate{index}ChangeReason': 'Subject-first shorter prompt; one prominent adult woman and visible notebook instead of a distant two-person scene.'})
    workflow = next(w['id'] for w in run.api('/api/workflows') if w['name'] == '06_scene_keyframe_quality_api')
    detail = once(run, field, 'RepairingStoryFirstFrame', '/api/tasks', {
        'projectId': run.state['projectId'], 'taskType': 'Image', 'resourceClass': 'GPU',
        'workflowId': workflow, 'stage': 'H3-Campus-Story-Keyframe-Repair', 'maxRetries': 0,
        'parameters': {'width': 864, 'height': 480, 'prompt': prompt, 'negative': NEGATIVE,
                       'seed': 2026102110 + revision, 'steps': 28, 'cfg': 6.5}})
    path = artifact(detail, ('.png',))
    run.save('AwaitingStoryFirstFrameInspection', **{f'candidate{index}Path': path, f'candidate{index}Sha256': sha(DATA / path)})
    print(json.dumps({'candidateIndex': index, 'path': path}), flush=True)


def video(run, number, profile):
    if run.state.get('selectedProfile') and run.state['selectedProfile'] != profile:
        raise RuntimeError('Story generation profile is frozen; no implicit source-resolution change')
    run.save(selectedProfile=profile, nativeCanvas=[1920, 1088] if profile == 'native1080' else [1376, 768],
             routeSelectionReason='Existing native1080 preference retained unless the user explicitly selects quality768.')
    if number > 1:
        inspection = json.loads((FOLDER / f'shot-{number - 1:02}/review.json').read_text(encoding='utf-8'))
        if inspection.get('status') != 'SelectedForContinuation':
            raise RuntimeError('Previous story shot requires actual content inspection before continuation')
        frame = inspection['lastFramePath']
        fingerprint = inspection['lastFrameSha256']
        if sha(DATA / frame) != fingerprint:
            raise RuntimeError('Previous ending-frame reference changed')
        prefix = 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
        anchors = ('The same adult woman with black ponytail, plain navy blue hoodie, black trousers and cream '
                   'backpack stays in the same university courtyard, with the same wooden bench, red notebook '
                   'and young adult man in a beige jacket and black backpack. Preserve the opening positions '
                   'and the identity, clothes and object ownership visible in the reference. ')
    else:
        frame, fingerprint, prefix = '', None, ''
        anchors = ('Cinematic live-action medium-wide eye-level shot in a quiet university courtyard with a '
                   'simple red brick library, a paved path, one wooden bench and a few green trees in warm '
                   'afternoon light. One fictional 22-year-old East Asian woman with a black ponytail, plain '
                   'navy blue hoodie, black trousers, white sneakers and a cream canvas backpack stands beside '
                   'the bench. One closed red hardcover notebook lies flat on the near end of the bench, '
                   'clearly visible. Several metres behind her, one young adult East Asian man in a beige '
                   'jacket, dark jeans and black backpack walks away along the path, seen from behind. ')
    if number >= 3:
        anchors = anchors.replace('Preserve the opening positions and the identity, clothes and object ownership visible in the reference.',
            'Begin with the positions and notebook holder visible in the reference. Keep the same identities, clothing and courtyard throughout; perform the movements and any notebook transfer described next.')
    if number >= 4:
        anchors = ('The same adult woman with a black ponytail, navy hoodie and cream backpack and the same '
                   'adult man with a beige jacket and black backpack stay in this courtyard. Keep their '
                   'identities, clothes and daylight consistent, starting at the reference positions. ')
    action = SHOTS[number - 1]['action']
    staging_path = FOLDER / f'shot-{number:02}/staging.json'
    staging = None
    if staging_path.exists():
        staging = json.loads(staging_path.read_text(encoding='utf-8'))
        if (number <= 1 or staging.get('shot') != number or staging.get('previousShot') != number-1
                or staging.get('previousVideoSha256') != run.state[f'shot{number-1}VideoSha256']
                or not isinstance(staging.get('action'), str) or not 1 <= len(staging['action']) <= 3000
                or not staging.get('reason')):
            raise RuntimeError('Staging adjustment must identify the inspected previous shot and its reason')
        action = staging['action']
    prompt = (prefix + 'integrated_multimodal_description: [Shot 1] ' + anchors + action
              + ' Coherent natural anatomy, restrained realistic colors, stable daylight. No on-screen text, '
              'no speaking, mouths remain closed.\n\noverall_soundscape: Very quiet campus ambience, faint birds '
              'and soft footsteps. No speech or music.\n\nnon_diegetic_music: N/A')
    frozen = {f'shot{number}Prompt': prompt, f'shot{number}Seed': 2026102130 + number,
              f'shot{number}InputFrame': frame, f'shot{number}InputFrameSha256': fingerprint}
    if staging is not None:
        frozen[f'shot{number}Staging'] = staging
    if run.state.get(f'shot{number}TaskId') and any(run.state.get(k) != v for k, v in frozen.items()):
        raise RuntimeError('Existing shot inputs changed; preserved')
    run.save(**frozen)
    if not run.state.get(f'shot{number}TaskId'):
        queue = run.api('/api/minimax/local/status')['queue']
        if queue.get('activeTasks') or queue.get('paused'):
            raise RuntimeError('Service queue is active or paused; no new GPU submission')
        run.api('/api/minimax/local/verify', {}, timeout=600)
    detail = once(run, f'shot{number}TaskId', f'GeneratingStoryShot{number}', '/api/minimax/local/video', {
        'projectId': run.state['projectId'], 'profile': profile, 'textToVideo': number == 1,
        'inputImagePath': frame, 'prompt': prompt, 'seed': run.state[f'shot{number}Seed']},
        timeout=22500 if profile == 'native1080' else 6000)
    path, audio = artifact(detail, ('.mp4',)), artifact(detail, ('.wav',))
    width, height = (1920, 1080) if profile == 'native1080' else (1376, 768)
    probe = video_probe(path, width, height)
    graph = json.loads(probe['format']['tags']['prompt'])
    condition = graph['6']['inputs']
    expected_canvas = (1920, 1088) if profile == 'native1080' else (1376, 768)
    if (condition['prompt'] != prompt or (condition['width'], condition['height']) != expected_canvas
            or condition['length'] != 124 or graph['10']['inputs']['steps'] != 20
            or graph['7']['inputs']['noise_seed'] != run.state[f'shot{number}Seed'] or graph['14']['inputs']['fps'] != 24):
        raise RuntimeError('Actual shot execution differs from its frozen inputs')
    if number == 1:
        if 'first_frame' in condition or any(n['class_type'] == 'LoadImage' for n in graph.values()):
            raise RuntimeError('Text opening unexpectedly used a reference frame')
    elif graph['5'].get('is_changed') != [fingerprint] or sha(DATA / frame) != fingerprint:
        raise RuntimeError('Continuation did not use the selected previous ending frame')
    folder = FOLDER / f'shot-{number:02}'
    folder.mkdir(exist_ok=True)
    (folder/'execution-graph.json').write_text(json.dumps(graph, indent=2), encoding='utf-8')
    (folder/'probe.json').write_text(json.dumps(probe, indent=2), encoding='utf-8')
    run.save('AwaitingStoryShotInspection', **{f'shot{number}VideoPath': path, f'shot{number}AudioPath': audio,
        f'shot{number}VideoSha256': sha(DATA/path), f'shot{number}TechnicalStatus': 'Passed',
        f'shot{number}Metrics': {k: detail['task'].get(k) for k in ['id','durationMs','vramPeakMiB','startedAt','finishedAt']}})
    print(json.dumps({'shot': number, 'taskId': run.state[f'shot{number}TaskId'], 'videoPath': path}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['frames', 'narration', 'repair-frame', 'video'], required=True)
    parser.add_argument('--revision', type=int, choices=[1, 2], default=1)
    parser.add_argument('--shot', type=int, choices=range(1, 6), default=1)
    parser.add_argument('--profile', choices=['native1080', 'quality768'], default='native1080')
    args = parser.parse_args()
    stage = args.stage
    FOLDER.mkdir(parents=True, exist_ok=True)
    with download_lock(FOLDER, '.h3-campus-story.lock', 'Another story runner is active'):
        run = Acceptance('http://127.0.0.1:18080', REPORT)
        try:
            if completed_story_check(run):
                return
            prepare(run)
            if stage == 'frames': frames(run)
            elif stage == 'narration': narration(run)
            elif stage == 'repair-frame': repair_frame(run, args.revision)
            else: video(run, args.shot, args.profile)
        except Exception as error:
            status = 'Failed' if isinstance(error, TaskFailure) and error.status == 'Failed' else 'Blocked'
            run.save(status, technicalStatus=status, error=str(error)[:1000])
            print(type(error).__name__ + ': ' + str(error)[:600], flush=True)
            raise SystemExit(1)


if __name__ == '__main__':
    main()

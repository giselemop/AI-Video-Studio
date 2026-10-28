"""Actual no-generation checks for the explicit cross-resolution audio-copy option."""
import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import API, FOLDER, Run, media, sha, write

run = Run(API, FOLDER / 'run.json')
run.access()
original = run.state['originalPath']
other_resolution = 'Artifacts/project-30/video/task-1206/v0001/v0001_seedvr2_10s_complete_audio_debda17254c8.mp4'
base = dict(projectId=run.state['projectId'], taskType='Concat', resourceClass='CPU',
            stage='Audio-Copy-Preflight-Only', maxRetries=0,
            parameters=dict(files=[other_resolution], videoSha256=sha(media(other_resolution)),
                audioStreamCopyFrom=original, audioStreamCopySha256=run.state['originalSha256'],
                allowResolutionDifference=True, outputName='preflight_only_never_generated.mp4'))
checks = []
before = [t['id'] for t in run.api('/api/tasks?limit=1000')]


def check(name, body, expected):
    result = run.api('/api/tasks/preflight', body)
    if result['passed'] != expected:
        raise RuntimeError('Unexpected audio-copy preflight: ' + name + ': ' + str(result['issues']))
    checks.append(dict(name=name, status='Passed', expectedAccepted=expected, issues=result['issues']))


check('Same timeline with explicitly different resolution', base, True)
for name, key, value in [('Explicit false keeps equal-resolution rule', 'allowResolutionDifference', False),
    ('String opt-in rejected', 'allowResolutionDifference', 'true'), ('Null opt-in rejected', 'allowResolutionDifference', None),
    ('Numeric opt-in rejected', 'allowResolutionDifference', 1),
    ('Audio source hash drift', 'audioStreamCopySha256', '0'*64), ('Video hash drift', 'videoSha256', '0'*64),
    ('No mixed resize parameters', 'targetWidth', 2560), ('No mixed caption parameters', 'subtitlePath', run.state['subtitlePath']),
    ('No mixed audio synthesis', 'audioTracks', []), ('No frame-rate conversion', 'targetFps', 60)]:
    body = copy.deepcopy(base)
    body['parameters'][key] = value
    check(name, body, False)
body = copy.deepcopy(base)
del body['parameters']['allowResolutionDifference']
check('Default still requires equal resolution', body, False)
body = copy.deepcopy(base)
body['parameters']['files'] = [original]
body['parameters']['videoSha256'] = run.state['originalSha256']
del body['parameters']['allowResolutionDifference']
check('Legacy same-resolution copy still accepted', body, True)
body = copy.deepcopy(base)
first = run.state['shot1Attempt1Path']
body['parameters'].update(files=[first], videoSha256=sha(media(first)))
check('Different duration and frame count still rejected', body, False)
body = copy.deepcopy(base)
body['parameters']['allowResolutionDifference'] = 'true'
response = run.session.post(API + '/api/tasks', json=body, headers={'Origin': API}, timeout=60)
if response.status_code != 422 or response.json().get('preflight', {}).get('passed') is not False:
    raise RuntimeError('Invalid actual POST was not rejected')
after = [t['id'] for t in run.api('/api/tasks?limit=1000')]
if before != after:
    raise RuntimeError('Rejected POST or preflight created a task')
write(FOLDER / 'audio-preflight-regression.json', dict(status='Passed', checks=checks, rejectedPostStatus=422,
    newTasks=0, note='Existing differently sized films are metadata-only fixtures; no media/audio output was generated.'))
print(f'Passed: {len(checks)} actual audio-copy preflight cases plus rejected POST; zero tasks created')

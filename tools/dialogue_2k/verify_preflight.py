"""Real loopback preflight checks for QHD and the unchanged source-size route."""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import API, FOLDER, Run, write

run = Run(API, FOLDER / 'run.json')
run.access()
source = run.state['shots'][0]
version = run.api('/api/video-restore/status')['engineVersion']
base = dict(projectId=run.state['projectId'], taskType='VideoRestore', resourceClass='GPU',
    stage='QHD-Preflight-Only', maxRetries=0, parameters=dict(input=source['path'],
    sourceSha256=source['sha256'], engineVersion=version, strength=.35, cutFrames=[],
    outputProfile='qhd1440', targetWidth=2560, targetHeight=1440))
checks = []
before = [t['id'] for t in run.api('/api/tasks?limit=1000')]


def check(name, body, expected):
    result = run.api('/api/tasks/preflight', body)
    if result['passed'] != expected:
        raise RuntimeError('Unexpected preflight result: ' + name + ': ' + str(result['issues']))
    checks.append(dict(name=name, status='Passed', expectedAccepted=expected, issues=result['issues']))


check('Explicit QHD upscale', base, True)
legacy = copy.deepcopy(base)
for key in ['outputProfile', 'targetWidth', 'targetHeight']:
    del legacy['parameters'][key]
check('Legacy source geometry remains accepted', legacy, True)
for name, key, value in [('Unknown profile', 'outputProfile', 'anything'),
    ('Null profile', 'outputProfile', None), ('Boolean profile', 'outputProfile', True),
    ('Wrong width', 'targetWidth', 2048), ('Wrong height', 'targetHeight', 1080),
    ('String width', 'targetWidth', '2560'), ('Boolean height', 'targetHeight', True),
    ('Null width', 'targetWidth', None), ('Floating dimension', 'targetWidth', 2560.5),
    ('Implicit upscale rejected', 'outputProfile', 'source'),
    ('Source digest drift', 'sourceSha256', '0' * 64),
    ('Engine drift', 'engineVersion', 'changed'), ('Too much reconstruction', 'strength', 1.1),
    ('String strength', 'strength', '.35'), ('Invalid cut', 'cutFrames', [53])]:
    body = copy.deepcopy(base)
    body['parameters'][key] = value
    check(name, body, False)
for key in ['targetWidth', 'targetHeight']:
    body = copy.deepcopy(base)
    del body['parameters'][key]
    check('Missing ' + key, body, False)
body = copy.deepcopy(base)
body['parameters'].update(targetWidth=3840, targetHeight=2160)
check('4K is outside the admitted profile', body, False)
body = copy.deepcopy(base)
body['resourceClass'] = 'CPU'
check('GPU queue still required', body, False)
body = copy.deepcopy(base)
body['episodeId'] = 1
check('Formal association still rejected', body, False)
after = [t['id'] for t in run.api('/api/tasks?limit=1000')]
if before != after:
    raise RuntimeError('Read-only preflight created or changed task list')
write(FOLDER / 'preflight-regression.json', dict(status='Passed', checks=checks, newTasks=0))
print(f'Passed: {len(checks)} actual preflight cases; zero tasks submitted')

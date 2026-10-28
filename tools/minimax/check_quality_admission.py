"""Check H3 profile admission without starting any valid generation task."""
import copy
import json
from pathlib import Path

from run_local_acceptance import Acceptance


def main():
    folder = Path(r'C:\install\AI\Data\H3Quality20261018')
    run = Acceptance('http://127.0.0.1:18080', folder / 'run.json')
    run.access()
    # A freshly restarted server has no in-memory hash cache. This reads local
    # weights only; allow its full bounded verification before the API checks.
    run.api('/api/minimax/local/verify', {}, timeout=600)
    profiles = {p['id']: p for p in run.api('/api/minimax/local/status')['generationProfiles']}
    before = {t['id'] for t in run.api('/api/dashboard')['recentTasks']}
    base = {
        'projectId': run.state['projectId'], 'taskType': 'ImageToVideo', 'resourceClass': 'GPU',
        'workflowId': profiles['quality768']['workflowId'], 'inputImagePath': run.state['firstFramePath'],
        'stage': 'MiniMax-Local-Experiment', 'maxRetries': 0,
        'parameters': {'profile': 'quality768', 'prompt': run.state['videoPrompt'],
                       'seed': run.state['seed'], 'width': 1376, 'height': 768,
                       'frames': 124, 'fps': 24, 'steps': 20, 'extractNativeAudio': True}
    }
    checks = []
    for profile in ('quality768', 'baseline480'):
        body = copy.deepcopy(base)
        chosen = profiles[profile]
        body['workflowId'] = chosen['workflowId']
        body['parameters'].update(profile=profile, width=chosen['width'], height=chosen['height'])
        result = run.api('/api/tasks/preflight', body)
        if not result['passed']:
            raise RuntimeError('Valid profile rejected: ' + profile + ': ' + str(result['issues']))
        checks.append({'case': profile + '-valid-preflight', 'status': 'Passed'})

    cases = []
    wrong_workflow = copy.deepcopy(base)
    wrong_workflow['workflowId'] = profiles['baseline480']['workflowId']
    cases.append(('cross-profile-workflow', wrong_workflow))
    missing = copy.deepcopy(base)
    del missing['parameters']['profile']
    cases.append(('768-without-profile', missing))
    for key, value in (('fps', 60), ('frames', 121), ('steps', 8), ('width', 1344), ('profile', 'automatic')):
        body = copy.deepcopy(base)
        body['parameters'][key] = value
        cases.append(('invalid-' + key, body))

    for name, body in cases:
        preflight = run.api('/api/tasks/preflight', body)
        if preflight['passed']:
            raise RuntimeError('Invalid profile unexpectedly passed; no task submitted: ' + name)
        response = run.session.post(run.base + '/api/tasks', json=body,
                                    headers={'Origin': run.base}, timeout=60)
        if response.status_code != 422:
            raise RuntimeError('Invalid admission returned HTTP ' + str(response.status_code) + ': ' + name)
        checks.append({'case': name, 'status': 'Passed', 'httpStatus': response.status_code,
                       'issues': response.json()['preflight']['issues']})

    after = {t['id'] for t in run.api('/api/dashboard')['recentTasks']}
    if after != before:
        raise RuntimeError('Task set changed during admission checks; inspect before declaring no submissions')
    report = {'status': 'Passed', 'checks': checks, 'taskSetUnchanged': True,
              'validGenerationSubmissions': 0}
    (folder / 'admission-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'Passed', 'checks': len(checks), 'taskSetUnchanged': True}))


if __name__ == '__main__':
    main()

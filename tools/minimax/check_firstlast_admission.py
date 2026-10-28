"""Real local preflight and invalid-POST checks; never submit a valid GPU task."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from run_local_acceptance import Acceptance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:18080')
    parser.add_argument('--project-id', type=int, required=True)
    parser.add_argument('--first', required=True)
    parser.add_argument('--last', required=True)
    parser.add_argument('--folder', type=Path, default=Path(r'C:\install\AI\Data\VisualValidation20261024\h3-integration'))
    args = parser.parse_args()
    run = Acceptance(args.base, args.folder / 'admission-run.json')
    run.access()
    root = Path(r'C:\install\AI\Data').resolve()

    def digest(relative):
        path = (root / relative).resolve()
        path.relative_to(root)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    profiles = {p['id']: p for p in run.api('/api/minimax/local/status')['generationProfiles']}
    if 'firstlast480' not in profiles or not profiles['firstlast480']['workflowId']:
        raise RuntimeError('Deploy new backend and register firstlast480 before admission checks')
    before = {t['id'] for t in run.api('/api/dashboard')['recentTasks']}
    parameters = {'provider': 'MiniMaxLocal', 'profile': 'firstlast480', 'textToVideo': False,
                  'conditioningMode': 'FirstLastFrame', 'prompt': 'One gentle local test gesture.', 'seed': 2026102401,
                  'width': 864, 'height': 480, 'frames': 124, 'fps': 24, 'steps': 20,
                  'firstFrameSha256': digest(args.first), 'lastFrameSha256': digest(args.last),
                  'lastFramePath': args.last, 'inputSlots': {'firstFrame': args.first, 'lastFrame': args.last},
                  'extractNativeAudio': True}
    base = {'projectId': args.project_id, 'taskType': 'ImageToVideo', 'resourceClass': 'GPU',
            'workflowId': profiles['firstlast480']['workflowId'], 'inputImagePath': args.first,
            'stage': 'MiniMax-Local-Experiment', 'maxRetries': 0, 'parameters': parameters}
    checks = []
    result = run.api('/api/tasks/preflight', base, timeout=600)
    if not result['passed']:
        raise RuntimeError('Valid first/last preflight rejected: ' + str(result['issues']))
    checks.append({'case': 'valid-firstlast-preflight', 'status': 'Passed', 'preflight': result})
    cases = []
    for name, change in [('invalid-fps', ('fps', 60)), ('invalid-frames', ('frames', 121)),
                         ('invalid-steps', ('steps', 8)), ('invalid-width', ('width', 832)),
                         ('drift-first-sha', ('firstFrameSha256', '0' * 64)),
                         ('drift-last-sha', ('lastFrameSha256', '0' * 64))]:
        body = copy.deepcopy(base)
        body['parameters'][change[0]] = change[1]
        cases.append((name, body))
    body = copy.deepcopy(base); body['parameters'].pop('lastFrameSha256'); cases.append(('missing-last-sha', body))
    body = copy.deepcopy(base); body['parameters']['inputSlots'].pop('lastFrame'); cases.append(('missing-last-slot', body))
    body = copy.deepcopy(base); body['parameters']['inputSlots']['firstFrame'] = args.last; cases.append(('first-slot-mismatch', body))
    body = copy.deepcopy(base); body['parameters']['lastFramePath'] = '../outside.png'; body['parameters']['inputSlots']['lastFrame'] = '../outside.png'; cases.append(('outside-last-path', body))
    body = copy.deepcopy(base); body['workflowId'] = profiles['baseline480']['workflowId']; cases.append(('cross-profile-workflow', body))
    for name, body in cases:
        result = run.api('/api/tasks/preflight', body, timeout=600)
        if result['passed']:
            raise RuntimeError('Unexpected valid preflight; invalid POST skipped: ' + name)
        body['idempotencyKey'] = f'h3-firstlast-audit:{run.state["runId"]}:{name}'
        response = run.session.post(run.base + '/api/tasks', json=body, headers={'Origin': run.base}, timeout=600)
        if response.status_code != 422:
            raise RuntimeError(f'Invalid request returned HTTP {response.status_code}: {name}; inspect tasks before continuing')
        checks.append({'case': name, 'status': 'Passed', 'httpStatus': 422, 'issues': result['issues']})
    after = {t['id'] for t in run.api('/api/dashboard')['recentTasks']}
    if before != after:
        raise RuntimeError('Task set changed during audit; no zero-submission claim made')
    report = {'status': 'Passed', 'validGpuSubmissions': 0, 'taskSetUnchanged': True, 'checks': checks}
    args.folder.mkdir(parents=True, exist_ok=True)
    (args.folder / 'admission-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'Passed', 'checks': len(checks), 'validGpuSubmissions': 0, 'taskSetUnchanged': True}))


if __name__ == '__main__':
    main()

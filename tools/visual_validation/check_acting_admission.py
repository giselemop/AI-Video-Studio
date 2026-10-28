"""Audit local VisualActing admission only; never POST a valid generation request.

Each negative case changes one guard factor. A manifest pathname and its content
hash are recomputed only as the derived envelope for changed manifest content.
The expected failed check and message are asserted before and after invalid POST.
Run only after the primary agent confirms that the local acting environment is ready.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
DATA = (ROOT.parent / 'Data').resolve()
RUN_FOLDER = DATA / 'VisualValidation20261024'
sys.path.insert(0, str(ROOT / 'tools' / 'minimax'))
from run_local_acceptance import Acceptance


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # All files are private audit evidence. Never overwrite an earlier run.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def digest(path: Path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def governed(value: str | Path):
    path = (DATA / value).resolve(strict=True)
    if not path.is_relative_to(DATA) or not path.is_file():
        raise ValueError('Existing local Data file required')
    return path


def relative(path: Path):
    return path.resolve().relative_to(DATA).as_posix()


def failed_checks(result):
    return [item for item in result.get('checks', []) if item.get('passed') is False]


def assert_target_failure(result, name: str, expected_check: str, message_part: str):
    failures = failed_checks(result)
    names = {item.get('name') for item in failures}
    if result.get('passed') is not False or names != {expected_check}:
        raise RuntimeError(f'{name}: expected only {expected_check} to fail, got {sorted(str(x) for x in names)}')
    if message_part and not any(message_part in str(item.get('message', '')) for item in failures):
        raise RuntimeError(f'{name}: rejection did not identify the intended guard ({message_part})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:18081')
    parser.add_argument('--project-id', type=int, default=38)
    args = parser.parse_args()
    state_file = governed(RUN_FOLDER / 'run.json')
    state_hash = digest(state_file)
    state = read(state_file)
    if state.get('projectId') != args.project_id:
        raise RuntimeError('Audit project must match the existing validation run; no project is created')
    source = governed('VisualValidation20261024/inputs/female-reference.png')
    driving = governed(state['driverPath'])
    frozen = {item['path']: item['sha256'] for item in state.get('preserved', [])}
    for path in (source, driving):
        expected = frozen.get(relative(path))
        if expected and digest(path) != expected:
            raise RuntimeError('Existing frozen source drifted: ' + relative(path))
    script = ROOT / 'tools' / 'visual_pilot_acting' / 'run.py'
    engine_hash = digest(script)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    folder = RUN_FOLDER / 'evidence' / 'acting-admission' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    run = Acceptance(args.base, folder / 'session.json')
    report = {
        'schemaVersion': 1, 'kind': 'PreflightAndInvalidPostOnly',
        'status': 'Blocked', 'projectId': args.project_id,
        'fixtureOnly': True, 'newGeneratedMedia': False, 'validGpuSubmissions': 0,
        'sourcePath': relative(source), 'sourceSha256': digest(source),
        'drivingPath': relative(driving), 'drivingSha256': digest(driving),
        'engineVersion': engine_hash, 'checks': [],
        'taskSetUnchanged': None, 'runStateUnchanged': None,
        'contentReview': 'NeedReview', 'publicationStatus': 'Blocked',
    }
    before_tasks = None

    def tasks():
        values = run.api('/api/tasks?limit=500', timeout=60)
        if not isinstance(values, list):
            raise RuntimeError('Unexpected task-list shape; zero-task-change claim withheld')
        return {item['id'] for item in values}

    def assert_no_new_tasks():
        current = tasks()
        if before_tasks != current:
            report['taskSetUnchanged'] = False
            report['addedTaskIds'] = sorted(current - before_tasks)
            report['removedTaskIds'] = sorted(before_tasks - current)
            raise RuntimeError('Task IDs changed during audit; inspect before further requests')

    def body_for_manifest(manifest, name):
        path = folder / 'manifests' / (name + '.json')
        write(path, manifest)
        return {
            'projectId': args.project_id, 'taskType': 'VisualActing', 'resourceClass': 'GPU',
            'stage': 'VisualValidation-AdmissionFixture', 'maxRetries': 0,
            'parameters': {'manifest': relative(path), 'manifestSha256': digest(path), 'engineVersion': engine_hash},
        }

    manifest = {
        'artifactKind': 'PreflightOnlyFixture', 'notGeneratedResult': True,
        'sourcePath': relative(source), 'sourceSha256': report['sourceSha256'],
        'drivingPath': relative(driving), 'drivingSha256': report['drivingSha256'],
        'driverOrigin': 'existing-local-generated-video', 'durationSeconds': 2.0,
        'drivingStartSeconds': 0.0, 'drivingMultiplier': 0.6, 'animationRegion': 'exp',
        'licenseAcknowledgement': 'ExperimentalNonCommercialInsightFaceWeights',
    }
    try:
        run.access()
        run.save(stage='CheckingActingAdmission', fixtureOnly=True, validGpuSubmissions=0)
        before_tasks = tasks()
        base = body_for_manifest(manifest, 'valid-control')
        write(folder / 'valid-request.json', base)
        valid = run.api('/api/tasks/preflight', base, timeout=600)
        write(folder / 'valid-preflight.json', valid)
        if valid.get('passed') is not True or failed_checks(valid):
            raise RuntimeError('Valid control failed; LP environment or fixture is not ready. Invalid POST tests skipped.')
        report['checks'].append({'case': 'valid-preflight-only', 'status': 'Passed', 'postedGeneration': False})
        assert_no_new_tasks()
        cases = []

        def manifest_case(name, key, value, message):
            changed = copy.deepcopy(manifest)
            changed[key] = value
            differing = [item for item in manifest if manifest[item] != changed[item]]
            if differing != [key]:
                raise AssertionError('Negative manifest must change exactly one guard factor')
            body = body_for_manifest(changed, name)
            cases.append((name, body, 'actingManifest', message, {'manifestField': key, 'derivedEnvelope': ['manifest', 'manifestSha256']}))

        # Use an EXISTING valid image outside Data, with its correct hash. A
        # nonexistent path would also fail File.Exists and could falsely appear
        # to prove the root boundary. Prefer the identical queue-copied source.
        inputs = ROOT.parent / 'ComfyUI' / 'input'
        candidates = [path for path in inputs.glob('*.png') if path.stat().st_size == source.stat().st_size][:50]
        candidates.sort(key=lambda path: digest(path) != report['sourceSha256'])
        candidates.append(inputs / 'bench_identity_anchor.png')
        boundary = None
        for candidate in candidates:
            if not candidate.is_file() or candidate.resolve().is_relative_to(DATA):
                continue
            process = subprocess.run([r'C:\install\FFmpeg\bin\ffprobe.exe', '-v', 'error', '-count_frames',
                '-show_entries', 'stream=codec_type,width,height,nb_read_frames', '-of', 'json', str(candidate)],
                capture_output=True, text=True, check=True, timeout=30)
            streams = json.loads(process.stdout).get('streams', [])
            image = next((item for item in streams if item.get('codec_type') == 'video'), {})
            width, height = image.get('width', 0), image.get('height', 0)
            if 256 <= width <= 1280 and 256 <= height <= 1280 and width % 2 == height % 2 == 0 and str(image.get('nb_read_frames')) == '1':
                boundary = candidate.resolve()
                break
        if boundary is None:
            raise RuntimeError('No existing valid outside-Data boundary fixture found; no weak nonexistent-path test is used')
        boundary_hash = digest(boundary)
        report['existingBoundaryFixture'] = {'path': str(boundary), 'sha256': boundary_hash,
            'sameBytesAsValidSource': boundary_hash == report['sourceSha256'], 'newFileCreated': False}
        outside_manifest = copy.deepcopy(manifest)
        outside_manifest['sourcePath'] = str(boundary)
        outside_manifest['sourceSha256'] = boundary_hash
        outside_body = body_for_manifest(outside_manifest, 'source-outside-data')
        cases.append(('source-outside-data', outside_body, 'actingManifest', '表演输入必须位于受控Data目录',
            {'guardFactor': 'governed location of coherent source asset', 'manifestFields': ['sourcePath', 'sourceSha256'],
             'sha256MatchesActualExistingFile': True, 'derivedEnvelope': ['manifest', 'manifestSha256']}))
        manifest_case('source-sha-drift', 'sourceSha256', '0' * 64, '表演输入哈希不符')
        manifest_case('driving-sha-drift', 'drivingSha256', '0' * 64, '表演输入哈希不符')
        manifest_case('duration-below-range', 'durationSeconds', 1.5, '仅开放2至3秒')
        # 2.01 is in the admitted duration range, but not an integer number
        # of frames at either admitted driving cadence (24 or 25 FPS).
        manifest_case('duration-not-frame-aligned', 'durationSeconds', 2.01, '帧数可精确对齐')
        manifest_case('driving-segment-too-short', 'drivingStartSeconds', 60.0, '驱动片段长度不足')
        manifest_case('license-not-acknowledged', 'licenseAcknowledgement', 'NotAcknowledged', '必须明确绑定实验许可')
        for name, field, value, check, message in [
            ('manifest-sha-drift', 'parameters.manifestSha256', '0' * 64, 'actingManifest', '表演清单哈希不符'),
            ('engine-version-drift', 'parameters.engineVersion', '0' * 64, 'actingManifest', '脚本版本已改变'),
            ('cpu-resource-rejected', 'resourceClass', 'CPU', 'actingGpuQueue', 'GPU全局互斥队列'),
            # Nonempty productionRunId alone exercises preview-only admission.
            # No nonexistent Episode/Shot is added to cause unrelated failures.
            ('formal-run-link-rejected', 'productionRunId', 1, 'actingPreviewOnly', '独立实验预览'),
        ]:
            body = copy.deepcopy(base)
            if field.startswith('parameters.'):
                body['parameters'][field.split('.', 1)[1]] = value
            else:
                body[field] = value
            cases.append((name, body, check, message, {'requestField': field}))

        for name, body, check, message, factor in cases:
            write(folder / (name + '-request.json'), body)
            preflight = run.api('/api/tasks/preflight', body, timeout=600)
            write(folder / (name + '-preflight.json'), preflight)
            assert_target_failure(preflight, name, check, message)
            # Only an already rejected request is sent to the actual task API.
            # A valid VisualActing request is never POSTed by this script.
            response = run.session.post(run.base + '/api/tasks', json=body,
                headers={'Origin': run.base, 'Idempotency-Key': f'acting-admission:{run.state["runId"]}:{name}'}, timeout=600)
            try:
                payload = response.json()
            except ValueError:
                payload = {'error': 'Non-JSON response'}
            write(folder / (name + '-post.json'), {'httpStatus': response.status_code, 'body': payload})
            if response.status_code != 422:
                raise RuntimeError(f'{name}: expected HTTP422; got {response.status_code}. Inspect task IDs before continuing.')
            post_preflight = payload.get('preflight')
            if not isinstance(post_preflight, dict):
                raise RuntimeError(f'{name}: HTTP422 did not include the expected preflight evidence')
            assert_target_failure(post_preflight, name + '-post', check, message)
            assert_no_new_tasks()
            report['checks'].append({'case': name, 'status': 'Passed', 'httpStatus': 422,
                                     'singleGuardFactor': factor, 'failedCheck': check, 'targetMessage': message})
            print(json.dumps({'case': name, 'status': 'Passed', 'httpStatus': 422}), flush=True)
        assert_no_new_tasks()
        report['taskSetUnchanged'] = True
        if digest(source) != report['sourceSha256'] or digest(driving) != report['drivingSha256']:
            raise RuntimeError('Existing input was modified during admission audit')
        if digest(boundary) != boundary_hash:
            raise RuntimeError('Existing boundary fixture was modified during admission audit')
        if digest(script) != engine_hash:
            raise RuntimeError('Engine changed during admission audit; results cannot attest the current version')
        report['runStateUnchanged'] = digest(state_file) == state_hash
        if not report['runStateUnchanged']:
            raise RuntimeError('Main run state changed concurrently; source-state preservation claim withheld')
        report['status'] = 'Passed'
    except Exception as error:
        report['status'] = 'Failed'
        report['error'] = str(error)[:1600]
        if before_tasks is not None:
            try:
                current = tasks()
                report['taskSetUnchanged'] = current == before_tasks
                report['addedTaskIds'] = sorted(current - before_tasks)
            except Exception:
                report['taskSetUnchanged'] = None
        report['runStateUnchanged'] = digest(state_file) == state_hash
        write(folder / 'report.json', report)
        print(json.dumps({'status': 'Failed', 'report': str(folder / 'report.json'), 'error': report['error']}), flush=True)
        raise
    write(folder / 'report.json', report)
    print(json.dumps({'status': 'Passed', 'checks': len(report['checks']), 'invalidPostCount': len(report['checks']) - 1,
                      'validGpuSubmissions': 0, 'taskSetUnchanged': True, 'report': str(folder / 'report.json')}), flush=True)


if __name__ == '__main__':
    main()

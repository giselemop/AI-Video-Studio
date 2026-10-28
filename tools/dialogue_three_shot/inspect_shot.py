"""CPU-only observation sheets for a real three-shot source video.

Spatial role labels are expectations from the shot plan, not identity recognition.
Mouth geometry is a review aid and never a phoneme/lip-sync accuracy score.
Invoke with the existing IdentityWorker Python runtime; this does not download models.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT.parent
DATA = AI / 'Data'
FOLDER = DATA / 'DialogueThreeShot20261023'
sys.path.insert(0, str(ROOT / 'tools' / 'identity_foundation'))
from identity_foundation import import_runtime


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def media_path(value):
    path = Path(value)
    path = (path if path.is_absolute() else DATA / path).resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError('Source must be a real video inside Data')
    return path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sheet(tiles, columns, path):
    if not tiles:
        return False
    width, height = tiles[0].size
    canvas = Image.new('RGB', (width * columns, height * math.ceil(len(tiles) / columns)), '#151b24')
    for index, tile in enumerate(tiles):
        canvas.paste(tile, (index % columns * width, index // columns * height))
    canvas.save(path, quality=92)
    return True


def thumbnail(image, size):
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, '#080b10')
    canvas.paste(copy, ((size[0] - copy.width) // 2, (size[1] - copy.height) // 2))
    return canvas


def inspect(index):
    run = read_json(FOLDER / 'run.json')
    source = media_path(run[f'shot{index}Path'])
    source_digest = digest(source)
    if source_digest != run[f'shot{index}Sha256']:
        raise RuntimeError('Recorded shot source changed')
    timeline = run.get('timeline') or read_json(FOLDER / 'audio' / 'timeline.json')
    shots = run.get('shots') or read_json(FOLDER / 'audio' / 'shot-definitions.json')
    shot = next(item for item in shots if item['index'] == index)
    global_offset = float(shot['startSeconds'])
    final_end = float(shot['endSeconds'])
    roles = ['female'] if index == 1 else ['male'] if index == 2 else ['female', 'male']
    # FaceAnalysis would attempt to fetch a missing model pack. Fail before import
    # or construction instead, because this review uses existing local assets only.
    model_root = AI / 'Models' / 'InsightFace'
    for filename in ['det_10g.onnx', '1k3d68.onnx']:
        model = model_root / 'models' / 'buffalo_l' / filename
        if not model.is_file() or model.stat().st_size == 0:
            raise RuntimeError('Existing local InsightFace model is missing: ' + filename)
    cv2, np, ort, FaceAnalysis = import_runtime()
    app = FaceAnalysis(name='buffalo_l', root=str(model_root), providers=['CPUExecutionProvider'],
                       allowed_modules=['detection', 'landmark_3d_68'])
    app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=.45)
    providers = {name: model.session.get_providers() for name, model in app.models.items()}
    if any(value != ['CPUExecutionProvider'] for value in providers.values()):
        raise RuntimeError('This inspection must use CPUExecutionProvider only')
    out = FOLDER / f'inspection-{index}'
    out.mkdir(parents=True, exist_ok=True)
    previous_report = out / 'mouth-observations.json'
    if previous_report.exists():
        old_digest = str(read_json(previous_report).get('sourceSha256', ''))
        if old_digest and old_digest != source_digest:
            if len(old_digest) != 64 or any(value not in '0123456789abcdef' for value in old_digest):
                raise RuntimeError('Previous inspection has an invalid source hash; preserve and inspect it manually')
            archive = out / ('previous-' + old_digest[:12])
            archive.mkdir(exist_ok=True)
            for filename in ['contact.jpg', 'speaking-faces.jpg', 'mouth-observations.json']:
                old_file = out / filename
                if old_file.exists():
                    shutil.copy2(old_file, archive / filename)
    cap = cv2.VideoCapture(str(source))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    metadata_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or metadata_frames <= 0:
        cap.release()
        raise RuntimeError('Source video metadata could not be read')
    observations, thumbs, faces_tiles = [], [], []
    decoded = 0
    try:
        for frame_index in range(metadata_frames):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f'Source decode failed at frame {frame_index}/{metadata_frames}')
            decoded += 1
            if frame_index % 3:
                continue
            local_time = frame_index / fps
            global_time = global_offset + local_time
            used_in_final = global_time < final_end - 1e-6
            faces = sorted(app.get(frame), key=lambda face: float(face.bbox[0]))
            count_matches = len(faces) == len(roles)
            row = {'frame': frame_index, 'localTimeSeconds': local_time,
                   'globalTimeSeconds': global_time, 'usedInFinal': used_in_final,
                   'faceCount': len(faces), 'expectedFaceCount': len(roles),
                   'faceCountMatches': count_matches,
                   'expectedSpeakingRoles': [item['role'] for item in timeline
                                             if item['startSeconds'] <= global_time < item['endSeconds']],
                   'faces': []}
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            for position, face in enumerate(faces):
                # If detections do not match the composition, do not silently
                # assign an extra/missing face to one of the named characters.
                role = roles[position] if count_matches else None
                expected_speaker = (role in row['expectedSpeakingRoles']) if role else None
                box = [float(value) for value in face.bbox]
                landmarks = getattr(face, 'landmark_3d_68', None)
                gap = None
                if landmarks is not None:
                    points = np.asarray(landmarks)[:, :2]
                    if len(points) >= 68 and np.all(np.isfinite(points)):
                        gap = float(np.linalg.norm(points[62] - points[66]) /
                                    max(np.linalg.norm(points[60] - points[64]), 1e-6))
                row['faces'].append({'positionFromLeft': position + 1, 'role': role,
                                     'roleBasis': 'shot composition only; identity unverified',
                                     'bbox': box, 'mouthGapRatio': gap,
                                     'expectedSpeaker': expected_speaker,
                                     'detConfidence': float(face.det_score)})
                if frame_index % 12 == 0:
                    x1, y1, x2, y2 = box
                    bounds = (max(0, math.floor(x1 - 10)), max(0, math.floor(y1 - 10)),
                              min(image.width, math.ceil(x2 + 10)), min(image.height, math.ceil(y2 + 10)))
                    if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                        tile = thumbnail(image.crop(bounds), (176, 192))
                        canvas = Image.new('RGB', (176, 230), '#151b24')
                        canvas.paste(tile, (0, 0))
                        label = role or f'unassigned-{position + 1}'
                        state = 'SPEAK' if expected_speaker else 'listen' if role else 'check'
                        draw = ImageDraw.Draw(canvas)
                        draw.text((5, 194), f'{global_time:.2f}s {label} {state}', fill='white')
                        draw.text((5, 211), f'local {local_time:.2f}s' + ('' if used_in_final else ' source tail'), fill='#b5c0ce')
                        faces_tiles.append(canvas)
            if frame_index % 12 == 0:
                canvas = Image.new('RGB', (416, 282), '#151b24')
                canvas.paste(thumbnail(image, (416, 240)), (0, 0))
                draw = ImageDraw.Draw(canvas)
                draw.text((8, 244), f'Shot {index} local {local_time:.2f}s / global {global_time:.2f}s', fill='white')
                draw.text((8, 261), f'faces {len(faces)}/{len(roles)}' + ('' if used_in_final else ' | source tail beyond final cut'), fill='#b5c0ce')
                thumbs.append(canvas)
            observations.append(row)
        extra, _ = cap.read()
        if extra:
            raise RuntimeError('Video contains more decoded frames than its declared frame count')
    finally:
        cap.release()
    sheet(thumbs, 3, out / 'contact.jpg')
    if not sheet(faces_tiles, 6, out / 'speaking-faces.jpg'):
        empty = Image.new('RGB', (528, 100), '#151b24')
        ImageDraw.Draw(empty).text((12, 35), 'No face crops detected; human review required.', fill='white')
        empty.save(out / 'speaking-faces.jpg', quality=92)
    report = {'status': 'NeedReview', 'scope': 'CPU detection/landmark observations only',
              'source': str(source), 'sourceSha256': source_digest, 'shotIndex': index,
              'expectedRolesFromLeft': roles, 'globalOffsetSeconds': global_offset,
              'finalShotEndSeconds': final_end, 'fps': fps, 'frames': metadata_frames,
              'decodedFrames': decoded, 'sampleStrideFrames': 3, 'sheetStrideFrames': 12,
              'sampledFrames': len(observations),
              'faceCountMatchingSamples': sum(item['faceCountMatches'] for item in observations),
              'executionProviders': providers, 'observations': observations,
              'limitations': ['Role labels reflect the planned composition, not identity recognition.',
                              'Mouth gap is geometric review aid, not phoneme alignment or lip-sync accuracy.',
                              'Expected speaker uses the frozen global audio timeline; emotion needs human review.',
                              'Face counts are detection results and may miss profile or occluded faces.']}
    (out / 'mouth-observations.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'NeedReview', 'shot': index, 'decodedFrames': decoded,
                      'sampledFrames': len(observations),
                      'faceCountMatchingSamples': report['faceCountMatchingSamples'],
                      'output': str(out)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--shot', type=int, choices=[1, 2, 3], required=True)
    inspect(parser.parse_args().shot)

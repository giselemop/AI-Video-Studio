"""CPU-only visual comparison of actual clean/restored three-shot frames.

This writes review sheets and provenance, never an automatic content decision.
Use the existing IdentityWorker Python runtime; no models are downloaded.
"""
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
TIMES = [.8, 1.5, 3.2, 5.3, 7.0, 9.3]
sys.path.insert(0, str(ROOT / 'tools' / 'identity_foundation'))
from identity_foundation import import_runtime


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def media(value):
    path = Path(value)
    path = (path if path.is_absolute() else DATA / path).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(DATA.resolve()):
        raise RuntimeError('Comparison media must stay inside Data')
    return path


def sha(path):
    with media(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def letterbox(image, size):
    image = image.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, '#080b10')
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def labeled(image, size, labels):
    canvas = Image.new('RGB', (size[0], size[1] + 18 * len(labels) + 6), '#151b24')
    canvas.paste(letterbox(image, size), (0, 0))
    draw = ImageDraw.Draw(canvas)
    for index, label in enumerate(labels):
        draw.text((5, size[1] + 3 + 18 * index), label, fill='white' if index == 0 else '#b5c0ce')
    return canvas


def sheet(pairs, path):
    if not pairs:
        return False
    width, height = pairs[0][0].size
    canvas = Image.new('RGB', (width * 2, height * len(pairs)), '#151b24')
    for index, (before, after) in enumerate(pairs):
        canvas.paste(before, (0, index * height))
        canvas.paste(after, (width, index * height))
    canvas.save(path, quality=92)
    return True


def frame_at(cap, index, cv2):
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    if not ok or abs(cap.get(cv2.CAP_PROP_POS_FRAMES) - (index + 1)) > .5:
        raise RuntimeError(f'Unable to decode the requested comparison frame {index}')
    return frame


def main():
    run = read_json(FOLDER / 'run.json')
    before_path, after_path = media(run['assemblyPath']), media(run['restorePath'])
    before_sha, after_sha = sha(before_path), sha(after_path)
    if before_sha != run['assemblySha256'] or after_sha != run['restoreSha256']:
        raise RuntimeError('A recorded comparison source changed')
    model_root = AI / 'Models' / 'InsightFace'
    model = model_root / 'models' / 'buffalo_l' / 'det_10g.onnx'
    if not model.is_file() or model.stat().st_size == 0:
        raise RuntimeError('The existing local detection model is missing; no download attempted')
    cv2, np, ort, FaceAnalysis = import_runtime()
    app = FaceAnalysis(name='buffalo_l', root=str(model_root),
                       providers=['CPUExecutionProvider'], allowed_modules=['detection'])
    app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=.45)
    providers = {name: item.session.get_providers() for name, item in app.models.items()}
    if any(value != ['CPUExecutionProvider'] for value in providers.values()):
        raise RuntimeError('Comparison detection must run on CPU only')
    caps = [cv2.VideoCapture(str(path)) for path in [before_path, after_path]]
    rows, faces_pairs, full_pairs = [], [], []
    try:
        if not all(cap.isOpened() for cap in caps):
            raise RuntimeError('A comparison video could not be opened')
        specs = [{'fps': float(cap.get(cv2.CAP_PROP_FPS)),
                  'frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                  'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                  'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} for cap in caps]
        if specs[0] != specs[1] or specs[0]['fps'] <= 0:
            raise RuntimeError('Before/after frame geometry, frame count and FPS must match')
        fps = specs[0]['fps']
        for time in TIMES:
            frame_index = round(time * fps)
            if frame_index >= specs[0]['frames']:
                raise RuntimeError('Requested comparison time is outside the video')
            before_frame, after_frame = [frame_at(cap, frame_index, cv2) for cap in caps]
            images = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                      for frame in [before_frame, after_frame]]
            actual_time = frame_index / fps
            full_pairs.append(tuple(labeled(image, (640, 360),
                                             [f'{actual_time:.3f}s | ' + label,
                                              f'frame {frame_index}; requested {time:.2f}s'])
                                    for image, label in zip(images, ['SOURCE', 'RESTORED'])))
            detected = sorted(app.get(before_frame), key=lambda face: float(face.bbox[0]))
            row = {'requestedTimeSeconds': time, 'actualTimeSeconds': actual_time,
                   'frame': frame_index, 'faceCountBefore': len(detected), 'faces': []}
            for position, face in enumerate(detected, 1):
                x1, y1, x2, y2 = [float(value) for value in face.bbox]
                width, height = x2 - x1, y2 - y1
                # The detector bounds facial skin. Include forehead/hair and a
                # little space around the head, then reuse exactly this crop
                # on the restored frame so framing cannot imply improvement.
                bounds = (max(0, math.floor(x1 - width * .20)),
                          max(0, math.floor(y1 - height * .38)),
                          min(images[0].width, math.ceil(x2 + width * .20)),
                          min(images[0].height, math.ceil(y2 + height * .14)))
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    continue
                faces_pairs.append(tuple(labeled(image.crop(bounds), (160, 180),
                                                  [f'{actual_time:.3f}s | ' + label,
                                                   f'face {position} from left'])
                                         for image, label in zip(images, ['SOURCE', 'RESTORED'])))
                row['faces'].append({'positionFromLeft': position,
                                     'detectedBBoxBefore': [x1, y1, x2, y2],
                                     'sharedCropBBox': list(bounds),
                                     'detConfidenceBefore': float(face.det_score)})
            rows.append(row)
    finally:
        for cap in caps:
            cap.release()
    out = FOLDER / 'restoration-comparison'
    out.mkdir(parents=True, exist_ok=True)
    old_report = out / 'comparison-metadata.json'
    if old_report.exists():
        old = read_json(old_report)
        if old.get('beforeSha256') != before_sha or old.get('afterSha256') != after_sha:
            old_digest = str(old.get('afterSha256', ''))
            if len(old_digest) != 64 or any(value not in '0123456789abcdef' for value in old_digest):
                raise RuntimeError('Previous comparison hash is invalid; inspect it before overwriting')
            archive = out / ('previous-' + old_digest[:12])
            archive.mkdir(exist_ok=True)
            for filename in ['comparison-metadata.json', 'faces-before-after.jpg', 'full-before-after.jpg']:
                old_file = out / filename
                if old_file.exists():
                    shutil.copy2(old_file, archive / filename)
    sheet(full_pairs, out / 'full-before-after.jpg')
    if not sheet(faces_pairs, out / 'faces-before-after.jpg'):
        empty = Image.new('RGB', (640, 100), '#151b24')
        ImageDraw.Draw(empty).text((12, 35), 'No faces detected; inspect full frames manually.', fill='white')
        empty.save(out / 'faces-before-after.jpg', quality=92)
    report = {'status': 'NeedReview', 'scope': 'Actual before/after frame comparison only',
              'beforePath': str(before_path), 'beforeSha256': before_sha,
              'afterPath': str(after_path), 'afterSha256': after_sha,
              'videoSpec': specs[0], 'requestedTimesSeconds': TIMES,
              'executionProviders': providers, 'samples': rows,
              'facePairCount': len(faces_pairs),
              'limitations': ['Faces are detected on the source only; the same rectangle is used after restoration.',
                              'Face positions are not identity verification.',
                              'These sampled stills do not establish temporal stability or lip-sync accuracy.',
                              'No content pass or restoration choice is made automatically.']}
    (out / 'comparison-metadata.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'NeedReview', 'samples': len(rows), 'facePairs': len(faces_pairs),
                      'output': str(out)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

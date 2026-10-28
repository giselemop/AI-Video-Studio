"""CPU-only same-frame comparisons; writes evidence, never selects a candidate."""
import argparse
import math
from pathlib import Path
import sys
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import DATA, FOLDER, ROOT, media, read, sha, write
sys.path.insert(0, str(ROOT / 'tools/identity_foundation'))
from identity_foundation import import_runtime


def fit(image, size):
    canvas = Image.new('RGB', size, '#0b1119')
    scale = min(size[0] / image.width, size[1] / image.height)
    item = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
    canvas.paste(item, ((size[0] - item.width) // 2, (size[1] - item.height) // 2))
    return canvas


def pair(before, after, size, label):
    canvas = Image.new('RGB', (size[0] * 2, size[1] + 32), '#17202c')
    canvas.paste(fit(before, size), (0, 32))
    canvas.paste(fit(after, size), (size[0], 32))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 9), label + ' | ORIGINAL', fill='white')
    draw.text((size[0] + 10, 9), label + ' | QHD', fill='white')
    return canvas


def sheet(rows, target):
    if not rows:
        raise RuntimeError('No actual comparison images')
    canvas = Image.new('RGB', (rows[0].width, sum(row.height for row in rows)), '#111820')
    y = 0
    for row in rows:
        canvas.paste(row, (0, y))
        y += row.height
    canvas.save(target, quality=94)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=int, choices=[1, 2, 3])
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--extra-frame', action='append', type=int, default=[])
    args = parser.parse_args()
    run = read(FOLDER / 'run.json')
    if args.index:
        source = run['shots'][args.index - 1]
        before, after = media(source['path']), media(run[f'shot{args.index}Attempt{args.attempt}Path'])
        expected = source['frames']
        indices = sorted(set([0, expected // 5, expected * 2 // 5, expected * 3 // 5, expected * 4 // 5, expected - 1]))
        out = FOLDER / f'inspection-shot-{args.index}-attempt-{args.attempt}'
    else:
        before, after = media(run['originalPath']), media(run['finalPath'])
        expected = 240
        indices = [19, 36, 52, 53, 77, 95, 96, 127, 168, 223, 239]
        out = FOLDER / 'comparison'
    if any(index < 0 or index >= expected for index in args.extra_frame):
        raise RuntimeError('Additional comparison frame is outside the actual clip')
    indices = sorted(set(indices + args.extra_frame))
    out.mkdir(exist_ok=True)
    cv2, np, ort, FaceAnalysis = import_runtime()
    model_root = ROOT.parent / 'Models/InsightFace'
    if not (model_root / 'models/buffalo_l/det_10g.onnx').is_file():
        raise RuntimeError('Existing local detection model is missing; no download allowed')
    app = FaceAnalysis(name='buffalo_l', root=str(model_root), providers=['CPUExecutionProvider'], allowed_modules=['detection'])
    app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=.45)
    providers = {name: model.session.get_providers() for name, model in app.models.items()}
    if any(value != ['CPUExecutionProvider'] for value in providers.values()):
        raise RuntimeError('Only CPU inspection is allowed')
    caps = [cv2.VideoCapture(str(path)) for path in [before, after]]
    whole, face_rows, records = [], [], []
    try:
        specs = [dict(width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                      frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), fps=cap.get(cv2.CAP_PROP_FPS)) for cap in caps]
        if any(s['frames'] != expected or s['fps'] != 24 for s in specs) or (specs[1]['width'], specs[1]['height']) != (2560, 1440):
            raise RuntimeError('Actual media does not match the frame-preserving QHD comparison')
        sx, sy = specs[1]['width'] / specs[0]['width'], specs[1]['height'] / specs[0]['height']
        for index in indices:
            frames = []
            for cap in caps:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Actual frame decoding failed')
                frames.append(frame)
            images = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) for frame in frames]
            label = f'frame {index:03} | {index/24:.3f}s'
            whole.append(pair(*images, (640, 360), label))
            detected = sorted(app.get(frames[0]), key=lambda item: float(item.bbox[0]))
            record = dict(frame=index, seconds=index / 24, detectedFaces=len(detected), faces=[])
            for number, face in enumerate(detected):
                x1, y1, x2, y2 = [float(v) for v in face.bbox]
                w, h = x2 - x1, y2 - y1
                bounds = (max(0, math.floor(x1 - .18*w)), max(0, math.floor(y1 - .30*h)),
                          min(images[0].width, math.ceil(x2 + .18*w)), min(images[0].height, math.ceil(y2 + .12*h)))
                scaled = tuple(round(value * (sx if axis % 2 == 0 else sy)) for axis, value in enumerate(bounds))
                row = pair(images[0].crop(bounds), images[1].crop(scaled), (256, 288), label + f' | face {number+1}')
                row.save(out / f'face-{index:03}-{number+1}.png')
                face_rows.append(row)
                record['faces'].append(dict(originalBounds=bounds, qhdBounds=scaled,
                                           originalKeypoints=face.kps.tolist() if face.kps is not None else None))
            records.append(record)
    finally:
        for cap in caps:
            cap.release()
    sheet(whole, out / 'full-before-after.jpg')
    sheet(face_rows, out / 'faces-before-after.jpg')
    report = dict(status='NeedReview', scope='Actual same-index frames and matching field-of-view crops; no automatic identity/lip-sync score',
                  beforePath=str(before), afterPath=str(after), beforeSha256=sha(before), afterSha256=sha(after),
                  specifications=specs, executionProviders=providers, samples=records)
    write(out / 'inspection.json', report)
    print(str(out), flush=True)


if __name__ == '__main__':
    main()

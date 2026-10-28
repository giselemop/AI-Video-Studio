"""CPU landmark observations of same-frame mouth motion, not a lip-sync score."""
import argparse
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import DATA, FOLDER, ROOT, media, read, sha, write
sys.path.insert(0, str(ROOT / 'tools/identity_foundation'))
from identity_foundation import import_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=int, required=True, choices=[1, 2, 3])
    parser.add_argument('--attempt', type=int, default=1)
    args = parser.parse_args()
    run = read(FOLDER / 'run.json')
    source = run['shots'][args.index - 1]
    paths = [media(source['path']), media(run[f'shot{args.index}Attempt{args.attempt}Path'])]
    cv2, np_, ort, FaceAnalysis = import_runtime()
    model_root = ROOT.parent / 'Models/InsightFace'
    for name in ['det_10g.onnx', '1k3d68.onnx']:
        if not (model_root / 'models/buffalo_l' / name).is_file():
            raise RuntimeError('Existing landmark model is missing; no download allowed')
    app = FaceAnalysis(name='buffalo_l', root=str(model_root), providers=['CPUExecutionProvider'],
                       allowed_modules=['detection', 'landmark_3d_68'])
    app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=.45)
    if any(model.session.get_providers() != ['CPUExecutionProvider'] for model in app.models.values()):
        raise RuntimeError('CPU-only geometry observation required')
    caps = [cv2.VideoCapture(str(path)) for path in paths]
    counts = [int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) for cap in caps]
    if counts != [source['frames'], source['frames']]:
        raise RuntimeError('Frame-preserving comparison required')
    rows, tiles = [], []
    try:
        for frame_index in range(counts[0]):
            frames = []
            for cap in caps:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Actual frame decode failed')
                frames.append(frame)
            # Give the detector the same pixel geometry on both paths.
            normalized = [cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA) for frame in frames]
            faces = [sorted(app.get(frame), key=lambda face: float(face.bbox[0])) for frame in normalized]
            expected = 2 if args.index == 3 else 1
            row = dict(frame=frame_index, seconds=frame_index / 24, expectedFaces=expected,
                       detectedFaces=[len(side) for side in faces], geometry=[])
            if all(len(side) == expected for side in faces):
                for person in range(expected):
                    points = [np.asarray(side[person].landmark_3d_68)[:, :2] for side in faces]
                    gaps = [float(np.linalg.norm(p[62]-p[66]) / max(np.linalg.norm(p[60]-p[64]), 1e-6)) for p in points]
                    row['geometry'].append(dict(positionFromLeft=person+1, originalGap=gaps[0], qhdGap=gaps[1],
                                                 absoluteGapDifference=abs(gaps[0]-gaps[1])))
                    if frame_index % 6 == 0:
                        lip = points[0][48:68]
                        lo, hi = np.min(lip, axis=0), np.max(lip, axis=0)
                        center = (lo + hi) / 2
                        half_w, half_h = max((hi[0]-lo[0])*.85, 28), max((hi[1]-lo[1])*.9, 20)
                        x1, y1 = max(0, int(center[0]-half_w)), max(0, int(center[1]-half_h))
                        x2, y2 = min(1280, int(center[0]+half_w)), min(720, int(center[1]+half_h))
                        tile = Image.new('RGB', (480, 168), '#101923')
                        draw = ImageDraw.Draw(tile)
                        for side, frame in enumerate(frames):
                            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                            sx, sy = image.width/1280, image.height/720
                            crop = image.crop((round(x1*sx), round(y1*sy), round(x2*sx), round(y2*sy)))
                            scale = min(230 / crop.width, 136 / crop.height)
                            crop = crop.resize((max(1, round(crop.width*scale)), max(1, round(crop.height*scale))), Image.Resampling.LANCZOS)
                            tile.paste(crop, (side*240+(240-crop.width)//2, 29+(136-crop.height)//2))
                            draw.text((side*240+6, 8), f'{frame_index/24:.3f}s | ' + ('ORIGINAL' if side == 0 else 'QHD'), fill='white')
                        tiles.append(tile)
            rows.append(row)
    finally:
        for cap in caps:
            cap.release()
    out = FOLDER / f'inspection-shot-{args.index}-attempt-{args.attempt}'
    out.mkdir(exist_ok=True)
    summaries = []
    for person in range(2 if args.index == 3 else 1):
        matched = [row['geometry'][person] for row in rows if len(row['geometry']) > person]
        if not matched:
            continue
        original = np.asarray([row['originalGap'] for row in matched])
        qhd = np.asarray([row['qhdGap'] for row in matched])
        summaries.append(dict(positionFromLeft=person+1, matchedFrames=len(matched),
            meanAbsoluteGapDifference=float(np.mean(abs(original-qhd))),
            maxAbsoluteGapDifference=float(np.max(abs(original-qhd))),
            zeroLagCorrelation=float(np.corrcoef(original, qhd)[0,1]) if np.std(original)>1e-6 and np.std(qhd)>1e-6 else None))
    if tiles:
        sheet = Image.new('RGB', (480, len(tiles)*168), '#101923')
        for i, tile in enumerate(tiles):
            sheet.paste(tile, (0, i*168))
        sheet.save(out / 'mouth-before-after.jpg', quality=94)
    report = dict(status='NeedReview', scope='Same-frame CPU mouth-geometry observations; no phoneme, identity or artistic accuracy score',
        index=args.index, originalSha256=sha(paths[0]), qhdSha256=sha(paths[1]),
        analysisGeometry=[1280,720], decodedFrames=counts[0], summary=summaries, observations=rows)
    write(out / 'mouth-motion.json', report)
    print(dict(decodedFrames=counts[0], summary=summaries), flush=True)


if __name__ == '__main__':
    main()

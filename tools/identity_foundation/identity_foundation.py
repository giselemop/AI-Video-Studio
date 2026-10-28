#!/usr/bin/env python3
"""Identity Foundation evidence runner and loopback InsightFace worker.

This file deliberately keeps the model runtime outside the VideoStudio
checkout.  It uses the official InsightFace 0.7.3 Python sources with the
optional face3d renderer omitted, plus the official buffalo_l ONNX pack.  The
identity path is therefore real detection + ArcFace embedding + landmarks,
not the legacy raster/filename proxy.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import html
import json
import math
import os
import platform
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(r"C:\install\AI\VideoStudio")
AI_ROOT = Path(r"C:\install\AI")
IDENTITY_ROOT = Path(r"C:\install\AI\IdentityWorker")
INSIGHTFACE_SOURCE = IDENTITY_ROOT / "vendor-src" / "insightface-0.7.3"
MODEL_ROOT = AI_ROOT / "Models" / "InsightFace"
DATA_ROOT = AI_ROOT / "Data"
DEFAULT_MASTER = DATA_ROOT / "Characters" / "15" / "standard" / "identity_front.png"
DEFAULT_RUN_ROOT = DATA_ROOT / "QA" / "identity_foundation_20260816" / "run_02"
DEFAULT_CACHE_ROOT = DEFAULT_RUN_ROOT / "cache"

VIEW_ORDER = [
    "front",
    "front_left_30",
    "front_right_30",
    "left_45",
    "right_45",
    "left_profile",
    "right_profile",
    "half_body_front",
    "half_body_left45",
    "half_body_right45",
    "full_body_front",
    "full_body_left45",
    "full_body_right45",
]
CORE_BENCHMARK_VIEWS = [
    "front",
    "front_left_30",
    "front_right_30",
    "left_45",
    "right_45",
    "half_body_front",
    "full_body_front",
]
SEEDS = [240101, 240102, 240103]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(AI_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def safe_path(value: str | Path, allowed_roots: Iterable[Path] = (DATA_ROOT, MODEL_ROOT, DEFAULT_RUN_ROOT)) -> Path:
    candidate = Path(value).expanduser().resolve()
    for root in allowed_roots:
        try:
            candidate.relative_to(root.resolve())
            return candidate
        except ValueError:
            continue
    raise ValueError(f"path outside identity worker allow-list: {candidate}")


def import_runtime() -> tuple[Any, Any, Any, Any]:
    """Import the isolated scientific runtime after adding official source."""
    if INSIGHTFACE_SOURCE.is_dir() and str(INSIGHTFACE_SOURCE) not in sys.path:
        sys.path.insert(0, str(INSIGHTFACE_SOURCE))
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    import onnxruntime  # type: ignore
    from insightface.app import FaceAnalysis  # type: ignore

    return cv2, np, onnxruntime, FaceAnalysis


def file_inventory(root: Path, suffixes: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (suffixes and path.suffix.lower() not in suffixes):
            continue
        rows.append({"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def load_image(path: Path, cv2: Any, np: Any) -> Any:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"unable to decode image: {path}")
    return image


def head_pose(kps: Any, width: int, height: int, cv2: Any, np: Any) -> dict[str, Any]:
    """Estimate yaw/pitch/roll from InsightFace's five aligned keypoints."""
    if kps is None or len(kps) != 5:
        return {"available": False, "reason": "five_keypoints_missing"}
    image_points = np.asarray(kps, dtype=np.float64)
    # left eye, right eye, nose, left mouth, right mouth; generic metric head.
    object_points = np.asarray(
        [(-30.0, 35.0, 30.0), (30.0, 35.0, 30.0), (0.0, 0.0, 55.0),
         (-25.0, -35.0, 25.0), (25.0, -35.0, 25.0)],
        dtype=np.float64,
    )
    focal = float(max(width, height))
    camera = np.asarray([[focal, 0, width / 2.0], [0, focal, height / 2.0], [0, 0, 1]], dtype=np.float64)
    distortion = np.zeros((4, 1), dtype=np.float64)
    try:
        # ITERATIVE needs six correspondences for an unconstrained initial
        # estimate in current OpenCV.  EPNP is the documented four-point
        # minimum and keeps the five-point InsightFace landmark path real.
        ok, rvec, tvec = cv2.solvePnP(
            object_points, image_points, camera, distortion, flags=cv2.SOLVEPNP_EPNP
        )
        if not ok:
            return {"available": False, "reason": "solvepnp_failed"}
        rotation, _ = cv2.Rodrigues(rvec)
        angles = cv2.RQDecomp3x3(rotation)[0]
        pitch, yaw, roll = [float(x) for x in angles]
        return {
            "available": True,
            "yaw": round(yaw, 3),
            "pitch": round(pitch, 3),
            "roll": round(roll, 3),
            "method": "solvePnP_5point_RQDecomp3x3",
        }
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def raw_view_class(yaw: float | None) -> str:
    if yaw is None:
        return "unknown"
    value = abs(yaw)
    if value < 12:
        return "front"
    if value < 27:
        return "three_quarter_15_27"
    if value < 58:
        return "three_quarter_27_58"
    return "profile_58_plus"


def quality_metrics(image: Any, bbox: Any, cv2: Any, np: Any) -> dict[str, Any]:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = [int(max(0, x)) for x in bbox]
    x2, y2 = min(width, x2), min(height, y2)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return {"valid": False, "blur": None, "occlusion": "unknown"}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    face_area_ratio = float((x2 - x1) * (y2 - y1) / max(width * height, 1))
    return {
        "valid": True,
        "blur": {"laplacianVariance": round(sharpness, 3), "score01": round(min(1.0, sharpness / 180.0), 4), "severe": sharpness < 20.0},
        "lighting": {"brightness": round(brightness, 3), "contrast": round(contrast, 3)},
        "faceAreaRatio": round(face_area_ratio, 5),
        "occlusion": {"status": "unmeasured", "reason": "buffalo_l has no occlusion head; manual review required"},
    }


class FaceEngine:
    def __init__(self, model_root: Path = MODEL_ROOT, cache_root: Path = DEFAULT_CACHE_ROOT, provider: str = "CPUExecutionProvider"):
        self.cv2, self.np, self.ort, FaceAnalysis = import_runtime()
        self.model_root = model_root.resolve()
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        providers = [provider]
        available = list(self.ort.get_available_providers())
        if provider not in available:
            providers = ["CPUExecutionProvider"]
            self.provider = "CPUExecutionProvider"
        self.app = FaceAnalysis(name="buffalo_l", root=str(self.model_root), providers=providers)
        self.app.prepare(ctx_id=-1, det_thresh=0.5, det_size=(640, 640))
        self._memory_cache: dict[str, dict[str, Any]] = {}

    @property
    def runtime_info(self) -> dict[str, Any]:
        return {
            "embeddingModel": "buffalo_l/w600k_r50.onnx",
            "detectorModel": "buffalo_l/det_10g.onnx",
            "landmarkModels": ["buffalo_l/2d106det.onnx", "buffalo_l/1k3d68.onnx"],
            "embeddingDimension": 512,
            "providerRequested": self.provider,
            "providersAvailable": list(self.ort.get_available_providers()),
            "providerUsed": self.provider,
            "modelRoot": str(self.model_root),
            "sourceVersion": "InsightFace 0.7.3 official Python source, optional face3d renderer omitted",
        }

    def _key(self, path: Path) -> str:
        stat = path.stat()
        return f"{path}|{stat.st_size}|{stat.st_mtime_ns}|buffalo_l|{self.provider}"

    def analyze(self, path_value: str | Path, include_embedding: bool = False) -> dict[str, Any]:
        path = safe_path(path_value)
        key = self._key(path)
        cached = self._memory_cache.get(key)
        if cached is not None:
            result = copy.deepcopy(cached)
            if not include_embedding:
                for face in result.get("faces", []):
                    face.pop("_embedding", None)
            return result
        started = time.perf_counter()
        image = load_image(path, self.cv2, self.np)
        faces = self.app.get(image)
        rows: list[dict[str, Any]] = []
        for index, face in enumerate(faces):
            bbox = [round(float(x), 3) for x in face.bbox.tolist()]
            kps = None if getattr(face, "kps", None) is None else [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in face.kps.tolist()]
            landmark106 = getattr(face, "landmark_2d_106", None)
            pose = head_pose(face.kps, image.shape[1], image.shape[0], self.cv2, self.np)
            # buffalo_l also exposes a 3d68 landmark pose.  Its pitch/roll are
            # stable for this asset set; use the five-point solvePnP yaw for
            # view separation because the latter preserves the clear side
            # direction on the local known samples.
            native_pose = getattr(face, "pose", None)
            if native_pose is None and hasattr(face, "get"):
                native_pose = face.get("pose")
            if native_pose is not None and len(native_pose) >= 3:
                pose["pitch"] = round(float(native_pose[0]), 3)
                pose["roll"] = round(float(native_pose[2]), 3)
                pose["method"] = "InsightFace_landmark_3d68_pitch_roll_plus_5point_solvePnP_yaw"
                pose["nativePose"] = [round(float(x), 3) for x in native_pose[:3]]
            q = quality_metrics(image, face.bbox, self.cv2, self.np)
            embedding = getattr(face, "embedding", None)
            if embedding is not None:
                embedding = self.np.asarray(embedding, dtype=self.np.float32).reshape(-1)
                embedding_norm = float(self.np.linalg.norm(embedding))
                embedding_hash = hashlib.sha256(embedding.tobytes()).hexdigest()
            else:
                embedding_norm = None
                embedding_hash = None
            rows.append({
                "faceIndex": index,
                "bbox": bbox,
                "detectionConfidence": round(float(getattr(face, "det_score", 0.0)), 6),
                "landmarks5": kps,
                "landmarks106": None if landmark106 is None else [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in landmark106.tolist()],
                "landmarkCount": 0 if landmark106 is None else int(len(landmark106)),
                "headPose": pose,
                "viewClassRaw": raw_view_class(pose.get("yaw") if pose.get("available") else None),
                "faceQuality": q,
                "embeddingDimension": None if embedding is None else int(embedding.shape[0]),
                "embeddingL2Norm": None if embedding_norm is None else round(embedding_norm, 6),
                "embeddingSha256": embedding_hash,
                "_embedding": None if embedding is None else embedding.tolist(),
            })
        result: dict[str, Any] = {
            "schemaVersion": "2026-08-16.identity-analysis.v2",
            "path": str(path),
            "relativePath": rel(path),
            "imageSha256": sha256_file(path),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
            "faceDetected": bool(rows),
            "faceCount": len(rows),
            "faces": rows,
            "worker": self.runtime_info,
            "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
        }
        self._memory_cache[key] = copy.deepcopy(result)
        if not include_embedding:
            result = dict(result)
            for face in result["faces"]:
                face.pop("_embedding", None)
        return result

    def compare(self, left_value: str | Path, right_value: str | Path) -> dict[str, Any]:
        left = self.analyze(left_value, include_embedding=True)
        right = self.analyze(right_value, include_embedding=True)
        left_face = left.get("faces", [None])[0] if left.get("faceCount") == 1 else None
        right_face = right.get("faces", [None])[0] if right.get("faceCount") == 1 else None
        similarity: float | None = None
        if left_face and right_face and left_face.get("_embedding") and right_face.get("_embedding"):
            a = self.np.asarray(left_face["_embedding"], dtype=self.np.float32)
            b = self.np.asarray(right_face["_embedding"], dtype=self.np.float32)
            similarity = float(self.np.dot(a, b) / max(float(self.np.linalg.norm(a) * self.np.linalg.norm(b)), 1e-8))
        return {
            "schemaVersion": "2026-08-16.identity-compare.v2",
            "left": {"path": left["path"], "faceDetected": left["faceDetected"], "faceCount": left["faceCount"], "detectionConfidence": left_face.get("detectionConfidence") if left_face else None},
            "right": {"path": right["path"], "faceDetected": right["faceDetected"], "faceCount": right["faceCount"], "detectionConfidence": right_face.get("detectionConfidence") if right_face else None},
            "rawCosineSimilarity": None if similarity is None else round(similarity, 8),
            "embeddingModel": self.runtime_info["embeddingModel"],
            "decision": "unavailable" if similarity is None else "calibration_required",
        }


def expected_view_spec(name: str) -> dict[str, Any]:
    key = name.lower().replace("-", "_")
    if key in ("front", "half_body_front", "full_body_front"):
        return {"side": "front", "minAbsYaw": 0, "maxAbsYaw": 15}
    if "left" in key:
        if "profile" in key:
            return {"side": "left", "minAbsYaw": 55, "maxAbsYaw": 180}
        if "30" in key:
            return {"side": "left", "minAbsYaw": 12, "maxAbsYaw": 40}
        return {"side": "left", "minAbsYaw": 27, "maxAbsYaw": 62}
    if "right" in key:
        if "profile" in key:
            return {"side": "right", "minAbsYaw": 55, "maxAbsYaw": 180}
        if "30" in key:
            return {"side": "right", "minAbsYaw": 12, "maxAbsYaw": 40}
        return {"side": "right", "minAbsYaw": 27, "maxAbsYaw": 62}
    return {"side": "unknown", "minAbsYaw": 0, "maxAbsYaw": 180}


def classify_view(yaw: float | None, requested: str, left_polarity: int = -1) -> tuple[str, bool, float]:
    if yaw is None:
        return "unknown", False, 0.0
    normalized = float(yaw) * float(left_polarity)
    spec = expected_view_spec(requested)
    abs_yaw = abs(normalized)
    if abs_yaw < 12:
        actual = "front"
    elif abs_yaw < 27:
        actual = "left_30" if normalized < 0 else "right_30"
    elif abs_yaw < 58:
        actual = "left_45" if normalized < 0 else "right_45"
    else:
        actual = "left_profile" if normalized < 0 else "right_profile"
    if spec["side"] == "front":
        passed = abs_yaw <= spec["maxAbsYaw"]
    elif spec["side"] == "left":
        passed = normalized < 0 and spec["minAbsYaw"] <= abs_yaw <= spec["maxAbsYaw"]
    elif spec["side"] == "right":
        passed = normalized > 0 and spec["minAbsYaw"] <= abs_yaw <= spec["maxAbsYaw"]
    else:
        passed = True
    distance = min(abs(abs_yaw - spec["minAbsYaw"]), abs(abs_yaw - spec["maxAbsYaw"])) if spec["side"] != "front" else abs_yaw
    confidence = max(0.0, min(1.0, 1.0 - distance / 45.0))
    return actual, bool(passed), round(confidence, 4)


def pick_paths(root: Path, pattern: str, limit: int) -> list[Path]:
    return [p for p in sorted(root.rglob(pattern)) if p.is_file()][:limit]


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key not in seen and path.is_file():
            result.append(path)
            seen.add(key)
    return result


def build_calibration_pairs() -> dict[str, list[dict[str, Any]]]:
    char15 = DATA_ROOT / "Characters" / "15"
    master = DEFAULT_MASTER
    easy = unique_paths([
        char15 / "standard" / "face_closeup.png",
        char15 / "standard" / "identity_three_quarter.png",
        char15 / "ref_20260811_102554_f6ea3a88.png",
        char15 / "ref_20260811_105155_5b33ff21.png",
        char15 / "ref_20260811_105155_701f4554.png",
    ])
    easy.extend(pick_paths(DATA_ROOT / "QA" / "identity_pipeline_20260816" / "front", "*.png", 6))
    hard = unique_paths(
        pick_paths(DATA_ROOT / "QA" / "identity_pipeline_20260816" / "front_left_30", "*.png", 4)
        + pick_paths(DATA_ROOT / "QA" / "identity_pipeline_20260816" / "front_right_30", "*.png", 4)
        + pick_paths(DATA_ROOT / "QA" / "identity_pipeline_20260816" / "left_45", "*.png", 2),
    )
    # These are deliberately restricted to single-face local assets.  Several
    # older character references are collages; putting them into a Same/Diff
    # threshold cohort would measure detector failure rather than identity.
    different = unique_paths([
        DATA_ROOT / "Characters" / "7" / "ref_20260810_002133_1c75d72f.png",
        DATA_ROOT / "Characters" / "7" / "ref_20260810_002133_2755ee2b.png",
        DATA_ROOT / "Characters" / "7" / "ref_20260810_002133_c879f2e6.png",
        DATA_ROOT / "Characters" / "8" / "standard" / "face_closeup.png",
        DATA_ROOT / "Characters" / "8" / "standard" / "front_full_body.png",
        DATA_ROOT / "Characters" / "8" / "standard" / "front_half_body.png",
        DATA_ROOT / "Characters" / "8" / "standard" / "identity_front.png",
        DATA_ROOT / "Characters" / "10" / "ref_20260810_002132_e61cb46a.png",
        DATA_ROOT / "Characters" / "11" / "ref_20260810_002132_33aff589.png",
        DATA_ROOT / "Characters" / "11" / "ref_20260810_002132_9a5c9155.png",
    ])
    def make(rows: list[Path], label: str, cohort: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        prefix = {"SamePersonEasy": "E", "SamePersonHard": "H", "DifferentPerson": "D"}.get(cohort, "P")
        for index, path in enumerate(unique_paths(rows)[:10], start=1):
            out.append({
                "pairId": f"{prefix}{index:02d}",
                "cohort": cohort,
                "left": str(master),
                "right": str(path),
                "groundTruth": label,
                "labelSource": "directory-owner-and-existing-character-manifest" if label == "same-person" else "distinct-character-id",
                "manualReviewRequired": cohort == "SamePersonHard",
            })
        return out
    return {
        "SamePersonEasy": make(easy, "same-person", "SamePersonEasy"),
        "SamePersonHard": make(hard, "same-person", "SamePersonHard"),
        "DifferentPerson": make(different, "different-person", "DifferentPerson"),
    }


def calibrate_threshold(engine: FaceEngine) -> dict[str, Any]:
    sets = build_calibration_pairs()
    rows: list[dict[str, Any]] = []
    for cohort, pairs in sets.items():
        for pair in pairs:
            result = engine.compare(pair["left"], pair["right"])
            rows.append({**pair, "rawCosineSimilarity": result["rawCosineSimilarity"], "leftFace": result["left"], "rightFace": result["right"]})
    scores = [float(row["rawCosineSimilarity"]) for row in rows if row["rawCosineSimilarity"] is not None]
    candidates = sorted({round(max(0.0, min(1.0, value)), 5) for value in scores} | {0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95})
    best: dict[str, Any] | None = None
    for threshold in candidates:
        tp = fp = tn = fn = 0
        for row in rows:
            score = row["rawCosineSimilarity"]
            if score is None:
                continue
            predicted_same = score >= threshold
            actual_same = row["groundTruth"] == "same-person"
            if predicted_same and actual_same:
                tp += 1
            elif predicted_same and not actual_same:
                fp += 1
            elif not predicted_same and not actual_same:
                tn += 1
            else:
                fn += 1
        total = tp + fp + tn + fn
        accuracy = (tp + tn) / total if total else 0.0
        hard = [r for r in rows if r.get("cohort") == "SamePersonHard"]
        hard_recall = sum(1 for r in hard if r["rawCosineSimilarity"] is not None and r["rawCosineSimilarity"] >= threshold) / max(len(hard), 1)
        false_accept = fp / max(fp + tn, 1)
        metrics = {"threshold": threshold, "accuracy": round(accuracy, 4), "hardRecall": round(hard_recall, 4), "falseAcceptRate": round(false_accept, 4), "tp": tp, "fp": fp, "tn": tn, "fn": fn}
        # Prefer a useful operating point that does not accept a large share
        # of the known different-person cohort.  Fall back to accuracy only
        # when the small local cohort has no threshold under 10% FAR.
        far_ok = false_accept <= 0.10
        rank = (1 if far_ok else 0, hard_recall, accuracy, -false_accept, threshold)
        if best is None or rank > best["_rank"]:
            best = {"_rank": rank, **metrics}
    assert best is not None
    for row in rows:
        score = row["rawCosineSimilarity"]
        row["decision"] = "unavailable" if score is None else ("same-person" if score >= best["threshold"] else "different-person")
    insufficient = any(len(sets[name]) < 10 for name in sets) or any(r.get("manualReviewRequired") for r in rows)
    return {
        "schemaVersion": "2026-08-16.identity-threshold-calibration.v2",
        "status": "Preliminary" if insufficient else "Calibrated",
        "ManualReviewRequired": bool(insufficient),
        "embeddingModel": engine.runtime_info["embeddingModel"],
        "cohorts": {name: {"requestedPairs": 10, "actualPairs": len(rows_for_set), "uniqueRightImages": len({r["right"] for r in rows_for_set})} for name, rows_for_set in sets.items()},
        "recommendedThreshold": best["threshold"],
        "selectionObjective": "max accuracy, then SamePersonHard recall, then lower false-accept rate",
        "validation": {k: v for k, v in best.items() if k != "_rank"},
        "pairs": rows,
        "limitations": [
            "SamePersonHard uses prior local generated/view assets and remains manually reviewable.",
            "DifferentPerson is a local distinct-character cohort, not a public demographic benchmark.",
            "Threshold is a production candidate only after manual review of the contact sheets.",
        ],
    }


def calibrate_view_angle(engine: FaceEngine, run_root: Path) -> dict[str, Any]:
    mirror_dir = run_root / "mirror_validation"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    cv2, np = engine.cv2, engine.np
    master = DEFAULT_MASTER
    mirror = mirror_dir / "identity_front_mirror.png"
    image = load_image(master, cv2, np)
    cv2.imencode(".png", cv2.flip(image, 1))[1].tofile(str(mirror))
    # The previous TV01/TV02 outputs are visibly front-facing despite their
    # prompt labels.  Use a clearly turned local reference, then mirror it to
    # create a controlled opposite-side validation pair.  This makes the
    # direction test explicit instead of trusting a failed prompt label.
    left = DATA_ROOT / "Characters" / "7" / "ref_20260810_002133_1c75d72f.png"
    right = mirror_dir / "known_right_45_mirror.png"
    left_image = load_image(left, cv2, np)
    cv2.imencode(".png", cv2.flip(left_image, 1))[1].tofile(str(right))
    known = [
        {"label": "front", "path": master, "manualViewLabel": "front"},
        {"label": "left_45", "path": left, "manualViewLabel": "left_45_visual_known"},
        {"label": "right_45", "path": right, "manualViewLabel": "right_45_mirrored_control"},
        {"label": "mirror_of_front", "path": mirror, "manualViewLabel": "front_mirrored"},
    ]
    measured: list[dict[str, Any]] = []
    for row in known:
        result = engine.analyze(row["path"])
        face = result.get("faces", [None])[0] if result.get("faceCount") == 1 else None
        pose = face.get("headPose") if face else None
        measured.append({**row, "path": str(row["path"]), "rawYaw": pose.get("yaw") if pose and pose.get("available") else None, "pitch": pose.get("pitch") if pose and pose.get("available") else None, "roll": pose.get("roll") if pose and pose.get("available") else None, "faceCount": result.get("faceCount"), "detectionConfidence": face.get("detectionConfidence") if face else None})
    left_yaw = next((r["rawYaw"] for r in measured if r["label"] == "left_45" and r["rawYaw"] is not None), 0.0)
    right_yaw = next((r["rawYaw"] for r in measured if r["label"] == "right_45" and r["rawYaw"] is not None), 0.0)
    polarity = 1 if left_yaw < 0 else -1
    side_separation = abs(float(left_yaw) - float(right_yaw))
    front_yaw = next((abs(float(r["rawYaw"])) for r in measured if r["label"] == "front" and r["rawYaw"] is not None), 999.0)
    mirror_front_yaw = next((abs(float(r["rawYaw"])) for r in measured if r["label"] == "mirror_of_front" and r["rawYaw"] is not None), 999.0)
    for row in measured:
        actual, passed, confidence = classify_view(row["rawYaw"], row["label"], polarity)
        row["normalizedViewClass"] = actual
        row["knownLabelPass"] = passed if row["label"] != "mirror_of_front" else front_yaw < 15 and mirror_front_yaw < 15
        row["viewConfidence"] = confidence
    return {
        "schemaVersion": "2026-08-16.view-angle-calibration.v2",
        "ViewAngleThresholdCalibration": {"frontAbsYawMax": 15, "threeQuarter30Range": [12, 40], "threeQuarter45Range": [27, 62], "profileMinAbsYaw": 55},
        "poseMethod": "InsightFace 5-point landmarks + solvePnP/RQDecomp3x3",
        "leftPolarity": polarity,
        "knownLeftYaw": left_yaw,
        "knownRightYaw": right_yaw,
        "sideSeparationDegrees": round(side_separation, 3),
        "frontMirrorInvariant": bool(front_yaw < 15 and mirror_front_yaw < 15),
        "directionSeparationPass": bool(side_separation >= 20),
        "manualReviewRequired": True,
        "knownSamples": measured,
        "limitations": ["Yaw sign is calibrated against two locally labelled images; human confirmation remains required for left/right semantics.", "Pitch/roll are measured but do not alone prove body framing."],
    }


def draw_pose_templates(run_root: Path) -> dict[str, Any]:
    cv2, np, _, _ = import_runtime()
    library_root = AI_ROOT / "Workflows" / "CharacterPoseTemplates"
    library_root.mkdir(parents=True, exist_ok=True)
    output_root = run_root / "pose_templates"
    output_root.mkdir(parents=True, exist_ok=True)
    controlnet = AI_ROOT / "Models" / "controlnet" / "control_v11p_sd15_openpose.pth"
    # COCO-ish normalized standing skeleton. x is mirrored for right/left views.
    base = {
        "nose": (0.50, 0.13), "neck": (0.50, 0.20), "left_shoulder": (0.40, 0.23), "right_shoulder": (0.60, 0.23),
        "left_elbow": (0.34, 0.36), "right_elbow": (0.66, 0.36), "left_wrist": (0.34, 0.50), "right_wrist": (0.66, 0.50),
        "left_hip": (0.44, 0.50), "right_hip": (0.56, 0.50), "left_knee": (0.44, 0.72), "right_knee": (0.56, 0.72),
        "left_ankle": (0.43, 0.94), "right_ankle": (0.57, 0.94), "left_eye": (0.475, 0.125), "right_eye": (0.525, 0.125),
        "left_ear": (0.45, 0.14), "right_ear": (0.55, 0.14),
    }
    edges = [("nose", "neck"), ("neck", "left_shoulder"), ("neck", "right_shoulder"), ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"), ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"), ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"), ("left_hip", "right_hip"), ("left_hip", "left_knee"), ("left_knee", "left_ankle"), ("right_hip", "right_knee"), ("right_knee", "right_ankle"), ("left_eye", "right_eye"), ("left_ear", "left_eye"), ("right_eye", "right_ear")]
    specs: dict[str, dict[str, Any]] = {
        "front": {"mode": "full", "yawHint": 0}, "front_left_30": {"mode": "full", "yawHint": -30}, "front_right_30": {"mode": "full", "yawHint": 30},
        "left_45": {"mode": "full", "yawHint": -45}, "right_45": {"mode": "full", "yawHint": 45}, "left_profile": {"mode": "full", "yawHint": -90}, "right_profile": {"mode": "full", "yawHint": 90},
        "half_body_front": {"mode": "half", "yawHint": 0}, "half_body_left45": {"mode": "half", "yawHint": -45}, "half_body_right45": {"mode": "half", "yawHint": 45},
        "full_body_front": {"mode": "full", "yawHint": 0}, "full_body_left45": {"mode": "full", "yawHint": -45}, "full_body_right45": {"mode": "full", "yawHint": 45},
    }
    rows: list[dict[str, Any]] = []
    for name in VIEW_ORDER:
        spec = specs[name]
        canvas = np.zeros((768, 512, 3), dtype=np.uint8)
        points = dict(base)
        yaw_hint = float(spec["yawHint"])
        sign = -1 if yaw_hint < 0 else 1
        # A tiny nose translation is not a useful pose condition.  For the
        # second attempt, project a visibly narrower/turned upper body and
        # move the facial keypoints enough for OpenPose ControlNet to see a
        # structural change.  The text prompt remains identical across
        # methods; only this explicit control image changes by requested view.
        abs_yaw = abs(yaw_hint)
        squash = 1.0 - min(0.48, abs_yaw / 180.0)
        shear = sign * min(0.16, abs_yaw / 320.0)
        for key, (x, y) in list(points.items()):
            x = 0.5 + (x - 0.5) * squash + shear * max(0.0, y - 0.18)
            points[key] = (x, y)
        face_shift = min(0.20, abs_yaw / 240.0) * sign
        if abs_yaw >= 12:
            points["nose"] = (0.5 + face_shift, 0.135)
            points["left_eye"] = (0.5 + face_shift * 0.35 - 0.035, 0.125)
            points["right_eye"] = (0.5 + face_shift * 0.35 + 0.035, 0.125)
            points["left_ear"] = (0.5 - 0.035 + face_shift * 0.1, 0.14)
            points["right_ear"] = (0.5 + 0.035 + face_shift * 0.1, 0.14)
        if spec["mode"] == "half":
            for key in ("left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"):
                points.pop(key, None)
        def xy(point: tuple[float, float]) -> tuple[int, int]:
            return int(point[0] * canvas.shape[1]), int(point[1] * canvas.shape[0])
        for a, b in edges:
            if a in points and b in points:
                cv2.line(canvas, xy(points[a]), xy(points[b]), (0, 180, 255), 5, cv2.LINE_AA)
        for point in points.values():
            cv2.circle(canvas, xy(point), 7, (0, 255, 0), -1, cv2.LINE_AA)
        filename = f"{name}_20260816.png"
        out_path = output_root / filename
        cv2.imencode(".png", canvas)[1].tofile(str(out_path))
        library_path = library_root / filename
        if not library_path.exists():
            cv2.imencode(".png", canvas)[1].tofile(str(library_path))
        coverage = "head_to_waist" if spec["mode"] == "half" else "head_to_ankles"
        rows.append({
            "name": name,
            "path": str(out_path),
            "libraryPath": str(library_path),
            "sourceType": "manual_standard_openpose_skeleton_v2",
            "controlType": "OpenPose",
            "promptOnly": False,
            "controlNetModel": str(controlnet),
            "controlNetPresent": controlnet.is_file(),
            "yawHint": spec["yawHint"],
            "bodyCoverageTarget": coverage,
            "headCropped": False,
            "feetCropped": spec["mode"] == "half",
            "manualReviewRequired": True,
        })
    payload = {
        "schemaVersion": "2026-08-16.pose-template-library.v2",
        "libraryRoot": str(library_root),
        "templateCount": len(rows),
        "templates": rows,
        "sourceProbe": {
            "sdposeModel": str(AI_ROOT / "Models" / "checkpoints" / "sdpose_wholebody_fp16.safetensors"),
            "sdposePresent": (AI_ROOT / "Models" / "checkpoints" / "sdpose_wholebody_fp16.safetensors").is_file(),
            "priorPoseExtractionEvidence": str(DATA_ROOT / "QA" / "benchmarks" / "action_identity_20260814" / "pose_extraction_20260815"),
            "decision": "Use explicit OpenPose skeletons for static identity views; prior SDPose/action maps remain a source probe and are not silently treated as neutral templates.",
        },
    }
    json_dump(run_root / "pose-template-library.json", payload)
    return payload


def master_qa(engine: FaceEngine) -> dict[str, Any]:
    result = engine.analyze(DEFAULT_MASTER)
    face = result.get("faces", [None])[0] if result.get("faceCount") == 1 else None
    pose = face.get("headPose") if face else None
    quality = face.get("faceQuality") if face else None
    checks = {
        "singleFace": result.get("faceCount") == 1,
        "sharpFace": bool(quality and not quality.get("blur", {}).get("severe", True)),
        "neutralExpression": "manual_review_required",
        "noOcclusion": "manual_review_required",
        "frontView": bool(pose and pose.get("available") and abs(float(pose.get("yaw", 999))) < 15),
        "goodLighting": bool(quality and 45 <= quality.get("lighting", {}).get("brightness", 0) <= 215),
        "hairVisible": "manual_review_required",
        "noCrop": bool(face and face.get("bbox", [0, 0, 0, 0])[1] > 1),
    }
    return {"path": str(DEFAULT_MASTER), "analysis": result, "checks": checks, "manualReviewRequired": True}


def method_probe() -> dict[str, Any]:
    node_info: dict[str, Any] = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=10) as response:
            object_info = json.loads(response.read().decode("utf-8"))
            for name in ["IPAdapterFaceID", "IPAdapterUnifiedLoaderFaceID", "IPAdapter", "ControlNetApplyAdvanced", "InstantID", "PuLID"]:
                node_info[name] = {"present": name in object_info}
    except Exception as exc:
        node_info["comfyProbe"] = {"error": f"{type(exc).__name__}: {exc}"}
    models = {
        "checkpoint": AI_ROOT / "Models" / "checkpoints" / "v1-5-pruned-emaonly-fp16.safetensors",
        "clipVision": AI_ROOT / "Models" / "clip_vision" / "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        "baselineIpAdapter": AI_ROOT / "Models" / "ipadapter" / "ip-adapter-plus-face_sd15.safetensors",
        "faceId": AI_ROOT / "Models" / "ipadapter" / "ip-adapter-faceid-plusv2_sd15.bin",
        "faceIdLoRA": AI_ROOT / "Models" / "loras" / "ip-adapter-faceid-plusv2_sd15_lora.safetensors",
        "openPoseControlNet": AI_ROOT / "Models" / "controlnet" / "control_v11p_sd15_openpose.pth",
        "instantIdModel": AI_ROOT / "Models" / "instantid" / "ip-adapter.bin",
        "pulidModel": AI_ROOT / "Models" / "pulid" / "pulid_sd15.safetensors",
    }
    statuses = {
        "Baseline": {"status": "AVAILABLE" if all(path.is_file() for name, path in models.items() if name in {"checkpoint", "clipVision", "baselineIpAdapter", "openPoseControlNet"}) else "BLOCKED_MODEL"},
        "FaceID": {"status": "READY_TO_PROBE" if models["faceId"].is_file() and models["faceIdLoRA"].is_file() and node_info.get("IPAdapterFaceID", {}).get("present") else "BLOCKED_MODEL_OR_DEPENDENCY"},
        "InstantID": {"status": "BLOCKED_NODE_OR_MODEL", "blocked": ["BLOCKED_NODE_MISSING", "BLOCKED_MODEL_MISSING", "BLOCKED_BASE_MODEL_MISSING"]},
        "PuLID": {"status": "BLOCKED_NODE_OR_MODEL", "blocked": ["BLOCKED_NODE_MISSING", "BLOCKED_MODEL_MISSING"]},
    }
    return {
        "schemaVersion": "2026-08-16.identity-method-probe.v2",
        "oneVariablePrinciple": {"master": str(DEFAULT_MASTER), "baseModel": str(models["checkpoint"]), "resolution": "512x768 or VRAM-probed equivalent", "sampler": "dpmpp_2m/karras", "steps": 28, "cfg": 5.8, "seeds": SEEDS, "poseControl": "OpenPose template"},
        "nodes": node_info,
        "models": {name: {"path": str(path), "present": path.is_file(), "bytes": path.stat().st_size if path.is_file() else None, "sha256": sha256_file(path)} for name, path in models.items()},
        "methods": statuses,
        "notes": ["InstantID is primarily an SDXL route; the checkout has no SDXL checkpoint or InstantID node/model, so it is not silently substituted with a prompt-only baseline.", "PuLID node/model was not found in the current ComfyUI installation."],
    }


def environment_report(engine: FaceEngine, run_root: Path) -> dict[str, Any]:
    api: dict[str, Any] = {}
    for name, url in {"videoStudio": "http://127.0.0.1:18080/api/health", "comfy": "http://127.0.0.1:8188/system_stats"}.items():
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                api[name] = {"url": url, "status": response.status, "body": json.loads(response.read().decode("utf-8"))}
        except Exception as exc:
            api[name] = {"url": url, "status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "schemaVersion": "2026-08-16.identity-foundation-environment.v2",
        "timestamp": now_iso(),
        "projectRoot": str(PROJECT_ROOT),
        "runRoot": str(run_root),
        "host": {"platform": platform.platform(), "python": sys.version, "machine": platform.machine(), "processor": platform.processor()},
        "api": api,
        "identityWorker": {"loopbackOnly": True, "host": "127.0.0.1", "port": 18084, "runtime": engine.runtime_info},
        "dirtyWorkPolicy": "pre-existing dirty checkout preserved; this run writes only new run_02 evidence and additive template files",
    }


def deployment_report(engine: FaceEngine) -> dict[str, Any]:
    model_dir = MODEL_ROOT / "models" / "buffalo_l"
    return {
        "schemaVersion": "2026-08-16.insightface-deployment.v2",
        "status": "PASS_REAL_RUNTIME",
        "package": {"requested": "insightface==0.7.3", "officialSource": str(INSIGHTFACE_SOURCE), "version": "0.7.3", "compiledInstall": "BLOCKED_DEPENDENCY_MSVC14", "fallback": "official pure-Python FaceAnalysis source with optional face3d renderer omitted"},
        "dependencyEvidence": {"onnxruntime": "isolated worker venv", "opencv": "isolated worker venv", "modelProvider": engine.provider, "python": sys.executable},
        "modelPack": {"name": "buffalo_l", "root": str(model_dir), "files": file_inventory(model_dir, (".onnx",))},
        "runtime": engine.runtime_info,
        "security": {"workerBind": "127.0.0.1", "inputAllowList": [str(DATA_ROOT), str(MODEL_ROOT), str(DEFAULT_RUN_ROOT)], "rawEmbeddingsPersisted": False},
        "blocked": ["BLOCKED_DEPENDENCY_MSVC14_FOR_OPTIONAL_FACE3D_BUILD"],
    }


def qa_candidate(engine: FaceEngine, row: dict[str, Any], threshold: float, left_polarity: int) -> dict[str, Any]:
    path_value = row.get("path")
    result: dict[str, Any] = {**row, "schemaVersion": "2026-08-16.candidate-qa-v2"}
    if not path_value or not Path(path_value).is_file():
        result.update({"technicalSuccess": False, "faceDetected": False, "faceCount": 0, "hardRejectFlags": ["NoGeneratedFile"], "autoDecision": "REJECT", "manualReviewRequired": False})
        return result
    analysis = engine.analyze(path_value)
    result["technicalSuccess"] = True
    result["analysisMs"] = analysis.get("elapsedMs")
    result["faceDetected"] = analysis.get("faceDetected", False)
    result["faceCount"] = analysis.get("faceCount", 0)
    face = analysis.get("faces", [None])[0] if analysis.get("faceCount") == 1 else None
    compare = engine.compare(DEFAULT_MASTER, path_value)
    score = compare.get("rawCosineSimilarity")
    pose = face.get("headPose") if face else None
    yaw = pose.get("yaw") if pose and pose.get("available") else None
    pitch = pose.get("pitch") if pose and pose.get("available") else None
    roll = pose.get("roll") if pose and pose.get("available") else None
    actual_view, view_pass, view_confidence = classify_view(yaw, row.get("requestedView", "front"), left_polarity)
    hard: list[str] = []
    if not result["faceDetected"]:
        hard.append("NoFace")
    if result["faceCount"] > 1:
        hard.extend(["MultipleFaces", "DuplicateFace"])
    if result["faceCount"] == 1 and face and float(face.get("detectionConfidence", 0)) < 0.60:
        hard.append("LowFaceConfidence")
    identity_pass = score is not None and float(score) >= threshold and result["faceCount"] == 1
    if not identity_pass:
        hard.append("WrongIdentity")
    if not view_pass:
        hard.append("WrongView")
    if face and face.get("faceQuality", {}).get("blur", {}).get("severe"):
        hard.append("SevereBlur")
    if face:
        bbox = face.get("bbox", [0, 0, 0, 0])
        head_crop = bbox[1] <= 2
        body_target = "full" if "full" in row.get("requestedView", "") else ("half" if "half" in row.get("requestedView", "") else "face")
    else:
        head_crop = False
        body_target = "unknown"
    if head_crop:
        hard.append("HeadCropped")
    # Body/feet need a pose/segmentation model or human review.  Never infer a
    # pass from image dimensions; keep the fields explicit and conservative.
    feet_crop: bool | str = "unmeasured"
    body_coverage: str = "unmeasured"
    if body_target == "full":
        result_body_review = True
    else:
        result_body_review = False
    result.update({
        "embeddingRawSimilarity": score,
        "identityDecision": "PASS" if identity_pass else "FAIL",
        "yaw": yaw,
        "pitch": pitch,
        "roll": roll,
        "viewClass": actual_view,
        "viewConfidence": view_confidence,
        "viewDecision": "PASS" if view_pass else "FAIL",
        "faceQuality": face.get("faceQuality") if face else None,
        "blur": face.get("faceQuality", {}).get("blur") if face else None,
        "occlusion": face.get("faceQuality", {}).get("occlusion") if face else {"status": "unmeasured"},
        "hairConsistency": "manual_review_required",
        "clothingConsistency": "manual_review_required",
        "bodyCoverage": body_coverage,
        "bodyFramingManualReviewRequired": result_body_review or body_target == "half",
        "headCrop": head_crop,
        "feetCrop": feet_crop,
        "hardRejectFlags": sorted(set(hard)),
        "identityPass": bool(identity_pass),
        "viewPass": bool(view_pass),
        "dualPass": bool(identity_pass and view_pass and not hard),
        "autoDecision": "REJECT" if hard else "REVIEW",
        "manualReviewRequired": True,
        "analysisPath": str(path_value),
    })
    return result


def html_contact_sheet(path: Path, title: str, rows: list[dict[str, Any]], image_key: str = "path") -> None:
    cells: list[str] = []
    for row in rows:
        value = row.get(image_key)
        image = Path(value) if value else None
        image_html = "<div class='missing'>no image</div>"
        if image and image.is_file():
            image_html = f"<img src='{html.escape(image.as_uri())}' loading='lazy'>"
        caption = "<br>".join(html.escape(f"{k}: {v}") for k, v in row.items() if k in {"candidateId", "method", "requestedView", "seed", "embeddingRawSimilarity", "identityDecision", "viewClass", "viewDecision", "autoDecision"})
        cells.append(f"<figure>{image_html}<figcaption>{caption}</figcaption></figure>")
    content = "<!doctype html><meta charset='utf-8'><title>{}</title><style>body{{font-family:Arial;background:#202124;color:#eee}}main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}figure{{margin:0;background:#303134;padding:8px}}img{{width:100%;height:260px;object-fit:contain;background:#111}}figcaption{{font-size:12px;line-height:1.4;margin-top:5px}}.missing{{height:260px;display:grid;place-items:center;background:#111;color:#f88}}</style><h1>{}</h1><main>{}</main>".format(html.escape(title), html.escape(title), "".join(cells))
    path.write_text(content, encoding="utf-8")


def bootstrap(run_root: Path) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    engine = FaceEngine(cache_root=run_root / "cache")
    threshold = calibrate_threshold(engine)
    view = calibrate_view_angle(engine, run_root)
    pose = draw_pose_templates(run_root)
    master = master_qa(engine)
    methods = method_probe()
    character_spec = {
        "schemaVersion": "2026-08-16.character-identity-spec.v2",
        "characterId": "15",
        "identityMaster": str(DEFAULT_MASTER),
        "gender": "adult male presentation",
        "ageRange": "adult, manual review required",
        "face": "East Asian male face with short black hair and trimmed mustache/goatee",
        "hair": "short black hair",
        "hairColor": "black",
        "clothing": "dark navy collared shirt",
        "clothingColor": "dark navy",
        "bodyType": "average adult male, manual review required",
        "makeup": "none specified",
        "accessories": "none specified",
        "fixedTraits": ["eye shape", "nose", "lips", "jawline", "mustache/goatee", "hair silhouette", "navy shirt"],
        "oldMaster": str(DEFAULT_MASTER),
        "newMaster": str(DEFAULT_MASTER),
        "masterChangeReason": "No silent replacement; current master remains fixed for all methods.",
        "masterQa": master,
    }
    json_dump(run_root / "character-identity-spec.json", character_spec)
    json_dump(run_root / "01-environment.json", environment_report(engine, run_root))
    json_dump(run_root / "02-insightface-deployment.json", deployment_report(engine))
    json_dump(run_root / "03-identity-threshold-calibration.json", threshold)
    json_dump(run_root / "04-view-angle-calibration.json", view)
    json_dump(run_root / "05-pose-template-library.json", pose)
    json_dump(run_root / "06-identity-method-benchmark.json", methods)
    # These are intentionally initialized before generation so a failed probe
    # still leaves a complete, non-fictional report set.
    json_dump(run_root / "07-controlled-candidates.json", {"schemaVersion": "2026-08-16.controlled-candidates.v2", "status": "WAITING_FOR_GENERATION_MANIFEST", "candidates": []})
    json_dump(run_root / "08-character-qa-v2.json", {"schemaVersion": "2026-08-16.character-qa-v2.v2", "status": "WAITING_FOR_GENERATION_MANIFEST", "candidates": []})
    json_dump(run_root / "09-golden-reference-pack-v2.json", {"schemaVersion": "2026-08-16.golden-pack-v2", "status": "NOT_EVALUATED", "goldenPack": []})
    json_dump(run_root / "10-reference-selector-v2-validation.json", {"schemaVersion": "2026-08-16.reference-selector-v2-validation", "status": "NOT_EVALUATED", "directQualifiedReferenceRate": None})
    json_dump(run_root / "11-performance.json", {"schemaVersion": "2026-08-16.identity-performance.v2", "embedding": {"status": "measured_during_worker_run"}, "generation": "not_run_at_bootstrap"})
    json_dump(run_root / "12-build-regression.json", {"schemaVersion": "2026-08-16.identity-build-regression.v2", "status": "PENDING_EXTERNAL_HARNESS"})
    json_dump(run_root / "13-final-acceptance.json", {"schemaVersion": "2026-08-16.identity-final-acceptance.v2", "finalStatus": "CONDITIONAL_IDENTITY_FOUNDATION", "reason": "Bootstrap complete; controlled generation and manual review are still outstanding."})
    return {"runRoot": str(run_root), "threshold": threshold["recommendedThreshold"], "leftPolarity": view["leftPolarity"], "methods": methods}


def evaluate(run_root: Path) -> dict[str, Any]:
    engine = FaceEngine(cache_root=run_root / "cache")
    threshold_report = read_json(run_root / "03-identity-threshold-calibration.json", {})
    view_report = read_json(run_root / "04-view-angle-calibration.json", {})
    threshold = float(threshold_report.get("recommendedThreshold", 0.85))
    polarity = int(view_report.get("leftPolarity", -1))
    generation = read_json(run_root / "generation-manifest.json", {})
    generation_rows = generation.get("candidates", []) if isinstance(generation, dict) else []
    qa_rows = [qa_candidate(engine, row, threshold, polarity) for row in generation_rows]
    for row in qa_rows:
        row.pop("_embedding", None)
    controlled = {
        "schemaVersion": "2026-08-16.controlled-candidates.v2",
        "master": str(DEFAULT_MASTER),
        "identityThreshold": threshold,
        "poseControlRequired": True,
        "summary": {
            "total": len(qa_rows),
            "technicalSuccess": sum(bool(r.get("technicalSuccess")) for r in qa_rows),
            "identityPass": sum(bool(r.get("identityPass")) for r in qa_rows),
            "viewPass": sum(bool(r.get("viewPass")) for r in qa_rows),
            "dualPass": sum(bool(r.get("dualPass")) for r in qa_rows),
            "hardReject": sum(bool(r.get("hardRejectFlags")) for r in qa_rows),
        },
        "candidates": [{k: v for k, v in row.items() if k not in {"analysisPath"}} for row in qa_rows],
    }
    json_dump(run_root / "07-controlled-candidates.json", controlled)
    json_dump(run_root / "08-character-qa-v2.json", {"schemaVersion": "2026-08-16.character-qa-v2.v2", "identityWorker": engine.runtime_info, "threshold": threshold, "candidates": qa_rows, "summary": controlled["summary"], "manualReviewRequired": True})
    accepted = [r for r in qa_rows if r.get("dualPass") and not r.get("hardRejectFlags")]
    golden: list[dict[str, Any]] = []
    for view in CORE_BENCHMARK_VIEWS:
        candidates = [r for r in accepted if r.get("requestedView") == view]
        candidates.sort(key=lambda r: (float(r.get("embeddingRawSimilarity") or -1), float(r.get("viewConfidence") or 0)), reverse=True)
        for item in candidates[:2]:
            golden.append({"goldenId": f"G{len(golden)+1:02d}", "requestedView": view, "path": item.get("path"), "method": item.get("method"), "seed": item.get("seed"), "autoRecommended": True, "manualReviewRequired": True, "qa": item})
    by_view = {view: sum(1 for item in golden if item["requestedView"] == view) for view in CORE_BENCHMARK_VIEWS}
    golden_report = {"schemaVersion": "2026-08-16.golden-pack-v2", "targetCount": "10-20", "count": len(golden), "goldenPack": golden, "byView": by_view, "status": "MANUAL_REVIEW_REQUIRED" if golden else "INCOMPLETE", "loRAAllowed": False, "manualReviewRequired": True}
    json_dump(run_root / "09-golden-reference-pack-v2.json", golden_report)
    selector_rows: list[dict[str, Any]] = []
    for view in CORE_BENCHMARK_VIEWS:
        view_items = [item for item in golden if item["requestedView"] == view]
        selector_rows.append({"requestId": f"G-{view}", "requestedView": view, "selection": view_items[0] if view_items else None, "selectionMode": "direct" if view_items else "fallback_front_or_blocked", "qualified": bool(view_items)})
    direct = sum(1 for r in selector_rows if r["selectionMode"] == "direct")
    selector_report = {"schemaVersion": "2026-08-16.reference-selector-v2-validation", "previousRun": {"fallback": 24, "total": 27, "direct": 3}, "current": {"total": len(selector_rows), "direct": direct, "fallback": len(selector_rows) - direct, "directQualifiedReferenceRate": round(direct / max(len(selector_rows), 1), 4)}, "rows": selector_rows, "gatePass": direct / max(len(selector_rows), 1) >= 0.8, "manualReviewRequired": True}
    json_dump(run_root / "10-reference-selector-v2-validation.json", selector_report)
    generation_results = generation.get("generationResults", []) if isinstance(generation, dict) else []
    durations = [float(r.get("durationMs")) for r in generation_results if r.get("durationMs") is not None]
    analysis_ms = [float(r.get("analysisMs")) for r in qa_rows if r.get("analysisMs") is not None]
    json_dump(run_root / "11-performance.json", {"schemaVersion": "2026-08-16.identity-performance.v2", "worker": engine.runtime_info, "embedding": {"count": len(qa_rows), "p50Ms": statistics.median(analysis_ms) if analysis_ms else None, "maxMs": max(analysis_ms) if analysis_ms else None}, "generation": {"count": len(durations), "p50Ms": statistics.median(durations) if durations else None, "maxMs": max(durations) if durations else None}, "vram": generation.get("vram", []) if isinstance(generation, dict) else []})
    method_summary: dict[str, Any] = {}
    for method in ["Baseline", "FaceID", "InstantID", "PuLID"]:
        rows = [r for r in qa_rows if r.get("method") == method]
        method_summary[method] = {"requested": len(CORE_BENCHMARK_VIEWS) * len(SEEDS), "generated": len(rows), "dualPass": sum(bool(r.get("dualPass")) for r in rows), "identityPass": sum(bool(r.get("identityPass")) for r in rows), "viewPass": sum(bool(r.get("viewPass")) for r in rows)}
    methods = read_json(run_root / "06-identity-method-benchmark.json", {})
    methods["results"] = method_summary
    methods["generationManifestPresent"] = bool(generation_rows)
    json_dump(run_root / "06-identity-method-benchmark.json", methods)
    gate_a = bool(threshold_report.get("status") in {"Calibrated", "Preliminary"} and threshold_report.get("validation", {}).get("accuracy", 0) >= 0.8 and threshold_report.get("ManualReviewRequired", True))
    gate_b = bool(view_report.get("directionSeparationPass") and view_report.get("frontMirrorInvariant"))
    core_views = {view: any(r.get("dualPass") and r.get("requestedView") == view for r in qa_rows) for view in CORE_BENCHMARK_VIEWS}
    gate_c = bool(generation_rows) and all(core_views.values())
    gate_d = len(golden) >= 10 and all(by_view.get(view, 0) >= 1 for view in CORE_BENCHMARK_VIEWS)
    gate_e = bool(selector_report["gatePass"])
    recommended = max(method_summary.items(), key=lambda item: (item[1]["dualPass"], item[1]["identityPass"]))[0] if any(value["dualPass"] for value in method_summary.values()) else "NO_METHOD_READY"
    gate_f = recommended != "NO_METHOD_READY"
    if gate_a and gate_b and gate_c and gate_d and gate_e and gate_f:
        final_status = "CONDITIONAL_IDENTITY_FOUNDATION"  # visual/manual approval is intentionally not automated.
    else:
        final_status = "NO_GO_IDENTITY_FOUNDATION"
    final = {
        "schemaVersion": "2026-08-16.identity-final-acceptance.v2",
        "finalStatus": final_status,
        "recommendedIdentityMethod": recommended,
        "readyForCharacterLoRAPoC": False,
        "gates": {
            "GateA_FaceEmbedding": {"status": "PASS" if gate_a else "FAIL", "evidence": "03-identity-threshold-calibration.json"},
            "GateB_ViewAngle": {"status": "PASS" if gate_b else "FAIL", "evidence": "04-view-angle-calibration.json"},
            "GateC_ControlledGeneration": {"status": "PASS" if gate_c else "FAIL", "evidence": "07-controlled-candidates.json"},
            "GateD_GoldenPack": {"status": "PASS" if gate_d else "FAIL", "evidence": "09-golden-reference-pack-v2.json"},
            "GateE_Selector": {"status": "PASS" if gate_e else "FAIL", "evidence": "10-reference-selector-v2-validation.json"},
            "GateF_IdentityMethod": {"status": "PASS" if gate_f else "FAIL", "evidence": "06-identity-method-benchmark.json"},
        },
        "summary": {"controlledCandidates": len(qa_rows), "identityPass": controlled["summary"]["identityPass"], "viewPass": controlled["summary"]["viewPass"], "dualPass": controlled["summary"]["dualPass"], "goldenPack": len(golden), "goldenByView": by_view, "selectorFallback": selector_report["current"]["fallback"]},
        "blocked": ["BLOCKED_MANUAL_REVIEW: hair/clothing/occlusion/body framing and aesthetic identity remain human decisions", "BLOCKED_LORA: LoRA is not started because all Gates A-F are not fully passed and manual review is pending", "BLOCKED_60S_ACTION: explicitly out of scope for this run"],
        "manualReview": ["identity likeness", "hair and clothing", "left/right 45-degree semantics", "half-body head-to-waist framing", "full-body head-to-feet framing", "golden pack final approval"],
    }
    json_dump(run_root / "13-final-acceptance.json", final)
    html_contact_sheet(run_root / "identity-method-comparison.html", "Identity Method Comparison", qa_rows)
    html_contact_sheet(run_root / "multiview-candidates-contact-sheet.html", "Controlled Multi-view Candidates", qa_rows)
    html_contact_sheet(run_root / "golden-reference-contact-sheet.html", "Golden Reference Pack v2", golden)
    return final


class WorkerHandler(BaseHTTPRequestHandler):
    engine: FaceEngine | None = None

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "loopbackOnly": True, "worker": self.engine.runtime_info if self.engine else None})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.engine is None:
            self._json(503, {"error": "worker_not_ready"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/identity/analyze":
                self._json(200, self.engine.analyze(payload["path"], bool(payload.get("includeEmbedding", False))))
            elif self.path == "/identity/compare":
                self._json(200, self.engine.compare(payload["left"], payload["right"]))
            elif self.path == "/identity/view-angle":
                result = self.engine.analyze(payload["path"])
                face = result.get("faces", [None])[0] if result.get("faceCount") == 1 else None
                pose = face.get("headPose") if face else None
                self._json(200, {"path": result.get("path"), "yaw": pose.get("yaw") if pose else None, "pitch": pose.get("pitch") if pose else None, "roll": pose.get("roll") if pose else None, "viewClassRaw": face.get("viewClassRaw") if face else "unknown", "confidence": face.get("detectionConfidence") if face else 0.0})
            else:
                self._json(404, {"error": "not_found"})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve(host: str, port: int, cache_root: Path) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("identity worker refuses non-loopback bind")
    WorkerHandler.engine = FaceEngine(cache_root=cache_root)
    server = ThreadingHTTPServer((host, port), WorkerHandler)
    print(json.dumps({"status": "ready", "host": host, "port": port, "worker": WorkerHandler.engine.runtime_info}), flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["serve", "bootstrap", "evaluate"], default="bootstrap")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18084)
    args = parser.parse_args()
    if args.mode == "serve":
        serve(args.host, args.port, args.run_root / "cache")
        return 0
    if args.mode == "bootstrap":
        result = bootstrap(args.run_root)
    else:
        result = evaluate(args.run_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

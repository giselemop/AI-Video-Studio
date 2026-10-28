"""Create validated face-landmark OpenPose maps for the multiview probe.

The face geometry is extracted from two real local photographs through the
loopback InsightFace worker, then interpolated/extrapolated for research
angles.  The raster follows the OpenPose body + white face-keypoint convention
used by the ControlNet 1.1 OpenPose route.  It is deliberately a new library;
the previous identity-foundation templates are not overwritten.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def get_face(worker_url: str, path: Path) -> dict[str, Any]:
    result = post_json(worker_url.rstrip("/") + "/identity/analyze", {"path": str(path)})
    if result.get("faceCount") != 1:
        raise RuntimeError(f"Expected one face in {path}, got {result.get('faceCount')}")
    face = result["faces"][0]
    if len(face.get("landmarks106") or []) != 106 or len(face.get("landmarks5") or []) != 5:
        raise RuntimeError(f"Missing 5/106 landmarks in {path}")
    return {"analysis": result, "face": face}


def normalized_points(face: dict[str, Any], key: str) -> np.ndarray:
    x1, y1, x2, y2 = [float(v) for v in face["bbox"]]
    width = max(x2 - x1, 1.0)
    height = max(y2 - y1, 1.0)
    values = np.asarray(face[key], dtype=np.float32)
    values[:, 0] = (values[:, 0] - x1) / width
    values[:, 1] = (values[:, 1] - y1) / height
    return values


def remove_roll(points: np.ndarray, landmarks5: np.ndarray) -> tuple[np.ndarray, float]:
    eye_left = landmarks5[0]
    eye_right = landmarks5[1]
    center = (eye_left + eye_right) / 2.0
    angle = math.atan2(float(eye_right[1] - eye_left[1]), float(eye_right[0] - eye_left[0]))
    cosine = math.cos(-angle)
    sine = math.sin(-angle)
    rotation = np.asarray([[cosine, -sine], [sine, cosine]], dtype=np.float32)
    return (points - center) @ rotation.T + center, math.degrees(angle)


def mirror(points: np.ndarray) -> np.ndarray:
    result = points.copy()
    result[:, 0] = 1.0 - result[:, 0]
    return result


def map_to_head(points: np.ndarray, left: float = 0.42, top: float = 0.055, width: float = 0.16, height: float = 0.15) -> np.ndarray:
    result = points.copy()
    result[:, 0] = left + result[:, 0] * width
    result[:, 1] = top + result[:, 1] * height
    return result


def draw_body(canvas: np.ndarray, face5: np.ndarray) -> None:
    # OpenPose's 18 body keypoint order: nose, neck, right shoulder/elbow/
    # wrist, left shoulder/elbow/wrist, right hip/knee/ankle, left
    # hip/knee/ankle, right eye, left eye, right ear, left ear.
    nose = tuple(face5[2])
    right_eye = tuple(face5[1])
    left_eye = tuple(face5[0])
    eye_y = float((right_eye[1] + left_eye[1]) / 2.0)
    points = [
        nose, (0.50, 0.20), (0.60, 0.23), (0.66, 0.36), (0.66, 0.50),
        (0.40, 0.23), (0.34, 0.36), (0.34, 0.50), (0.56, 0.50),
        (0.56, 0.72), (0.57, 0.94), (0.44, 0.50), (0.44, 0.72),
        (0.43, 0.94), right_eye, left_eye, (0.60, eye_y), (0.40, eye_y),
    ]
    limb_seq = [
        (2, 3), (2, 6), (3, 4), (4, 5), (6, 7), (7, 8), (2, 9),
        (9, 10), (10, 11), (2, 12), (12, 13), (13, 14), (2, 1),
        (1, 15), (15, 17), (1, 16), (16, 18),
    ]
    colors = [
        (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
        (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
        (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
        (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255),
        (255, 0, 170),
    ]
    height, width = canvas.shape[:2]
    for (left_index, right_index), color in zip(limb_seq, colors):
        first = points[left_index - 1]
        second = points[right_index - 1]
        x = np.asarray([first[0] * width, second[0] * width])
        y = np.asarray([first[1] * height, second[1] * height])
        center = (int(np.mean(x)), int(np.mean(y)))
        length = float(np.sqrt((x[0] - x[1]) ** 2 + (y[0] - y[1]) ** 2))
        angle = math.degrees(math.atan2(float(y[0] - y[1]), float(x[0] - x[1])))
        polygon = cv2.ellipse2Poly(center, (max(1, int(length / 2)), 4), int(angle), 0, 360, 1)
        cv2.fillConvexPoly(canvas, polygon, tuple(int(value * 0.6) for value in color))
    for index, (x, y) in enumerate(points):
        color = colors[min(index, len(colors) - 1)]
        cv2.circle(canvas, (int(x * width), int(y * height)), 4, color, thickness=-1)


def validate_geometry(face5: np.ndarray, face106: np.ndarray, target_yaw: float) -> dict[str, Any]:
    eye_vector = face5[1] - face5[0]
    eye_distance = float(np.linalg.norm(eye_vector))
    eye_roll = math.degrees(math.atan2(float(eye_vector[1]), float(eye_vector[0])))
    eye_center = (face5[0] + face5[1]) / 2.0
    mouth_center = (face5[3] + face5[4]) / 2.0
    nose_eye_offset = float(face5[2][0] - eye_center[0])
    checks = {
        "landmark106Count": int(len(face106)),
        "allFinite": bool(np.isfinite(face106).all()),
        "allInNormalizedFaceBox": bool((face106 >= -0.02).all() and (face106 <= 1.02).all()),
        "eyeDistance": round(eye_distance, 6),
        "eyeRollDegrees": round(eye_roll, 4),
        "noseBelowEyes": bool(face5[2][1] > eye_center[1]),
        "mouthBelowNose": bool(mouth_center[1] > face5[2][1]),
        "targetYawHint": target_yaw,
    }
    checks["geometryPass"] = bool(
        checks["landmark106Count"] == 106
        and checks["allFinite"]
        and checks["allInNormalizedFaceBox"]
        and eye_distance > 0.035
        and abs(eye_roll) <= 1.5
        and checks["noseBelowEyes"]
        and checks["mouthBelowNose"]
    )
    checks["noseEyeCenterOffset"] = round(nose_eye_offset, 6)
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--worker-url", default="http://127.0.0.1:18084")
    parser.add_argument("--front", default="C:\\install\\AI\\Data\\Characters\\15\\standard\\identity_front.png")
    parser.add_argument("--left", default="C:\\install\\AI\\Data\\Characters\\7\\ref_20260810_002133_1c75d72f.png")
    parser.add_argument("--library-root", default="C:\\install\\AI\\Workflows\\CharacterHeadPoseTemplates")
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    out_root = run_root / "head_pose_templates"
    library_root = Path(args.library_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    library_root.mkdir(parents=True, exist_ok=True)

    front_data = get_face(args.worker_url, Path(args.front))
    left_data = get_face(args.worker_url, Path(args.left))
    front106, front5 = normalized_points(front_data["face"], "landmarks106"), normalized_points(front_data["face"], "landmarks5")
    left106, left5 = normalized_points(left_data["face"], "landmarks106"), normalized_points(left_data["face"], "landmarks5")
    front106, _ = remove_roll(front106, front5)
    front5, front_roll = remove_roll(front5, front5)
    left106, _ = remove_roll(left106, left5)
    left5, left_roll = remove_roll(left5, left5)
    left_native_yaw = float(left_data["face"]["headPose"]["yaw"])
    left_abs_yaw = max(abs(left_native_yaw), 1.0)

    targets = [
        ("head_front", 0.0, "front"),
        ("head_left_15", -15.0, "left"),
        ("head_right_15", 15.0, "right"),
        ("head_left_30", -30.0, "left"),
        ("head_right_30", 30.0, "right"),
        ("head_left_45", -45.0, "left"),
        ("head_right_45", 45.0, "right"),
        ("head_left_60", -60.0, "left"),
        ("head_right_60", 60.0, "right"),
    ]
    rows: list[dict[str, Any]] = []
    for name, target_yaw, side in targets:
        if target_yaw == 0:
            base106, base5 = front106, front5
            interpolation = 0.0
        else:
            interpolation = abs(target_yaw) / left_abs_yaw
            base106 = front106 * (1.0 - interpolation) + left106 * interpolation
            base5 = front5 * (1.0 - interpolation) + left5 * interpolation
            if side == "right":
                base106 = mirror(base106)
                base5 = mirror(base5)
                # Mirroring swaps the semantic left/right eye and mouth
                # labels.  Keep the 5-point contract semantic after the
                # raster mirror so body eye/ear keypoints do not become a
                # 180-degree roll artifact.
                base5[[0, 1]] = base5[[1, 0]]
                base5[[3, 4]] = base5[[4, 3]]
        face106 = map_to_head(base106)
        face5 = map_to_head(base5)
        validation = validate_geometry(base5, base106, target_yaw)
        canvas = np.zeros((768, 512, 3), dtype=np.uint8)
        draw_body(canvas, face5)
        for x, y in face106:
            cv2.circle(canvas, (int(x * canvas.shape[1]), int(y * canvas.shape[0])), 3, (255, 255, 255), thickness=-1)
        filename = f"{name}_20260817.png"
        output_path = out_root / filename
        library_path = library_root / filename
        cv2.imencode(".png", canvas)[1].tofile(str(output_path))
        if not library_path.exists():
            cv2.imencode(".png", canvas)[1].tofile(str(library_path))
        rows.append({
            "name": name,
            "path": str(output_path),
            "libraryPath": str(library_path),
            "targetYaw": target_yaw,
            "side": side,
            "controlType": "OpenPose body + face keypoints",
            "sourceType": "real_face_landmark_interpolation_or_extrapolation",
            "sourceFront": str(Path(args.front).resolve()),
            "sourceLeft": str(Path(args.left).resolve()),
            "sourceFrontYaw": float(front_data["face"]["headPose"]["yaw"]),
            "sourceLeftYaw": left_native_yaw,
            "interpolationFactorFromRealLeft": round(interpolation, 6),
            "rollCorrectionDegrees": {"front": round(front_roll, 4), "left": round(left_roll, 4)},
            "landmarkCount": 106,
            "geometryValidation": validation,
            "pitchRoll2DControl": "pitch/roll are not independently encoded by this 2D raster; manual and output QA required",
            "manualReviewRequired": True,
        })
    payload = {
        "schemaVersion": "2026-08-17.head-pose-template-library.v1",
        "runRoot": str(run_root),
        "libraryRoot": str(library_root),
        "controlNetModel": "C:\\install\\AI\\Models\\controlnet\\control_v11p_sd15_openpose.pth",
        "officialControlContract": "ControlNet 1.1 OpenPose body + face keypoints",
        "templates": rows,
        "allGeometryPass": all(row["geometryValidation"]["geometryPass"] for row in rows),
        "manualReviewRequired": True,
        "limitations": [
            "Head landmarks are extracted from real local photographs and interpolated; 45/60 degree templates include controlled extrapolation beyond the known left sample.",
            "The raster controls 2D face keypoint placement; pitch/roll and semantic body framing remain QA measurements, not guarantees.",
            "The head-pose benchmark must judge generated images with InsightFace yaw and the frozen thresholds.",
        ],
    }
    (run_root / "head-pose-template-library.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

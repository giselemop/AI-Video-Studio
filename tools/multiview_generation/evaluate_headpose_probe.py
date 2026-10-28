"""Evaluate the 15-image FaceID + explicit face-landmark OpenPose probe."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import requests


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def expected_view(target_yaw: float) -> dict[str, Any]:
    if abs(target_yaw) < 1:
        return {"side": "front", "minAbsYaw": 0, "maxAbsYaw": 15}
    if abs(target_yaw) <= 30:
        return {"side": "left" if target_yaw < 0 else "right", "minAbsYaw": 12, "maxAbsYaw": 40}
    return {"side": "left" if target_yaw < 0 else "right", "minAbsYaw": 27, "maxAbsYaw": 62}


def view_pass(target_yaw: float, yaw: float | None) -> tuple[bool, str, float | None]:
    if yaw is None:
        return False, "unknown", None
    spec = expected_view(target_yaw)
    error = abs(float(yaw) - target_yaw)
    if spec["side"] == "front":
        ok = abs(float(yaw)) < spec["maxAbsYaw"]
        return ok, "front" if ok else ("left" if yaw < 0 else "right"), error
    magnitude_ok = spec["minAbsYaw"] <= abs(float(yaw)) < spec["maxAbsYaw"]
    direction_ok = (yaw < 0) if spec["side"] == "left" else (yaw > 0)
    if magnitude_ok and direction_ok:
        actual = f"{spec['side']}_{30 if abs(target_yaw) <= 30 else 45}"
        return True, actual, error
    if abs(float(yaw)) < spec["minAbsYaw"]:
        return False, "front", error
    actual_side = "left" if yaw < 0 else "right"
    return False, f"{actual_side}_{30 if abs(yaw) < 40 else 45 if abs(yaw) < 62 else 'profile'}", error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--worker-url", default="http://127.0.0.1:18084")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    manifest_path = run_root / "headpose-generation-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    template_library = json.loads((run_root / "head-pose-template-library.json").read_text(encoding="utf-8"))
    master = manifest["identityMaster"]
    rows: list[dict[str, Any]] = []
    for item in manifest["results"]:
        if not item.get("technicalSuccess") or not item.get("path"):
            rows.append({**item, "faceDetected": False, "faceCount": 0, "technicalSuccess": False, "identityPass": False, "viewPass": False, "dualPass": False, "hardRejectFlags": ["GenerationFailed"]})
            continue
        analysis = post_json(args.worker_url.rstrip("/") + "/identity/analyze", {"path": item["path"]})
        comparison = post_json(args.worker_url.rstrip("/") + "/identity/compare", {"left": master, "right": item["path"]})
        face = analysis.get("faces", [None])[0] if analysis.get("faceCount") == 1 else None
        pose = face.get("headPose") if face else None
        yaw = pose.get("yaw") if pose else None
        target_yaw = float(item["targetYaw"])
        passes_view, detected_view, yaw_error = view_pass(target_yaw, yaw)
        similarity = comparison.get("rawCosineSimilarity")
        passes_identity = bool(face and similarity is not None and float(similarity) >= args.threshold)
        hard_reject: list[str] = []
        if not face or analysis.get("faceCount") != 1:
            hard_reject.append("FaceMissingOrCountInvalid")
        if not passes_identity:
            hard_reject.append("WrongIdentity")
        if not passes_view:
            hard_reject.append("WrongView")
        rows.append({
            "method": item["method"],
            "requestedView": item["requestedView"],
            "targetYaw": target_yaw,
            "seed": item["seed"],
            "path": item["path"],
            "workflow": manifest["workflow"],
            "headPoseTemplate": item["headPoseTemplate"],
            "identityMaster": master,
            "headPoseWeight": item["headPoseWeight"],
            "faceIdWeight": item["faceIdWeight"],
            "openPoseWeight": item["openPoseWeight"],
            "technicalSuccess": True,
            "faceDetected": bool(face),
            "faceCount": int(analysis.get("faceCount", 0)),
            "detectionConfidence": face.get("detectionConfidence") if face else None,
            "landmark5Count": len(face.get("landmarks5") or []) if face else 0,
            "landmark106Count": len(face.get("landmarks106") or []) if face else 0,
            "rawCosineSimilarity": similarity,
            "identityDecision": "PASS" if passes_identity else "FAIL",
            "yaw": yaw,
            "pitch": pose.get("pitch") if pose else None,
            "roll": pose.get("roll") if pose else None,
            "yawError": yaw_error,
            "detectedView": detected_view,
            "viewClassRaw": face.get("viewClassRaw") if face else "unknown",
            "viewDecision": "PASS" if passes_view else "FAIL",
            "viewConfidence": face.get("detectionConfidence") if face else 0.0,
            "faceQuality": face.get("faceQuality") if face else None,
            "blur": face.get("faceQuality", {}).get("blur") if face else None,
            "occlusion": face.get("faceQuality", {}).get("occlusion") if face else None,
            "bodyPoseStatus": "UNMEASURED_MANUAL_REVIEW",
            "bodyCoverage": "UNMEASURED_MANUAL_REVIEW",
            "headCrop": "UNMEASURED_MANUAL_REVIEW",
            "feetCrop": "UNMEASURED_MANUAL_REVIEW",
            "hardRejectFlags": hard_reject,
            "identityPass": passes_identity,
            "viewPass": passes_view,
            "dualPass": bool(passes_identity and passes_view and not hard_reject),
            "autoDecision": "REVIEW" if passes_identity and passes_view else "REJECT",
            "manualReviewRequired": True,
            "analysisMs": analysis.get("elapsedMs"),
            "generationDurationMs": item.get("durationMs"),
            "vramBefore": item.get("vramBefore"),
            "vramAfter": item.get("vramAfter"),
        })
    total = len(rows)
    technical = sum(bool(row.get("technicalSuccess")) for row in rows)
    identity = sum(bool(row.get("identityPass")) for row in rows)
    view = sum(bool(row.get("viewPass")) for row in rows)
    dual = sum(bool(row.get("dualPass")) for row in rows)
    generation_times = [float(row["generationDurationMs"]) for row in rows if row.get("generationDurationMs") is not None]
    analysis_times = [float(row["analysisMs"]) for row in rows if row.get("analysisMs") is not None]
    free_vram = [float(row["vramAfter"]["freeMiB"]) for row in rows if row.get("vramAfter")]
    summary = {
        "total": total,
        "technicalSuccess": technical,
        "identityPass": identity,
        "viewPass": view,
        "dualPass": dual,
        "dualPassRate": round(dual / total, 4) if total else 0.0,
        "hardReject": sum(bool(row.get("hardRejectFlags")) for row in rows),
        "headPoseBenchmarkGate": "PASS_CONTINUE" if dual / total >= 0.3 else "LOW_YIELD",
        "expansionAllowed": bool(dual / total >= 0.3),
        "byView": {},
    }
    for view_name in sorted({row["requestedView"] for row in rows}):
        group = [row for row in rows if row["requestedView"] == view_name]
        summary["byView"][view_name] = {
            "total": len(group),
            "identityPass": sum(bool(row["identityPass"]) for row in group),
            "viewPass": sum(bool(row["viewPass"]) for row in group),
            "dualPass": sum(bool(row["dualPass"]) for row in group),
            "actualYaw": [row["yaw"] for row in group],
            "yawError": [row["yawError"] for row in group],
        }
    benchmark = {
        "schemaVersion": "2026-08-17.faceid-headpose-benchmark.v1",
        "runRoot": str(run_root),
        "method": "FaceID+HeadPose",
        "frozenIdentityThreshold": args.threshold,
        "viewThresholds": {"frontAbsYawMax": 15, "threeQuarter30Range": [12, 40], "threeQuarter45Range": [27, 62]},
        "oneVariablePrinciple": manifest["fixed"],
        "summary": summary,
        "rows": rows,
        "manualReviewRequired": True,
        "limitations": [
            "The explicit face map is a 2D OpenPose face-keypoint control; pitch/roll and body crop are still manually reviewed.",
            "No threshold was loosened and no near-front result is reclassified as 30/45.",
        ],
    }
    (run_root / "04-faceid-headpose-benchmark.json").write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    control = {
        "schemaVersion": "2026-08-17.head-pose-control.v1",
        "templateLibrary": str(run_root / "head-pose-template-library.json"),
        "workflow": manifest["workflow"],
        "controlNet": manifest["controlNet"],
        "controlType": "OpenPose body + explicit 106 face landmark raster",
        "fixedWeights": manifest["fixed"],
        "templateGeometry": {"count": len(template_library["templates"]), "allGeometryPass": template_library["allGeometryPass"], "benchmarkTemplatesGeometryPass": all(next(row for row in template_library["templates"] if row["name"] == name)["geometryValidation"]["geometryPass"] for name in ["head_front", "head_left_30", "head_right_30", "head_left_45", "head_right_45"])},
        "benchmark": {"rows": total, "dualPass": dual, "dualPassRate": summary["dualPassRate"], "gate": summary["headPoseBenchmarkGate"]},
        "targetActual": [{"requestedView": row["requestedView"], "targetYaw": row["targetYaw"], "actualYaw": row["yaw"], "yawError": row["yawError"], "detectedView": row["detectedView"]} for row in rows],
        "identityPoseTradeoff": "FaceID identity conditioning and explicit face pose conditioning remain coupled; benchmark output, not prompt labels, decides the tradeoff.",
        "manualReviewRequired": True,
    }
    (run_root / "03-head-pose-control.json").write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "performance": {"generationP50Ms": statistics.median(generation_times) if generation_times else None, "generationP95Ms": sorted(generation_times)[max(0, math.ceil(len(generation_times) * 0.95) - 1)] if generation_times else None, "identityQaP50Ms": statistics.median(analysis_times) if analysis_times else None, "minFreeVramMiB": min(free_vram) if free_vram else None}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

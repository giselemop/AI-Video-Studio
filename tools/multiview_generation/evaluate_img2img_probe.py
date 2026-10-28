"""Evaluate the controlled SD1.5 Img2Img A/B/C/D multiview probe."""

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


def view_pass(target_yaw: float, yaw: float | None) -> tuple[bool, str, float | None]:
    if yaw is None:
        return False, "unknown", None
    value = float(yaw)
    error = abs(value - target_yaw)
    if abs(target_yaw) <= 30:
        minimum, maximum = 12.0, 40.0
        label = 30
    else:
        minimum, maximum = 27.0, 62.0
        label = 45
    side = "left" if target_yaw < 0 else "right"
    ok = minimum <= abs(value) < maximum and ((value < 0) if side == "left" else (value > 0))
    if ok:
        return True, f"{side}_{label}", error
    if abs(value) < minimum:
        detected = "front"
    else:
        detected = f"{'left' if value < 0 else 'right'}_{45 if abs(value) >= 40 else 30}"
    return False, detected, error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--worker-url", default="http://127.0.0.1:18084")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    manifest = json.loads((run_root / "img2img-generation-manifest.json").read_text(encoding="utf-8-sig"))
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
        passes_view, detected_view, yaw_error = view_pass(float(item["targetYaw"]), yaw)
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
            **item,
            "technicalSuccess": True,
            "faceDetected": bool(face), "faceCount": int(analysis.get("faceCount", 0)),
            "detectionConfidence": face.get("detectionConfidence") if face else None,
            "landmark5Count": len(face.get("landmarks5") or []) if face else 0,
            "landmark106Count": len(face.get("landmarks106") or []) if face else 0,
            "rawCosineSimilarity": similarity,
            "identityDecision": "PASS" if passes_identity else "FAIL", "identityPass": passes_identity,
            "targetYaw": float(item["targetYaw"]), "yaw": yaw,
            "pitch": pose.get("pitch") if pose else None, "roll": pose.get("roll") if pose else None,
            "yawError": yaw_error, "detectedView": detected_view, "viewClassRaw": face.get("viewClassRaw") if face else "unknown",
            "viewDecision": "PASS" if passes_view else "FAIL", "viewPass": passes_view,
            "viewConfidence": face.get("detectionConfidence") if face else 0.0,
            "faceQuality": face.get("faceQuality") if face else None,
            "blur": face.get("faceQuality", {}).get("blur") if face else None,
            "occlusion": face.get("faceQuality", {}).get("occlusion") if face else None,
            "bodyPoseStatus": "UNMEASURED_MANUAL_REVIEW", "bodyCoverage": "UNMEASURED_MANUAL_REVIEW",
            "headCrop": "UNMEASURED_MANUAL_REVIEW", "feetCrop": "UNMEASURED_MANUAL_REVIEW",
            "hardRejectFlags": hard_reject, "dualPass": bool(passes_identity and passes_view and not hard_reject),
            "autoDecision": "REVIEW" if passes_identity and passes_view else "REJECT", "manualReviewRequired": True,
            "analysisMs": analysis.get("elapsedMs"), "generationDurationMs": item.get("durationMs"),
        })
    total = len(rows)
    technical = sum(bool(row.get("technicalSuccess")) for row in rows)
    identity = sum(bool(row.get("identityPass")) for row in rows)
    view = sum(bool(row.get("viewPass")) for row in rows)
    dual = sum(bool(row.get("dualPass")) for row in rows)
    rate = dual / total if total else 0.0
    generation_times = [float(row["generationDurationMs"]) for row in rows if row.get("generationDurationMs") is not None]
    analysis_times = [float(row["analysisMs"]) for row in rows if row.get("analysisMs") is not None]
    summary: dict[str, Any] = {
        "total": total, "technicalSuccess": technical, "identityPass": identity, "viewPass": view, "dualPass": dual,
        "dualPassRate": round(rate, 4), "hardReject": sum(bool(row.get("hardRejectFlags")) for row in rows),
        "gate": "PASS_CONTINUE" if rate >= 0.3 else "LOW_YIELD", "expansionAllowed": rate >= 0.3,
        "byMethod": {}, "byView": {}, "byDenoise": {},
    }
    for key, selector in (("byMethod", lambda row: row["method"]), ("byView", lambda row: row["requestedView"]), ("byDenoise", lambda row: str(row["denoise"]))):
        for value in sorted({selector(row) for row in rows}):
            group = [row for row in rows if selector(row) == value]
            summary[key][value] = {
                "total": len(group), "identityPass": sum(bool(row.get("identityPass")) for row in group),
                "viewPass": sum(bool(row.get("viewPass")) for row in group), "dualPass": sum(bool(row.get("dualPass")) for row in group),
                "dualPassRate": round(sum(bool(row.get("dualPass")) for row in group) / len(group), 4) if group else 0.0,
                "yaws": [row.get("yaw") for row in group], "similarities": [row.get("rawCosineSimilarity") for row in group],
            }
    benchmark = {
        "schemaVersion": "2026-08-17.img2img-benchmark.v1", "runRoot": str(run_root), "methods": manifest["methods"],
        "views": manifest["views"], "denoiseLevels": manifest["denoiseLevels"], "frozenIdentityThreshold": args.threshold,
        "viewThresholds": {"threeQuarter30Range": [12, 40], "threeQuarter45Range": [27, 62]}, "oneVariablePrinciple": manifest["fixed"],
        "summary": summary, "rows": rows, "manualReviewRequired": True,
        "limitations": ["Img2Img comparison uses one fixed SD1.5 checkpoint, one identity master, one seed per configuration, and explicit face-control rasters.", "Body pose/crop and occlusion remain manual review fields; thresholds were not loosened."],
    }
    (run_root / "09-img2img-benchmark.json").write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "performance": {"generationP50Ms": statistics.median(generation_times) if generation_times else None, "generationP95Ms": sorted(generation_times)[max(0, math.ceil(len(generation_times) * 0.95) - 1)] if generation_times else None, "identityQaP50Ms": statistics.median(analysis_times) if analysis_times else None}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

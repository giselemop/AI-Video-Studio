from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


VIEWS = {
    "front": {"targetYaw": 0.0, "core": True},
    "right30": {"targetYaw": 30.0, "core": True},
    "right45": {"targetYaw": 45.0, "core": True},
    "back": {"targetYaw": None, "core": False},
    "left45": {"targetYaw": -45.0, "core": True},
    "left30": {"targetYaw": -30.0, "core": True},
}
PAIRS = [
    ("front", "left30"),
    ("front", "right30"),
    ("front", "left45"),
    ("front", "right45"),
    ("left30", "left45"),
    ("right30", "right45"),
]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def post(worker: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(worker.rstrip("/") + path, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def safe_copy(source: Path, run_root: Path, label: str) -> Path:
    source = source.resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in label)
    destination = run_root / "worker_inputs" / f"{safe_label}_{digest}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.resolve()


def view_result(target: float | None, yaw: float | None) -> tuple[bool | None, str, float | None]:
    if target is None:
        return None, "back_or_unscored", None
    if yaw is None:
        return False, "unknown", None
    yaw = float(yaw)
    error = abs(yaw - target)
    if abs(target) < 1:
        return abs(yaw) < 15, "front" if abs(yaw) < 15 else ("left" if yaw < 0 else "right"), error
    band = 30 if abs(target) <= 30 else 45
    lower, upper = ((12, 40) if band == 30 else (27, 62))
    direction = yaw < 0 if target < 0 else yaw > 0
    ok = lower <= abs(yaw) < upper and direction
    detected = ("left" if yaw < 0 else "right") + str(band) if ok else ("front" if abs(yaw) < 12 else ("left" if yaw < 0 else "right"))
    return bool(ok), detected, error


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    core = [row for row in rows if row.get("core")]
    technical = [row for row in core if row.get("technicalSuccess")]
    identity = sum(bool(row.get("identityPass")) for row in core)
    view = sum(bool(row.get("viewPass")) for row in core)
    dual = sum(bool(row.get("dualPass")) for row in core)
    hard = sum(bool(row.get("hardRejects")) for row in core)
    cosines = [float(row["identityRawCosine"]) for row in rows if row.get("identityRawCosine") is not None]
    yaw_errors = [float(row["yawError"]) for row in core if row.get("yawError") is not None]
    return {
        "requestedCoreCount": len(core),
        "technicalSuccessCount": len(technical),
        "identityPassCount": identity,
        "viewPassCount": view,
        "dualPassCount": dual,
        "hardRejectCount": hard,
        "conditionalDualRate": round(dual / len(technical), 4) if technical else None,
        "coreEndToEndDualRate": round(dual / len(core), 4) if core else None,
        "medianIdentity": statistics.median(cosines) if cosines else None,
        "medianYawError": statistics.median(yaw_errors) if yaw_errors else None,
        "p95YawError": sorted(yaw_errors)[max(0, math.ceil(len(yaw_errors) * 0.95) - 1)] if yaw_errors else None,
        "coreViewCoverage": round(view / len(core), 4) if core else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--worker", default="http://127.0.0.1:18084")
    parser.add_argument("--output", required=True)
    parser.add_argument("--back-only", action="store_true")
    args = parser.parse_args()

    run_root = Path(args.run_root).resolve()
    candidate_dir = Path(args.candidate_dir).resolve()
    reference = Path(args.reference).resolve()
    out_path = Path(args.output).resolve()
    result: dict[str, Any] = {
        "schema": "character-architecture-replacement.multiview-qa.v1",
        "capturedAt": now(),
        "alias": args.alias,
        "architecture": args.architecture,
        "runRoot": str(run_root),
        "worker": args.worker,
        "reference": str(reference),
        "thresholds": {
            "identityRawCosine": 0.5,
            "frontAbsYawMax": 15,
            "yaw30Range": [12, 40],
            "yaw45Range": [27, 62],
            "crossViewCosine": 0.5,
            "multiViewSetPass": "all core IdentityPass, at least 4/5 core ViewPass, no severe HardReject, cross-view mean/min/median >= crossViewCosine",
        },
        "status": "STARTED",
        "rows": [],
        "crossView": {"pairs": [], "mean": None, "min": None, "median": None, "pass": False},
    }
    try:
        images = sorted(candidate_dir.rglob("*.png"))
        if args.back_only:
            images = [image for image in images if image.name.lower().startswith("sith_back_")]
        else:
            images = [image for image in images if image.name.lower().startswith("color_")]
        result["discoveredImages"] = [str(image) for image in images]
        master_safe = safe_copy(reference, run_root, f"{args.alias}_identity_master")
        rows: list[dict[str, Any]] = []
        for index, image in enumerate(images):
            if args.back_only:
                requested = "back"
            else:
                requested = list(VIEWS.keys())[index % len(VIEWS)]
            target = VIEWS[requested]["targetYaw"]
            worker_image = safe_copy(image, run_root, f"{args.alias}_{requested}_{index}")
            row: dict[str, Any] = {
                "index": index,
                "requestedView": requested,
                "targetYaw": target,
                "core": bool(VIEWS[requested]["core"]),
                "sourcePath": str(image),
                "workerOutputPath": str(worker_image),
                "technicalSuccess": True,
                "faceCount": None,
                "identityRawCosine": None,
                "identityPass": False,
                "yaw": None,
                "pitch": None,
                "roll": None,
                "viewPass": None,
                "detectedView": "unknown",
                "yawError": None,
                "hardRejects": [],
                "dualPass": False,
            }
            try:
                analysis = post(args.worker, "/identity/analyze", {"path": str(worker_image)})
                comparison = post(args.worker, "/identity/compare", {"left": str(master_safe), "right": str(worker_image)})
                row["identityAnalysis"] = analysis
                row["comparison"] = comparison
                row["faceCount"] = int(analysis.get("faceCount", 0))
                face = analysis.get("faces", [None])[0] if row["faceCount"] == 1 else None
                pose = face.get("headPose") if face else None
                row["identityRawCosine"] = comparison.get("rawCosineSimilarity")
                row["identityPass"] = bool(face and row["identityRawCosine"] is not None and float(row["identityRawCosine"]) >= 0.5)
                row["yaw"] = pose.get("yaw") if pose else None
                row["pitch"] = pose.get("pitch") if pose else None
                row["roll"] = pose.get("roll") if pose else None
                row["viewPass"], row["detectedView"], row["yawError"] = view_result(target, row["yaw"])
                if not face or row["faceCount"] != 1:
                    row["hardRejects"].append("FaceMissingOrCountInvalid")
                if not row["identityPass"]:
                    row["hardRejects"].append("IdentityFail")
                if row["core"] and not row["viewPass"]:
                    row["hardRejects"].append("ViewFail")
                row["dualPass"] = bool(row["core"] and row["identityPass"] and row["viewPass"] and not row["hardRejects"])
            except Exception as exc:
                row["technicalSuccess"] = False
                row["hardRejects"].append("QAWorkerError")
                row["qaError"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
        result["rows"] = rows
        result["summary"] = summarize(rows)

        by_view = {name: next((row for row in rows if row.get("requestedView") == name), None) for name in VIEWS}
        pair_rows = []
        for left, right in PAIRS:
            lrow, rrow = by_view.get(left), by_view.get(right)
            if not lrow or not rrow:
                pair_rows.append({"left": left, "right": right, "status": "NOT_AVAILABLE", "rawCosine": None})
                continue
            try:
                comparison = post(args.worker, "/identity/compare", {"left": lrow["workerOutputPath"], "right": rrow["workerOutputPath"]})
                cosine = comparison.get("rawCosineSimilarity")
                pair_rows.append({"left": left, "right": right, "status": "EVALUATED", "rawCosine": cosine, "comparison": comparison})
            except Exception as exc:
                pair_rows.append({"left": left, "right": right, "status": "ERROR", "rawCosine": None, "error": f"{type(exc).__name__}: {exc}"})
        cosines = [float(item["rawCosine"]) for item in pair_rows if item.get("rawCosine") is not None]
        result["crossView"] = {
            "pairs": pair_rows,
            "mean": statistics.mean(cosines) if cosines else None,
            "min": min(cosines) if cosines else None,
            "median": statistics.median(cosines) if cosines else None,
            "threshold": 0.5,
            "pass": bool(len(pair_rows) == len(PAIRS) and len(cosines) == len(PAIRS) and min(cosines) >= 0.5),
        }
        core = [row for row in rows if row.get("core")]
        severe = [row for row in core if any(reject in {"FaceMissingOrCountInvalid", "QAWorkerError"} for reject in row.get("hardRejects", []))]
        result["multiViewSetPass"] = bool(
            len(core) == 5
            and all(row.get("identityPass") for row in core)
            and sum(bool(row.get("viewPass")) for row in core) >= 4
            and not severe
            and result["crossView"]["pass"]
        )
        result["status"] = "EVALUATED" if rows else "NO_OUTPUTS"
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = repr(exc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": len(result.get("rows", [])), "multiViewSetPass": result.get("multiViewSetPass"), "output": str(out_path)}, ensure_ascii=False))
    return 0 if result["status"] in {"EVALUATED", "NO_OUTPUTS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

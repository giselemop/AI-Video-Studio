"""Apply the frozen Identity/View/HardReject QA to SDXL stage outputs."""

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


RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")
WORKER = "http://127.0.0.1:18084"
MASTER = r"C:\install\AI\ComfyUI\input\multiview_20260817_identity_master.png"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(WORKER + path, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def worker_safe_copy(source: str | Path, run_root: Path, label: str) -> str:
    """Copy a generated/reference image under the worker's Data allow-list.

    ComfyUI keeps its output under C:\\install\\AI\\ComfyUI\\output, while the
    local identity worker intentionally rejects paths outside Data/Models/run
    roots. Hashing the destination makes this additive and avoids overwriting
    an existing evidence image on a rerun.
    """
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()[:12]
    safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in label)
    destination_dir = run_root / "worker_inputs"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{safe_label}_{digest}{source_path.suffix.lower()}"
    if not destination.exists():
        shutil.copy2(source_path, destination)
    return str(destination.resolve())


def view_result(target: float, yaw: float | None) -> tuple[bool, str, float | None]:
    if yaw is None:
        return False, "unknown", None
    yaw = float(yaw)
    error = abs(yaw - target)
    if abs(target) < 1:
        return abs(yaw) < 15, "front" if abs(yaw) < 15 else ("left" if yaw < 0 else "right"), error
    side = "left" if target < 0 else "right"
    band = 30 if abs(target) <= 30 else 45
    ok = 12 <= abs(yaw) < 40 if band == 30 else 27 <= abs(yaw) < 62
    direction = yaw < 0 if side == "left" else yaw > 0
    detected = f"{side}_{band}" if ok and direction else ("front" if abs(yaw) < 12 else ("left" if yaw < 0 else "right"))
    return bool(ok and direction), detected, error


def stage_source(run_root: Path, method: str, stage: str) -> Path | None:
    paths = sorted(run_root.glob(f"stage-{method.lower()}-{stage.lower()}-generation*.json"), key=lambda path: path.stat().st_mtime)
    return paths[-1] if paths else None


def summarize(rows: list[dict[str, Any]], method: str, stage: str, status: str | None = None) -> dict[str, Any]:
    requested = len(rows)
    technical_rows = [row for row in rows if row.get("technicalSuccess")]
    identity = sum(bool(row.get("identityPass")) for row in rows)
    view = sum(bool(row.get("viewPass")) for row in rows)
    dual = sum(bool(row.get("dualPass")) for row in rows)
    hard = sum(bool(row.get("hardRejects")) for row in rows)
    cosines = [float(row["identityRawCosine"]) for row in rows if row.get("identityRawCosine") is not None]
    yaw_errors = [float(row["yawError"]) for row in rows if row.get("yawError") is not None]
    result_status = status or ("NOT_EVALUATED" if requested == 0 else "EVALUATED")
    return {
        "method": method,
        "stage": stage,
        "status": result_status,
        "requestedCount": requested,
        "technicalSuccessCount": len(technical_rows),
        "identityPassCount": identity,
        "viewPassCount": view,
        "dualPassCount": dual,
        "endToEndYield": round(dual / requested, 4) if requested else None,
        "conditionalQualityYield": round(dual / len(technical_rows), 4) if technical_rows else None,
        "hardRejectCount": hard,
        "medianCosine": statistics.median(cosines) if cosines else None,
        "medianYawError": statistics.median(yaw_errors) if yaw_errors else None,
        "p95YawError": sorted(yaw_errors)[max(0, math.ceil(len(yaw_errors) * 0.95) - 1)] if yaw_errors else None,
        "gate": "METHOD_REJECTED_STAGE_B" if stage == "B" and requested and dual / requested < 0.3 else ("PASS_CONTINUE" if stage == "B" and requested and dual / requested >= 0.3 else ("METHOD_CANDIDATE" if stage == "C" and requested and dual / requested >= 0.5 else ("METHOD_STRONG_CANDIDATE" if stage == "C" and requested and dual / requested >= 0.7 else "NOT_APPLICABLE"))),
        "noMonotonicViewControl": False,
        "identityDegradesWithYaw": False,
    }


def evaluate_stage(run_root: Path, method: str, stage: str, output_name: str) -> dict[str, Any]:
    source = stage_source(run_root, method, stage)
    if not source:
        result = {"schemaVersion": "2026-08-18.sdxl-stage-qa.v1", "capturedAt": now(), "runRoot": str(run_root), "method": method, "stage": stage, "status": "NOT_RUN", "summary": summarize([], method, stage, "NOT_RUN"), "rows": [], "sourceGenerationManifest": None}
        (run_root / output_name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    for item in raw.get("rows", []):
        base = {
            "method": method,
            "stage": stage,
            "requestedView": item.get("requestedView"),
            "targetYaw": item.get("targetYaw"),
            "seed": item.get("seed"),
            "technicalSuccess": bool(item.get("technicalSuccess")),
            "outputPath": item.get("outputPath"),
            "generationTimeMs": item.get("generationTimeMs"),
            "peakVramMiB": item.get("gpu", {}).get("peakVramMiB") if item.get("gpu") else None,
            "lowestFreeVramMiB": item.get("gpu", {}).get("lowestFreeMiB") if item.get("gpu") else None,
            "gpu": item.get("gpu"),
            "hardwareStatus": item.get("hardwareStatus"),
            "oom": item.get("oom", False),
            "checkpoint": r"C:\install\AI\Models\checkpoints\sdxl\sd_xl_base_1.0.safetensors",
            "identityModel": "antelopev2",
            "adapter": "ip-adapter.bin" if method == "InstantID" else "ip-adapter_pulid_sdxl_fp16.safetensors",
            "controlNet": r"C:\install\AI\Models\controlnet\instantid\diffusion_pytorch_model.safetensors" if method == "InstantID" else None,
            "evaModel": "EVA02_CLIP_L_336_psz14_s6B.pt" if method == "PuLID" else None,
            "steps": 24,
            "cfg": 5.0,
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "resolution": "512x768",
            "identityStrength": 0.8 if method == "InstantID" else None,
            "controlStrength": 0.8 if method == "InstantID" else None,
            "pulidWeight": 0.8 if method == "PuLID" else None,
            "fusion": "fidelity" if method == "PuLID" else None,
            "faceDetected": False,
            "faceCount": 0,
            "identityRawCosine": None,
            "identityPass": False,
            "yaw": None,
            "pitch": None,
            "roll": None,
            "detectedView": "unknown",
            "yawError": None,
            "viewPass": False,
            "hardRejects": [],
            "manualReviewRequired": True,
        }
        if not base["technicalSuccess"] or not base["outputPath"]:
            base["hardRejects"] = ["GenerationFailed"]
            rows.append({**base, "dualPass": False})
            continue
        try:
            worker_output = worker_safe_copy(base["outputPath"], run_root, f"{method}_{stage}_{base['requestedView']}_{base['seed']}")
            worker_master = worker_safe_copy(MASTER, run_root, "identity_master")
            base["workerOutputPath"] = worker_output
            base["workerIdentityMasterPath"] = worker_master
            analysis = post("/identity/analyze", {"path": worker_output})
            comparison = post("/identity/compare", {"left": worker_master, "right": worker_output})
            base["faceCount"] = int(analysis.get("faceCount", 0))
            face = analysis.get("faces", [None])[0] if base["faceCount"] == 1 else None
            pose = face.get("headPose") if face else None
            base["faceDetected"] = bool(face)
            base["identityRawCosine"] = comparison.get("rawCosineSimilarity")
            base["identityPass"] = bool(face and base["identityRawCosine"] is not None and float(base["identityRawCosine"]) >= 0.5)
            base["yaw"] = pose.get("yaw") if pose else None
            base["pitch"] = pose.get("pitch") if pose else None
            base["roll"] = pose.get("roll") if pose else None
            base["viewPass"], base["detectedView"], base["yawError"] = view_result(float(base["targetYaw"]), base["yaw"])
            if not face or base["faceCount"] != 1:
                base["hardRejects"].append("FaceMissingOrCountInvalid")
            if not base["identityPass"]:
                base["hardRejects"].append("IdentityFail")
            if not base["viewPass"]:
                base["hardRejects"].append("ViewFail")
            base["identityAnalysis"] = {"detectionConfidence": face.get("detectionConfidence") if face else None, "faceQuality": face.get("faceQuality") if face else None, "viewClassRaw": face.get("viewClassRaw") if face else "unknown", "analysisMs": analysis.get("elapsedMs")}
        except Exception as exc:
            base["hardRejects"].append("QAWorkerError")
            base["qaError"] = f"{type(exc).__name__}: {exc}"
        base["dualPass"] = bool(base["technicalSuccess"] and base["identityPass"] and base["viewPass"] and not base["hardRejects"])
        rows.append(base)
    summary = summarize(rows, method, stage)
    if stage in {"B", "C"}:
        by_view: dict[str, Any] = {}
        for view in sorted({row.get("requestedView") for row in rows}):
            group = [row for row in rows if row.get("requestedView") == view]
            by_view[view] = {"requested": len(group), "technical": sum(bool(row.get("technicalSuccess")) for row in group), "identity": sum(bool(row.get("identityPass")) for row in group), "view": sum(bool(row.get("viewPass")) for row in group), "dual": sum(bool(row.get("dualPass")) for row in group), "yaws": [row.get("yaw") for row in group], "yawErrors": [row.get("yawError") for row in group]}
        summary["byView"] = by_view
        if len(by_view) >= 3:
            front = [row.get("yaw") for row in rows if row.get("requestedView") == "front" and row.get("yaw") is not None]
            left30 = [abs(row.get("yaw")) for row in rows if row.get("requestedView") == "left30" and row.get("yaw") is not None]
            left45 = [abs(row.get("yaw")) for row in rows if row.get("requestedView") == "left45" and row.get("yaw") is not None]
            summary["noMonotonicViewControl"] = bool(front and left30 and left45 and not (statistics.median([abs(value) for value in front]) < statistics.median(left30) < statistics.median(left45)))
            identity_by_angle = [sum(bool(row.get("identityPass")) for row in rows if row.get("requestedView") == view) for view in ["front", "left30", "left45"]]
            summary["identityDegradesWithYaw"] = bool(identity_by_angle[0] > identity_by_angle[-1])
    result = {"schemaVersion": "2026-08-18.sdxl-stage-qa.v1", "capturedAt": now(), "runRoot": str(run_root), "method": method, "stage": stage, "status": "EVALUATED", "sourceGenerationManifest": str(source), "summary": summary, "rows": rows, "thresholds": {"identityRawCosine": 0.5, "frontAbsYawMax": 15, "yaw30Range": [12, 40], "yaw45Range": [27, 62], "dual": "IdentityPass AND ViewPass AND no HardReject"}, "manualReviewRequired": True}
    (run_root / output_name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(RUN_ROOT))
    args = parser.parse_args()
    root = Path(args.run_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    outputs = [evaluate_stage(root, "InstantID", "B", "06-instantid-stage-b.json"), evaluate_stage(root, "PuLID", "B", "07-pulid-stage-b.json"), evaluate_stage(root, "InstantID", "C", "08-instantid-stage-c.json"), evaluate_stage(root, "PuLID", "C", "09-pulid-stage-c.json")]
    for method, filename in [("InstantID", "04-instantid-vram-probe.json"), ("PuLID", "05-pulid-vram-probe.json")]:
        source = stage_source(root, method, "A")
        payload = json.loads(source.read_text(encoding="utf-8-sig")) if source else {"rows": [], "summary": {"status": "NOT_RUN"}}
        (root / filename).write_text(json.dumps({"schemaVersion": "2026-08-18.sdxl-vram-probe.v1", "capturedAt": now(), "method": method, "stage": "A", "status": "PASS" if payload.get("summary", {}).get("technicalSuccessCount", 0) else "FAIL_OR_NOT_RUN", "sourceGenerationManifest": str(source) if source else None, "summary": payload.get("summary", {}), "rows": payload.get("rows", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outputs": [{"method": item["method"], "stage": item["stage"], "summary": item["summary"]} for item in outputs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

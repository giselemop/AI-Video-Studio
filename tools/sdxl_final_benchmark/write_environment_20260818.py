"""Capture the non-secret runtime and workspace evidence for the SDXL final run."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def get_json(url: str) -> Any:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def command(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(args, cwd=str(cwd) if cwd else None, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def nvidia_smi() -> list[dict[str, Any]]:
    output = command(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"])
    rows: list[dict[str, Any]] = []
    if output.startswith("ERROR:"):
        return rows
    for line in output.splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) >= 5:
            rows.append({"name": values[0], "totalMiB": float(values[1]), "usedMiB": float(values[2]), "freeMiB": float(values[3]), "utilizationPercent": float(values[4])})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    project = Path(r"C:\install\AI\VideoStudio")
    workspace = Path(r"C:\install\AI")
    object_info = get_json("http://127.0.0.1:8188/object_info")
    system_stats = get_json("http://127.0.0.1:8188/system_stats")
    api_health = get_json("http://127.0.0.1:18080/api/health")
    worker_health = get_json("http://127.0.0.1:18084/health")
    status = command(["git", "status", "--porcelain=v1"], project)
    dirty = [line for line in status.splitlines() if line.strip()]
    system_devices = system_stats.get("devices", []) if isinstance(system_stats, dict) else []
    device = system_devices[0] if system_devices else {}
    drive = shutil.disk_usage("C:\\")
    manifest = run_root / "02-existing-assets.json"
    evidence = {
        "schemaVersion": "2026-08-18.sdxl-final-environment.v1",
        "capturedAt": now(),
        "runRoot": str(run_root),
        "scope": "InstantID + PuLID SDXL final decision benchmark only; no SD1.5 retuning, video, action, TTS, SRT, LoRA, Wan or Hunyuan work.",
        "workspace": str(workspace),
        "host": {"platform": platform.platform(), "python": platform.python_version(), "computerName": os.environ.get("COMPUTERNAME", "")},
        "git": {"branch": command(["git", "branch", "--show-current"], project), "head": command(["git", "rev-parse", "HEAD"], project), "dirtyCount": len(dirty), "existingDirtyFiles": dirty, "preservation": "No reset, clean, checkout, deletion or overwrite of existing user work."},
        "services": {"mainApi": "http://127.0.0.1:18080/api/health", "mainHealth": api_health, "comfy": "http://127.0.0.1:8188", "identityWorker": "http://127.0.0.1:18084/health", "workerHealth": worker_health},
        "comfy": {"version": system_stats.get("system", {}).get("comfyui_version") if isinstance(system_stats, dict) else None, "python": system_stats.get("system", {}).get("python_version") if isinstance(system_stats, dict) else None, "pytorch": system_stats.get("system", {}).get("pytorch_version") if isinstance(system_stats, dict) else None, "objectInfoNodeCount": len(object_info) if isinstance(object_info, dict) else None, "gpuFromComfy": {"name": device.get("name"), "totalMiB": round(device.get("vram_total", 0) / 1048576, 1) if device else None, "freeMiB": round(device.get("vram_free", 0) / 1048576, 1) if device else None}, "gpuFromNvidiaSmi": nvidia_smi(), "registeredNodes": {name: name in object_info if isinstance(object_info, dict) else False for name in ["InstantIDModelLoader", "InstantIDFaceAnalysis", "ApplyInstantID", "PulidModelLoader", "PulidInsightFaceLoader", "PulidEvaClipLoader", "ApplyPulid"]}},
        "disk": {"C": {"freeBytes": drive.free, "freeGiB": round(drive.free / 1024**3, 2), "totalGiB": round(drive.total / 1024**3, 2)}},
        "assetManifest": str(manifest),
        "previousEvidence": r"C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01",
        "frozenQA": {"identityRawCosine": 0.5, "frontAbsYawMax": 15, "yaw30Range": [12, 40], "yaw45Range": [27, 62], "dualDefinition": "IdentityPass AND ViewPass AND no HardReject"},
    }
    (run_root / "01-environment.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Collect non-secret environment and frozen baseline evidence for the 2026-08-17 run."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


RUN_ROOT = Path(r"C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01")
OLD_ROOT = Path(r"C:\install\AI\Data\QA\identity_foundation_20260816\run_02")
WORKSPACE = Path(r"C:\install\AI")
PROJECT = WORKSPACE / "VideoStudio"
MODELS = WORKSPACE / "Models"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def get_json(url: str) -> Any:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # evidence collector must still write partial evidence
        return {"error": str(exc)}


def run_text(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(args, cwd=str(cwd) if cwd else None, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def sha256(path: Path, max_bytes: int = 4 * 1024 * 1024 * 1024) -> str | None:
    if not path.is_file() or path.stat().st_size > max_bytes:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, expected_size: int | None = None) -> dict[str, Any]:
    exists = path.is_file()
    record: dict[str, Any] = {"path": str(path), "exists": exists, "expectedBytes": expected_size}
    if exists:
        record.update({"bytes": path.stat().st_size, "sha256IfSmall": sha256(path), "completeBySize": expected_size is None or path.stat().st_size == expected_size})
    else:
        record.update({"bytes": 0, "sha256IfSmall": None, "completeBySize": False})
    return record


def method_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method in sorted({row.get("method", "unknown") for row in rows}):
        group = [row for row in rows if row.get("method") == method]
        result[method] = {
            "total": len(group),
            "technicalSuccess": sum(bool(row.get("technicalSuccess")) for row in group),
            "identityPass": sum(bool(row.get("identityPass")) for row in group),
            "viewPass": sum(bool(row.get("viewPass")) for row in group),
            "dualPass": sum(bool(row.get("dualPass")) for row in group),
        }
    return result


def main() -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    old_qa_path = OLD_ROOT / "08-character-qa-v2.json"
    old_qa = json.loads(old_qa_path.read_text(encoding="utf-8-sig")) if old_qa_path.exists() else {}
    old_rows = old_qa.get("candidates", old_qa.get("rows", []))
    object_info = get_json("http://127.0.0.1:8188/object_info")
    system_stats = get_json("http://127.0.0.1:8188/system_stats")
    main_health = get_json("http://127.0.0.1:18080/health")
    worker_health = get_json("http://127.0.0.1:18084/health")
    git_status = run_text(["git", "status", "--porcelain=v1"], PROJECT)
    git_lines = [line for line in git_status.splitlines() if line.strip()]
    git_head = run_text(["git", "rev-parse", "HEAD"], PROJECT)
    git_branch = run_text(["git", "branch", "--show-current"], PROJECT)
    devices = system_stats.get("devices", []) if isinstance(system_stats, dict) else []
    device = devices[0] if devices else {}
    model_files = [
        file_record(MODELS / "checkpoints" / "v1-5-pruned-emaonly-fp16.safetensors"),
        file_record(MODELS / "ipadapter" / "ip-adapter-faceid-plusv2_sd15.bin"),
        file_record(MODELS / "controlnet" / "control_v11p_sd15_openpose.pth"),
        file_record(MODELS / "InsightFace" / "models" / "buffalo_l" / "det_10g.onnx"),
        file_record(MODELS / "checkpoints" / "sdxl" / "sd_xl_base_1.0.safetensors", 6938078334),
        file_record(MODELS / "instantid" / "ip-adapter.bin", 1691134141),
        file_record(MODELS / "controlnet" / "instantid" / "diffusion_pytorch_model.safetensors", 2502139136),
        file_record(MODELS / "pulid" / "ip-adapter_pulid_sdxl_fp16.safetensors", 791372856),
        file_record(MODELS / "InsightFace" / "downloads" / "antelopev2.zip", 360662982),
    ]
    nodes = {
        "ComfyUI_InstantID_20260817": {"path": str(WORKSPACE / "ComfyUI" / "custom_nodes" / "ComfyUI_InstantID_20260817"), "registered": "InstantIDModelLoader" in object_info if isinstance(object_info, dict) else False, "stagingHead": run_text(["git", "-C", str(RUN_ROOT / "install_staging" / "ComfyUI_InstantID"), "rev-parse", "HEAD"])},
        "PuLID_ComfyUI_20260817": {"path": str(WORKSPACE / "ComfyUI" / "custom_nodes" / "PuLID_ComfyUI_20260817"), "registered": "PulidModelLoader" in object_info if isinstance(object_info, dict) else False, "stagingHead": run_text(["git", "-C", str(RUN_ROOT / "install_staging" / "PuLID_ComfyUI"), "rev-parse", "HEAD"])},
        "ComfyUI_IPAdapter_plus": {"path": str(WORKSPACE / "ComfyUI" / "custom_nodes" / "ComfyUI_IPAdapter_plus"), "registered": "IPAdapterFaceID" in object_info if isinstance(object_info, dict) else False},
    }
    environment = {
        "schemaVersion": "2026-08-17.multiview-environment.v1",
        "capturedAt": now(),
        "runRoot": str(RUN_ROOT),
        "workspace": str(WORKSPACE),
        "scope": "static multiview identity generation only; video/action/TTS/LoRA expansion intentionally excluded",
        "host": {"platform": platform.platform(), "pythonCollector": sys.version, "computerName": os.environ.get("COMPUTERNAME", "")},
        "git": {"branch": git_branch, "head": git_head, "dirtyCount": len(git_lines), "dirtyEvidence": git_lines[:20], "preservationRule": "pre-existing and additive dirty work preserved; no reset/clean/checkout"},
        "endpoints": {"mainApi": "http://127.0.0.1:18080", "comfy": "http://127.0.0.1:8188", "identityWorker": "http://127.0.0.1:18084", "mainHealth": main_health, "workerHealth": worker_health},
        "comfy": {"version": "0.31.0", "objectInfoNodeCount": len(object_info) if isinstance(object_info, dict) else None, "systemStats": system_stats, "gpu": {"name": device.get("name"), "totalMiB": round(device.get("vram_total", 0) / 1048576, 0) if device else None, "freeMiB": round(device.get("vram_free", 0) / 1048576, 0) if device else None}},
        "nodes": nodes,
        "pythonDependenciesAddedWithoutTorchUpgrade": {"facexlib": "0.3.0", "ftfy": "6.3.1", "timm": "1.0.28", "wcwidth": "0.8.2"},
        "models": model_files,
        "frozenQa": {"identityThreshold": 0.5, "frontAbsYawMax": 15, "yaw30Range": [12, 40], "yaw45Range": [27, 62], "thresholdChanged": False},
        "externalEvidence": {"instantIdOfficialRepo": "https://github.com/instantx-research/instantid", "instantIdComfyNode": "https://github.com/cubiq/ComfyUI_InstantID", "puLidOfficialRepo": "https://github.com/ToTheBeginning/PuLID", "puLidComfyNode": "https://github.com/cubiq/PuLID_ComfyUI"},
    }
    (RUN_ROOT / "01-environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline = {
        "schemaVersion": "2026-08-17.multiview-baseline-summary.v1",
        "capturedAt": now(),
        "previousRunRoot": str(OLD_ROOT),
        "sourceQa": str(old_qa_path),
        "generationManifest": str(OLD_ROOT / "generation-manifest.json"),
        "frozenThresholds": {"identityCosine": 0.5, "frontAbsYawMax": 15, "yaw30Range": [12, 40], "yaw45Range": [27, 62]},
        "summary": old_qa.get("summary", {}),
        "byMethod": method_summary(old_rows),
        "faceIdFailureAnalysis": str(RUN_ROOT / "faceid-failure-analysis.json"),
        "baselineConclusion": "Previous FaceID 21/21 and total 42/42 technical success do not establish usable identity-view coupling: FaceID Dual 3/21 (14.29%), all 12 previous non-front FaceID views failed view QA, and overall Dual was 3/42 (7.14%).",
        "thresholdPolicy": "No threshold loosening; no prior output relabeled as a pass.",
    }
    (RUN_ROOT / "02-baseline-summary.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"environment": environment["git"], "baseline": baseline["byMethod"], "gpu": environment["comfy"]["gpu"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Capture the non-destructive baseline for the 3D character foundation gate.

This intentionally records facts available on the local machine only.  It never
reads credentials and never downloads model files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(r"C:\install\AI")
STUDIO = ROOT / "VideoStudio"
EVIDENCE = ROOT / "Data" / "QA" / "3d_character_foundation_20260818" / "run_01"
INPUTS = EVIDENCE / "worker_inputs"
WORKER = "http://127.0.0.1:18084"


def run(command: list[str], cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        p = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        return {
            "command": command,
            "returncode": p.returncode,
            "stdout": p.stdout[-12000:],
            "stderr": p.stderr[-12000:],
        }
    except Exception as exc:  # evidence should survive missing optional tools
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


def wsl_probe(command: list[str]) -> dict[str, Any]:
    """WSL emits UTF-16LE/console bytes on this host; decode raw evidence faithfully."""
    try:
        p = subprocess.run(command, capture_output=True, timeout=20, shell=False)
        def decode(raw: bytes) -> str:
            if not raw:
                return ""
            try:
                return raw.decode("utf-16le")
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="replace")
        return {"command": command, "returncode": p.returncode, "stdout": decode(p.stdout), "stderr": decode(p.stderr)}
    except Exception as exc:
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        st = path.stat()
        item.update({"bytes": st.st_size, "sha256": sha256(path)})
        try:
            from PIL import Image

            with Image.open(path) as im:
                item.update({"format": im.format, "width": im.width, "height": im.height, "mode": im.mode})
        except Exception as exc:
            item["image_probe_error"] = f"{type(exc).__name__}: {exc}"
    return item


def git_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "commit": run(["git", "-C", str(path), "rev-parse", "HEAD"], timeout=15),
        "status": run(["git", "-C", str(path), "status", "--short"], timeout=15),
        "remote": run(["git", "-C", str(path), "remote", "-v"], timeout=15),
    }


def write_json(name: str, data: dict[str, Any]) -> None:
    out = EVIDENCE / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def worker_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.dumps(payload).encode("utf-8")
        req = Request(WORKER + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {"http_status": response.status, "response": parsed}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def capture_environment() -> None:
    gpu = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"])
    wsl_status = wsl_probe(["wsl.exe", "--status"])
    wsl_list = wsl_probe(["wsl.exe", "-l", "-v"])
    disk = shutil.disk_usage(ROOT)
    python_path = Path(sys.executable)
    torch_info: dict[str, Any] = {}
    try:
        import torch

        torch_info = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
            "devices": [
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "total_memory_bytes": torch.cuda.get_device_properties(i).total_memory,
                }
                for i in range(torch.cuda.device_count())
            ],
        }
    except Exception as exc:
        torch_info = {"error": f"{type(exc).__name__}: {exc}"}

    write_json(
        "01-environment.json",
        {
            "schema": "3d-character-foundation/environment-v1",
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": {"hostname": socket.gethostname(), "platform": platform.platform(), "python": sys.version, "python_executable": str(python_path)},
            "workspace": {"root": str(ROOT), "studio": str(STUDIO), "evidence_root": str(EVIDENCE)},
            "gpu_probe": gpu,
            "torch": torch_info,
            "disk_C": {"total_bytes": disk.total, "free_bytes": disk.free, "used_bytes": disk.used},
            "wsl": {"status": wsl_status, "list": wsl_list},
            "service_health": {
                "comfyui_8188": run(["powershell", "-NoProfile", "-Command", "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8188/system_stats -TimeoutSec 10).StatusCode } catch { $_.Exception.Message }"], timeout=20),
                "video_studio_api_18080": run(["powershell", "-NoProfile", "-Command", "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18080/api/health -TimeoutSec 10).StatusCode } catch { $_.Exception.Message }"], timeout=20),
                "identity_worker_18084": run(["powershell", "-NoProfile", "-Command", "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18084/health -TimeoutSec 10).StatusCode } catch { $_.Exception.Message }"], timeout=20),
            },
        },
    )


def capture_historical() -> None:
    identity_master = INPUTS / "identity_master_face.png"
    comparisons: dict[str, Any] = {}
    for name in [
        "character_A_front.png",
        "character_A_full_body_wide.png",
        "character_B_front.png",
        "character_B_full_body.png",
        "character_B_full_body_v2.png",
        "character_B_full_body_wide.png",
    ]:
        comparisons[name] = worker_post(
            "/identity/compare",
            {"left": str(identity_master), "right": str(INPUTS / name)},
        )

    write_json(
        "02-historical-baseline.json",
        {
            "schema": "3d-character-foundation/historical-baseline-v1",
            "prior_decision": "ARCHITECTURE_SELECTION_INSUFFICIENT",
            "prior_evidence_root": str(ROOT / "Data" / "QA" / "character_architecture_replacement_20260818" / "run_01"),
            "identity_master": file_record(identity_master),
            "identity_master_semantics": "Frozen prior official Identity Master; adult East Asian man, head-and-shoulders, not full body.",
            "full_body_reference_status": "BLOCKED_FULL_BODY_REFERENCE",
            "full_body_reference_reason": "No trusted same-person full-body ground truth. Existing A/B full-body candidates were compared against the frozen master and are not valid substitutes.",
            "worker_compare": comparisons,
            "prior_candidate_notes": {
                "sith": "Previous local run was a back-view diffusion sampler only; no persistent mesh/representation or valid multiview set.",
                "stdgen": "Previous local run produced six independent images, not a persistent representation; it did not pass the unified multiview gate.",
                "sam3d": "Previous official checkpoint download attempts were blocked by repository approval.",
            },
        },
    )


def capture_assets() -> None:
    hs = ROOT / "CharacterArchitectures" / "HumanSplat"
    sith = ROOT / "CharacterArchitectures" / "SiTH"
    sam = ROOT / "CharacterArchitectures" / "SAM3DBody"
    pippo = ROOT / "CharacterArchitectures" / "Pippo"
    sith_weights = [
        sith / "checkpoints" / "SiTH_diffusion" / "controlnet" / "diffusion_pytorch_model.bin",
        sith / "checkpoints" / "SiTH_diffusion" / "image_encoder" / "pytorch_model.bin",
        sith / "checkpoints" / "SiTH_diffusion" / "projection" / "diffusion_pytorch_model.bin",
        sith / "checkpoints" / "SiTH_diffusion" / "unet" / "diffusion_pytorch_model.bin",
        sith / "checkpoints" / "SiTH_diffusion" / "vae" / "diffusion_pytorch_model.bin",
    ]
    hs_paths = [
        hs / "out" / "178000" / "model.safetensors",
        hs / "extensions" / "pixielib" / "HPS" / "pixie_data" / "SMPLX_NEUTRAL_2020.npz",
        hs / "extensions" / "pixielib" / "HPS" / "pixie_data" / "pixie_model.tar",
        hs / "extensions" / "diff-gaussian-rasterization",
    ]
    sam_paths = [sam / "checkpoints", sam / "checkpoints" / "sam-3d-body-dinov3"]
    pippo_paths = [pippo]
    pippo_reference = None
    pippo_record = EVIDENCE / "13-pippo-reference.json"
    if pippo_record.is_file():
        try:
            pippo_reference = json.loads(pippo_record.read_text(encoding="utf-8"))
        except Exception as exc:
            pippo_reference = {"read_error": f"{type(exc).__name__}: {exc}"}
    write_json(
        "03-candidate-assets.json",
        {
            "schema": "3d-character-foundation/candidate-assets-v1",
            "official_repositories": {
                "HumanSplat": "https://github.com/humansplat/humansplat",
                "SiTH": "https://github.com/SiTH-Diffusion/SiTH",
                "SAM3DBody": "https://github.com/facebookresearch/sam-3d-body",
                "Pippo": "https://github.com/facebookresearch/pippo",
            },
            "local_repositories": {"HumanSplat": git_record(hs), "SiTH": git_record(sith), "SAM3DBody": git_record(sam), "Pippo": git_record(pippo)},
            "humansplat_required_or_present": [file_record(p) for p in hs_paths],
            "sith_official_weights_present": [file_record(p) for p in sith_weights],
            "sam_local_paths": [file_record(p) for p in sam_paths],
            "pippo_local_paths": [file_record(p) for p in pippo_paths],
            "pippo_reference_status": pippo_reference,
            "policy": {
                "no_nonofficial_weights": True,
                "no_credential_capture": True,
                "png_set_is_not_representation": True,
                "representation_must_be_persistent_and_camera_renderable": True,
            },
        },
    )


def main() -> int:
    global EVIDENCE, INPUTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    EVIDENCE = args.evidence_root.resolve()
    INPUTS = EVIDENCE / "worker_inputs"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    capture_environment()
    capture_historical()
    capture_assets()
    print(json.dumps({"evidence_root": str(EVIDENCE), "files": ["01-environment.json", "02-historical-baseline.json", "03-candidate-assets.json"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

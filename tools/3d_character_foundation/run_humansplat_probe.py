#!/usr/bin/env python3
"""Run a safe HumanSplat deployment/import probe.

The probe deliberately stops before any credential prompt or non-official
download.  A missing model or dependency is evidence of the deployment gate,
not a reason to synthesize a fake representation.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\install\AI")
REPO = ROOT / "CharacterArchitectures" / "HumanSplat"
EVIDENCE = ROOT / "Data" / "QA" / "3d_character_foundation_20260818" / "run_01"


def run(command: list[str], cwd: Path | None = None, timeout: int = 120, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
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
            env=env,
        )
        return {
            "command": command,
            "returncode": p.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout": p.stdout[-16000:],
            "stderr": p.stderr[-16000:],
        }
    except Exception as exc:
        return {
            "command": command,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def exists(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "is_file": path.is_file(), "is_dir": path.is_dir()}


def import_probe(python: Path) -> dict[str, Any]:
    code = (
        "import importlib.util,sys; "
        "print('python='+sys.version); "
        "mods=['torch','diffusers','transformers','xformers','smplx','trimesh','plyfile','pygltflib','kiui','rembg','pytorch3d']; "
        "[print(m+'='+str(bool(importlib.util.find_spec(m)))) for m in mods]; "
        "import src.models"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    started = time.perf_counter()
    try:
        p = subprocess.run(
            [str(python), "-c", code],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env=env,
            shell=False,
        )
        return {
            "command": [str(python), "-c", code],
            "returncode": p.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout": p.stdout[-16000:],
            "stderr": p.stderr[-16000:],
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "elapsed_seconds": round(time.perf_counter() - started, 3)}


def main() -> int:
    global REPO, EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    REPO = args.repo.resolve()
    EVIDENCE = args.evidence_root.resolve()
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    checkpoint = REPO / "out" / "178000" / "model.safetensors"
    hps_root = REPO / "extensions" / "pixielib" / "HPS" / "pixie_data"
    raster_src = REPO / "extensions" / "diff-gaussian-rasterization"
    py_compile = run([str(args.python), "-m", "compileall", "-q", str(REPO / "src"), str(REPO / "extensions")], cwd=REPO, timeout=180)
    imports = import_probe(args.python)
    official_env = os.environ.copy()
    official_env["PYTHONPATH"] = str(REPO) + os.pathsep + official_env.get("PYTHONPATH", "")
    official_entry = run([str(args.python), str(REPO / "src" / "inference.py")], cwd=REPO, timeout=180, env=official_env)

    missing = [
        str(checkpoint) if not checkpoint.exists() else None,
        str(hps_root / "SMPLX_NEUTRAL_2020.npz") if not (hps_root / "SMPLX_NEUTRAL_2020.npz").exists() else None,
        str(hps_root / "pixie_model.tar") if not (hps_root / "pixie_model.tar").exists() else None,
    ]
    missing = [x for x in missing if x]
    import_text = (imports.get("stdout", "") + imports.get("stderr", "")).lower()
    entry_text = (official_entry.get("stdout", "") + official_entry.get("stderr", "")).lower()
    blocked_reasons = []
    if not checkpoint.exists():
        blocked_reasons.append("HUMANSPLAT_CHECKPOINT_MISSING: src/models/human_splat.py hard-codes out/178000/model.safetensors")
    if "no module named 'diffusers'" in import_text or "no module named \"diffusers\"" in import_text or "no module named 'diffusers'" in entry_text:
        blocked_reasons.append("DEPENDENCY_MISSING: diffusers is absent in the isolated probe interpreter")
    if "no module named 'xformers'" in import_text or "no module named \"xformers\"" in import_text:
        blocked_reasons.append("DEPENDENCY_MISSING: xformers is absent; official SV3D constructor requires it")
    if not (hps_root / "SMPLX_NEUTRAL_2020.npz").exists() or not (hps_root / "pixie_model.tar").exists():
        blocked_reasons.append("GATED_HPS_ASSETS_MISSING: official fetch_hps.sh requires PIXIE and SMPL-X account credentials")
    if not any(raster_src.rglob("*.pyd")) and not any(raster_src.rglob("*.dll")):
        blocked_reasons.append("RENDERER_NOT_BUILT: diff-gaussian-rasterization source exists but no local Windows binary was found")

    ram_probe = run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"], timeout=30)
    result = {
        "schema": "3d-character-foundation/humansplat-probe-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(REPO),
        "python": str(args.python),
        "hardware": run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"], timeout=30),
        "cpu_ram": {"cpu": platform.processor(), "logical_cpus": os.cpu_count(), "ram_probe": ram_probe},
        "official_assets_and_entrypoints": {
            "checkpoint": exists(checkpoint),
            "smplx": exists(hps_root / "SMPLX_NEUTRAL_2020.npz"),
            "pixie": exists(hps_root / "pixie_model.tar"),
            "gaussian_rasterizer_source": exists(raster_src),
            "official_fetch_script": exists(REPO / "settings" / "fetch_hps.sh"),
            "official_setup_script": exists(REPO / "settings" / "setup.sh"),
        },
        "static_compile_probe": py_compile,
        "python_import_probe": imports,
        "official_inference_entry_probe": official_entry,
        "representation_created": False,
        "persistent_representation_paths": [],
        "camera_renders": [],
        "renderer_executed": False,
        "vram_peak_mib": None,
        "cpu_time_seconds": None,
        "wall_time_seconds": max(py_compile.get("elapsed_seconds", 0), imports.get("elapsed_seconds", 0), official_entry.get("elapsed_seconds", 0)),
        "probe_gate": "BLOCKED",
        "blocked_reasons": blocked_reasons or ["Official entry did not produce a representation; inspect probe logs."],
        "missing_paths": missing,
        "credential_policy": "No credentials read, stored, or submitted; fetch_hps.sh was inspected but not executed.",
    }
    (EVIDENCE / "04-humansplat-deployment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "05-humansplat-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"probe_gate": result["probe_gate"], "blocked_reasons": blocked_reasons, "representation_created": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

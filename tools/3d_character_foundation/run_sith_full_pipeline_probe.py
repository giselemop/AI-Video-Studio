#!/usr/bin/env python3
"""Audit and execute the SiTH full-pipeline entry points without fake input.

The target Identity Master is head-and-shoulders, so this probe never turns it
into a fabricated full-body ground truth.  It records the official local
weights, dependency/import failures, and the exact boundary where a real mesh
could not be produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\install\AI")
REPO = ROOT / "CharacterArchitectures" / "SiTH"
EVIDENCE = ROOT / "Data" / "QA" / "3d_character_foundation_20260818" / "run_01"


def run(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 180) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        p = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        return {"command": command, "returncode": p.returncode, "elapsed_seconds": round(time.perf_counter() - started, 3), "stdout": p.stdout[-16000:], "stderr": p.stderr[-16000:]}
    except Exception as exc:
        return {"command": command, "elapsed_seconds": round(time.perf_counter() - started, 3), "error": f"{type(exc).__name__}: {exc}"}


def file_record(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        out["bytes"] = path.stat().st_size
        if path.stat().st_size <= 4_000_000_000:
            h = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    h.update(block)
            out["sha256"] = h.hexdigest()
    return out


def probe_imports(python: Path, env: dict[str, str]) -> dict[str, Any]:
    code = (
        "import importlib.util,sys; print('python='+sys.version); "
        "mods=['torch','torchvision','diffusers','transformers','accelerate','kaolin','nvdiffrast','smplx','trimesh','timm','einops','ninja','gradio','tinyobjloader']; "
        "[print(m+'='+str(bool(importlib.util.find_spec(m)))) for m in mods]; "
        "import torch; print('torch='+torch.__version__); print('cuda='+str(torch.version.cuda)); print('cuda_available='+str(torch.cuda.is_available()))"
    )
    return run([str(python), "-c", code], cwd=REPO, env=env, timeout=120)


def entry_import(python: Path, entry: str, env: dict[str, str]) -> dict[str, Any]:
    code = f"import {entry}"
    return run([str(python), "-c", code], cwd=REPO, env=env, timeout=120)


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

    env = os.environ.copy()
    sidecar = REPO / "sidecar_packages"
    env["PYTHONPATH"] = str(sidecar) + os.pathsep + str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    py_compile = run([str(args.python), "-m", "compileall", "-q", str(REPO / "fit.py"), str(REPO / "hallucinate.py"), str(REPO / "reconstruct.py"), str(REPO / "fitting"), str(REPO / "recon"), str(REPO / "diffusion")], cwd=REPO, env=env, timeout=180)
    imports = probe_imports(args.python, env)
    fit_import = entry_import(args.python, "fit", env)
    hallucinate_import = entry_import(args.python, "hallucinate", env)
    reconstruct_import = entry_import(args.python, "reconstruct", env)

    key_files = [
        REPO / "checkpoints" / "SiTH_diffusion" / "unet" / "diffusion_pytorch_model.bin",
        REPO / "checkpoints" / "SiTH_diffusion" / "controlnet" / "diffusion_pytorch_model.bin",
        REPO / "checkpoints" / "SiTH_diffusion" / "image_encoder" / "pytorch_model.bin",
        REPO / "checkpoints" / "SiTH_diffusion" / "projection" / "diffusion_pytorch_model.bin",
        REPO / "checkpoints" / "SiTH_diffusion" / "vae" / "diffusion_pytorch_model.bin",
        REPO / "checkpoints" / "recon_model.pth",
        REPO / "checkpoints" / "save_smplerx.pth",
        REPO / "data" / "body_models" / "smplx" / "SMPLX_NEUTRAL.pkl",
        REPO / "data" / "body_models" / "smplx" / "SMPLX_NEUTRAL.npz",
    ]
    expected_sizes = {
        REPO / "checkpoints" / "recon_model.pth": 785339073,
        REPO / "checkpoints" / "save_smplerx.pth": 2647490595,
    }
    outputs = []
    for suffix in [".obj", ".ply", ".glb", ".gltf", ".splat"]:
        outputs.extend(str(p) for p in REPO.rglob(f"*{suffix}") if "data" not in p.parts or p.name in {"smplx_canonical.obj", "smplx_uv.obj"})
    missing = [str(p) for p in key_files if not p.exists()]
    incomplete = [str(p) for p, expected in expected_sizes.items() if p.exists() and p.stat().st_size != expected]
    reasons = [
        "BLOCKED_FULL_BODY_REFERENCE: frozen Identity Master is head-and-shoulders and no trusted same-person full-body reference exists",
        "WINDOWS_NATIVE_BLOCKED: official environment targets Ubuntu 22.04/PyTorch 2.1/CUDA 12.1; this host is Windows/Python 3.13/Torch 2.11/CUDA 13",
    ]
    if not (REPO / "data" / "body_models" / "smplx").exists():
        reasons.append("GATED_BODY_ASSET_MISSING: SMPL-X body models are not present; official release requires account-gated download")
    if not (REPO / "checkpoints" / "save_smplerx.pth").exists():
        reasons.append("CHECKPOINT_MISSING: save_smplerx.pth was not present at probe capture")
    elif (REPO / "checkpoints" / "save_smplerx.pth").stat().st_size != expected_sizes[REPO / "checkpoints" / "save_smplerx.pth"]:
        reasons.append("CHECKPOINT_INCOMPLETE: save_smplerx.pth download was not complete at probe capture")
    if not (REPO / "checkpoints" / "recon_model.pth").exists():
        reasons.append("CHECKPOINT_MISSING: recon_model.pth was not present at probe capture")
    import_text = (json.dumps(imports, ensure_ascii=False) + json.dumps(fit_import, ensure_ascii=False) + json.dumps(hallucinate_import, ensure_ascii=False) + json.dumps(reconstruct_import, ensure_ascii=False)).lower()
    for dep in ["kaolin", "nvdiffrast", "smplx", "trimesh", "accelerate", "gradio"]:
        if f"no module named '{dep}'" in import_text or f"{dep}=false" in import_text:
            reasons.append(f"DEPENDENCY_MISSING: {dep}")
    if len(reasons) >= 3:
        reasons.append("DEPLOYMENT_COMPLEXITY_BLOCK: more than two independent dependency/asset gates remain")

    result = {
        "schema": "3d-character-foundation/sith-full-pipeline-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(REPO),
        "repo_commit": run(["git", "-C", str(REPO), "rev-parse", "HEAD"], timeout=20),
        "python": str(args.python),
        "runtime": {"platform": platform.platform(), "python": sys.version, "torch_probe": imports},
        "official_pipeline": ["fit.py body fitting", "hallucinate.py back-view reasoning", "reconstruct.py textured mesh/canonical reconstruction", "optional xatlas UV avatar"],
        "static_compile": py_compile,
        "dependency_probe": imports,
        "entrypoint_imports": {"fit": fit_import, "hallucinate": hallucinate_import, "reconstruct": reconstruct_import},
        "official_assets": [file_record(p) for p in key_files],
        "existing_candidate_outputs": outputs,
        "persistent_representation_paths": [],
        "representation_created": False,
        "mesh_created": False,
        "textured_mesh_created": False,
        "camera_renders": [],
        "renderer_executed": False,
        "full_pipeline_executed": False,
        "probe_gate": "BLOCKED",
        "blocked_reasons": reasons,
        "missing_paths_at_capture": missing,
        "incomplete_paths_at_capture": incomplete,
        "previous_sampler_boundary": "Previous local attempt was back-view diffusion only; its generated PNGs are explicitly excluded from this full-pipeline representation gate.",
        "credential_policy": "No SMPL-X credentials were requested or stored.",
    }
    for name in ["07-sith-deployment.json", "08-sith-full-pipeline-probe.json", "09-sith-multiview.json"]:
        (EVIDENCE / name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"probe_gate": result["probe_gate"], "representation_created": False, "reason_count": len(reasons)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

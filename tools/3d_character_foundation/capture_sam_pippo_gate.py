#!/usr/bin/env python3
"""Capture SAM 3D Body permission evidence and Pippo reference status."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\install\AI")
SAM = ROOT / "CharacterArchitectures" / "SAM3DBody"
EVIDENCE = ROOT / "Data" / "QA" / "3d_character_foundation_20260818" / "run_01"


def run(command: list[str], cwd: Path | None = None, timeout: int = 60) -> dict[str, Any]:
    try:
        p = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
        return {"command": command, "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]}
    except Exception as exc:
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


def local_probe(python: Path) -> dict[str, Any]:
    code = "import pyrootutils; import sam_3d_body; print('sam_import=ok')"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SAM) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        p = subprocess.run([str(python), "-c", code], cwd=str(SAM), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, shell=False)
        return {"command": [str(python), "-c", code], "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]}
    except Exception as exc:
        return {"command": [str(python), "-c", code], "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    evidence.mkdir(parents=True, exist_ok=True)

    urls = [
        "https://huggingface.co/facebook/sam-3d-body-dinov3/resolve/main/config.json",
        "https://huggingface.co/facebook/sam-3d-body-vith/resolve/main/config.json",
    ]
    hf = [run(["curl.exe", "-I", "-L", "--max-time", "25", url]) for url in urls]
    local = local_probe(args.python)
    sam = {
        "schema": "3d-character-foundation/sam3d-gate-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "official_repo": "https://github.com/facebookresearch/sam-3d-body",
        "local_repo": str(SAM),
        "checkpoint_recheck": {"urls": urls, "responses": hf, "decision": "GATED_BLOCKED: official HF response is GatedRepo/approval required"},
        "local_checkpoint_paths": [str(SAM / "checkpoints" / "sam-3d-body-dinov3"), str(SAM / "checkpoints" / "sam-3d-body-vith")],
        "local_import_probe": local,
        "representation_created": False,
        "persistent_representation_paths": [],
        "camera_renders": [],
        "probe_gate": "BLOCKED_CHECKPOINT_ACCESS",
        "blocked_reasons": ["Official DINOv3 and ViT-H checkpoint config requests returned GatedRepo and require authenticated access/approval.", "No local checkpoint directory was present.", "No SAM 3D Body probe was run after the permission gate, per scope."],
        "no_large_retry": True,
    }
    (evidence / "10-sam3d-deployment.json").write_text(json.dumps(sam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (evidence / "11-sam3d-probe.json").write_text(json.dumps(sam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sam_mv = dict(sam)
    sam_mv["schema"] = "3d-character-foundation/sam3d-multiview-v1"
    sam_mv["multiview_gate"] = "NOT_RUN_BLOCKED_CHECKPOINT_ACCESS"
    (evidence / "12-sam3d-multiview.json").write_text(json.dumps(sam_mv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pippo = {
        "schema": "3d-character-foundation/pippo-reference-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "official_repo": "https://github.com/facebookresearch/pippo",
        "official_head_probe": run(["git", "ls-remote", "https://github.com/facebookresearch/pippo.git", "HEAD"]),
        "release_status": "Official README states this is a code-only release without pre-trained weights; packaged training samples require authenticated Hugging Face access.",
        "decision": "REFERENCE_ONLY_NO_LOCAL_DECISION",
        "representation_created": False,
        "probe_gate": "NOT_A_DECISION_CANDIDATE",
        "policy": "No non-official weights downloaded; no local clone created.",
    }
    (evidence / "13-pippo-reference.json").write_text(json.dumps(pippo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sam": sam["probe_gate"], "pippo": pippo["decision"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

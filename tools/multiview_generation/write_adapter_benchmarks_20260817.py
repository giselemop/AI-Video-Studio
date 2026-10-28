"""Write honest deployment/benchmark status records for InstantID and PuLID."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    run_root = Path(r"C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01")
    probe = load(run_root / "adapter-asset-probe.json")
    environment = load(run_root / "01-environment.json")
    assets = probe["assets"]
    probes = {item["name"]: item for item in probe["probes"]}
    captured = datetime.now().astimezone().isoformat()
    common = {
        "capturedAt": captured,
        "runRoot": str(run_root),
        "activeComfyNodePaths": [
            r"C:\install\AI\ComfyUI\custom_nodes\ComfyUI_InstantID_20260817",
            r"C:\install\AI\ComfyUI\custom_nodes\PuLID_ComfyUI_20260817",
        ],
        "gpu": environment.get("comfy", {}).get("gpu", {}),
        "officialContract": {
            "instantId": "SDXL-only; antelopev2; InstantID adapter; InstantID ControlNet",
            "puLid": "SDXL route; antelopev2; PuLID adapter; EVA02 CLIP",
        },
        "noFakeGenerationRule": "No output image was counted as a benchmark sample unless the full workflow completed and produced a file.",
    }
    instantid_status = "DEPLOYED_NODE_BLOCKED_INCOMPLETE_ASSETS" if not assets["instantIdAdapter"]["completeBySize"] or not assets["instantIdControlNet"]["completeBySize"] or not assets["sdxlBase"]["completeBySize"] else "READY_FOR_PROBE"
    instantid_deploy = {
        "schemaVersion": "2026-08-17.instantid-deployment.v1",
        **common,
        "method": "InstantID",
        "status": instantid_status,
        "nodeRepo": {"staging": str(run_root / "install_staging" / "ComfyUI_InstantID"), "active": r"C:\install\AI\ComfyUI\custom_nodes\ComfyUI_InstantID_20260817", "commit": "72495e806bc2ab9c41581e15ccaa1bcf83c477e8", "objectInfoRegistered": True},
        "dependencies": {"facexlib": "not required by InstantID node", "insightface": "0.7.3 source via runtime path", "onnxruntime": "1.28.0 via runtime path", "antelopev2": assets["antelopeFolder"]},
        "assets": {"adapter": assets["instantIdAdapter"], "controlNet": assets["instantIdControlNet"], "sdxlBase": assets["sdxlBase"], "antelopeZip": assets["antelopeZip"]},
        "actualProbes": [probes.get("InstantIDFaceAnalysis.antelopev2.CPU"), probes.get("InstantIDModelLoader.ip-adapter.bin")],
        "blockers": ["InstantID adapter and ControlNet files are incomplete partial downloads; loader integrity is not proven.", "No complete SDXL checkpoint is available for a valid InstantID generation workflow.", "12GB RTX 4070 must be measured only after a complete SDXL workflow is available; current run records preflight blockage, not a fabricated OOM."],
    }
    instantid_benchmark = {
        "schemaVersion": "2026-08-17.instantid-benchmark.v1",
        **common,
        "method": "InstantID",
        "status": "BLOCKED_PREGENERATION_INCOMPLETE_ASSETS",
        "summary": {"total": 0, "technicalSuccess": 0, "identityPass": None, "viewPass": None, "dualPass": None, "dualPassRate": None, "gate": "BLOCKED", "expansionAllowed": False},
        "plannedProbe": {"views": ["head_front", "head_left_30", "head_right_30", "head_left_45", "head_right_45"], "seed": 330101, "resolution": "512x768", "identityInput": "multiview_20260817_identity_master.png", "imageKpsInput": "head_pose_templates/*.png"},
        "actualProbes": instantid_deploy["actualProbes"],
        "assetEvidence": instantid_deploy["assets"],
        "blocker": "A valid generation cannot be queued until the adapter, InstantID ControlNet, and SDXL checkpoint pass complete-size/hash checks.",
    }
    pulid_status = "DEPLOYED_MODEL_LOADER_PASS_EVA_BLOCKED" if probes.get("PulidModelLoader.ip-adapter_pulid_sdxl_fp16.safetensors", {}).get("status") == "PASS" else "DEPLOYED_NODE_BLOCKED_MODEL"
    pulid_deploy = {
        "schemaVersion": "2026-08-17.pulid-deployment.v1",
        **common,
        "method": "PuLID",
        "status": pulid_status,
        "nodeRepo": {"staging": str(run_root / "install_staging" / "PuLID_ComfyUI"), "active": r"C:\install\AI\ComfyUI\custom_nodes\PuLID_ComfyUI_20260817", "commit": "93e0c4c226b87b23c0009d671978bad0e77289ff", "objectInfoRegistered": True},
        "dependencies": {"facexlib": "0.3.0", "timm": "1.0.28", "ftfy": "6.3.1", "wcwidth": "0.8.2", "insightface": "0.7.3 source via runtime path", "antelopev2": assets["antelopeFolder"], "evaClip": "native loader requests EVA02_CLIP_L_336_psz14_s6B.pt (~856MiB); controlled probe skipped the download"},
        "assets": {"adapter": assets["pulidAdapter"], "sdxlBase": assets["sdxlBase"], "antelopeZip": assets["antelopeZip"]},
        "actualProbes": [probes.get("PulidModelLoader.ip-adapter_pulid_sdxl_fp16.safetensors"), probes.get("PulidInsightFaceLoader.antelopev2.CPU"), probes.get("PulidEvaClipLoader")],
        "blockers": ["EVA CLIP is not installed; the native loader was deliberately prevented from starting an 856MiB automatic download in the final probe.", "No complete SDXL checkpoint is available for a valid PuLID generation workflow.", "No identity/view benchmark is counted without full SDXL + EVA + PuLID execution."],
    }
    pulid_benchmark = {
        "schemaVersion": "2026-08-17.pulid-benchmark.v1",
        **common,
        "method": "PuLID",
        "status": "BLOCKED_PREGENERATION_EVA_AND_SDXL",
        "summary": {"total": 0, "technicalSuccess": 0, "identityPass": None, "viewPass": None, "dualPass": None, "dualPassRate": None, "gate": "BLOCKED", "expansionAllowed": False},
        "plannedProbe": {"views": ["front", "head_left_30", "head_right_45"], "seed": 340101, "resolution": "512x768", "method": "fidelity", "weight": 0.8},
        "actualProbes": pulid_deploy["actualProbes"],
        "assetEvidence": pulid_deploy["assets"],
        "blocker": "A full PuLID generation requires the missing EVA CLIP asset and a complete SDXL checkpoint; node/model-loader passes are not quality passes.",
    }
    for name, value in (("05-instantid-deployment.json", instantid_deploy), ("06-instantid-benchmark.json", instantid_benchmark), ("07-pulid-deployment.json", pulid_deploy), ("08-pulid-benchmark.json", pulid_benchmark)):
        (run_root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"instantid": instantid_deploy["status"], "pulid": pulid_deploy["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

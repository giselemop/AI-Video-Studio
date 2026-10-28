"""Freeze the keyframe template and its additive contract, without deploying either."""

import hashlib
import json
from pathlib import Path

from download_models import ARTIFACTS
from prepare import build_workflow, PRESERVE, CASES


def write_new(path, data):
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() != encoded:
        raise RuntimeError("Existing frozen artifact differs; refusing overwrite: " + str(path))
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    filename = "flux2_klein4b_keyframe_api.json"
    workflow = build_workflow("female-reference.png", PRESERVE + CASES[0][1], 20261024)
    workflow_hash = write_new(root / filename, workflow)
    contract = {
        "id": "flux2-klein4b-keyframe-local-1024-v1",
        "version": "flux2-klein4b-keyframe-local-1024-v1",
        "fileName": filename,
        "workflowType": "Image",
        "productionEligible": False,
        "experimental": True,
        "licenseStatus": "APACHE_2_0_LOCAL_EXPERIMENT_PENDING_CONTENT_REVIEW",
        "taskTypes": ["Image", "Keyframe"],
        "modelFiles": [a["name"] for a in ARTIFACTS],
        "modelSha256": {a["name"]: a["sha256"] for a in ARTIFACTS},
        "nodes": [
            {"role": "diffusionModel", "nodeId": "1", "classType": "UNETLoader", "inputName": "unet_name"},
            {"role": "textEncoder", "nodeId": "2", "classType": "CLIPLoader", "inputName": "clip_name"},
            {"role": "vae", "nodeId": "3", "classType": "VAELoader", "inputName": "vae_name"},
            {"role": "positivePrompt", "nodeId": "7", "classType": "CLIPTextEncode", "inputName": "text"},
            {"role": "sampler", "nodeId": "14", "classType": "RandomNoise", "inputName": "noise_seed"},
            {"role": "schedule", "nodeId": "13", "classType": "Flux2Scheduler", "inputName": "steps"},
            {"role": "guidance", "nodeId": "11", "classType": "CFGGuider", "inputName": "cfg"},
            {"role": "output", "nodeId": "18", "classType": "SaveImage", "inputName": "filename_prefix"},
        ],
        "slots": [{"role": "firstFrame", "nodeId": "4", "classType": "LoadImage", "inputName": "image", "required": True}],
        "media": {"defaultWidth": 1024, "defaultHeight": 576, "allowedDimensions": [{"width": 1024, "height": 576}], "nativeFps": 1, "allowedFps": [], "exactFrameCount": False, "preserveAudio": False},
        "notes": "sha256=" + workflow_hash + " | Local-only FLUX.2 Klein 4B distilled FP8 reference edit, Qwen3-4B BF16 text encoder on CPU, 4-step Euler CFG1. Apache 2.0 model artifacts. Frozen six-candidate visual evaluation only; generation and identity/content approval remain distinct.",
    }
    write_new(root / "contract-definition.json", contract)
    print(json.dumps({"workflow": str(root / filename), "sha256": workflow_hash, "contract": str(root / "contract-definition.json")}))


if __name__ == "__main__":
    main()

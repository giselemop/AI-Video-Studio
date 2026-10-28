"""Build six fixed local ComfyUI edit prompts without submitting GPU work."""

import argparse
import hashlib
import json
from pathlib import Path


DATA_ROOT = Path(r"C:\install\AI\Data")
SETUP_ROOT = DATA_ROOT / "VisualValidation20261024" / "keyframes-setup"
MODELS = {
    "unet": "flux-2-klein-4b-fp8.safetensors",
    "clip": "qwen_3_4b.safetensors",
    "vae": "flux2-vae.safetensors",
}
PRESERVE = (
    "Edit the provided reference image. Preserve the exact identity of the adult person, "
    "facial proportions, age, hairstyle, outfit, lighting, background, and photographic style. "
    "Keep realistic natural skin texture. No text, logo, beauty filter or plastic skin. "
)
CASES = [
    ("K01_original_neutral", "Keep the original three-quarter camera angle, gaze direction, lighting and head-and-shoulders framing, with a neutral closed-mouth expression; make no other changes."),
    ("K02_original_smile", "Keep the original three-quarter camera angle, gaze direction, lighting and head-and-shoulders framing; change only expression to a very slight closed-mouth smile."),
    ("K03_relative_left_10", "Keep the head-and-shoulders framing; turn the head only 10 degrees left relative to the original three-quarter angle, with a neutral expression. Preserve the same eye shape and face shape."),
    ("K04_relative_right_10", "Keep the head-and-shoulders framing; turn the head only 10 degrees right relative to the original three-quarter angle, with a neutral expression. Preserve the same eye shape and face shape."),
    ("K05_closeup_neutral", "Change only framing to a natural face close-up of the same person, keeping the original three-quarter angle, gaze direction, lighting and neutral closed-mouth expression."),
    ("K06_closeup_smile", "Use a natural face close-up of the same person, keeping the original three-quarter angle, gaze direction, lighting and a very slight closed-mouth smile."),
]


def build_workflow(comfy_image, prompt, seed, width=1024, height=576, filename_prefix="VisualValidation20261024/Klein"):
    if not comfy_image or ".." in Path(comfy_image).parts or Path(comfy_image).is_absolute():
        raise ValueError("comfy_image must be the explicit relative uploaded ComfyUI input name")
    if width % 16 or height % 16 or width < 256 or height < 256 or width * height > 1024 * 1024:
        raise ValueError("Pilot dimensions must be multiples of 16, >=256 and <=1 megapixel")
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["clip"], "type": "flux2", "device": "cpu"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae"]}},
        "4": {"class_type": "LoadImage", "inputs": {"image": comfy_image}},
        "5": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "8": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
        "9": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "10": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["9", 0], "latent": ["6", 0]}},
        "11": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["8", 0], "negative": ["10", 0], "cfg": 1.0}},
        "12": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "13": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": width, "height": height}},
        "14": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "15": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "16": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["14", 0], "guider": ["11", 0], "sampler": ["12", 0], "sigmas": ["13", 0], "latent_image": ["15", 0]}},
        "17": {"class_type": "VAEDecode", "inputs": {"samples": ["16", 0], "vae": ["3", 0]}},
        "18": {"class_type": "SaveImage", "inputs": {"images": ["17", 0], "filename_prefix": filename_prefix}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--comfy-image", required=True)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if not source.is_relative_to(DATA_ROOT.resolve()):
        raise ValueError("Source must be an explicitly selected asset under the Data root")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    run_root = SETUP_ROOT / "prepared" / source_hash[:12]
    run_root.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "PreparedOnly", "gpu_submitted": False, "source_path": str(source), "source_sha256": source_hash, "comfy_image": args.comfy_image, "models": MODELS, "cases": []}
    for case_id, instruction in CASES:
        graph = build_workflow(args.comfy_image, PRESERVE + instruction, args.seed, args.width, args.height, "VisualValidation20261024/" + case_id)
        encoded = (json.dumps(graph, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        path = run_root / (case_id + ".api.json")
        if path.exists() and path.read_bytes() != encoded:
            raise RuntimeError("Prepared file differs; refusing overwrite: " + str(path))
        path.write_bytes(encoded)
        manifest["cases"].append({"id": case_id, "seed": args.seed, "width": args.width, "height": args.height, "workflow_path": str(path), "workflow_sha256": hashlib.sha256(encoded).hexdigest(), "prompt": PRESERVE + instruction})
    manifest_path = run_root / "manifest.json"
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != content:
        raise RuntimeError("Manifest differs; refusing overwrite")
    manifest_path.write_text(content, encoding="utf-8")
    print(str(manifest_path))


if __name__ == "__main__":
    main()

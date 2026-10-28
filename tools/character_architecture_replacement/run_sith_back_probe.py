from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolution", type=int, default=256)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=410101)
    args = parser.parse_args()
    repo = Path(args.repo)
    model = Path(args.model)
    reference = Path(args.reference)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "candidate-a-execution.json"
    result: dict = {
        "schema": "character-architecture-replacement.candidate-execution.v1",
        "capturedAtUtc": now(),
        "candidate": "SiTH",
        "alias": "candidate-a",
        "repo": str(repo),
        "repoHead": None,
        "model": str(model),
        "reference": str(reference),
        "requested": {"stage": "back_view_hallucination", "samples": args.samples, "resolution": args.resolution, "steps": args.steps, "seed": args.seed},
        "pipelineBoundary": {"attempted": ["image-conditioned CLIP reference embedding", "ControlNet UV/view conditioning", "diffusion back-view sampling"], "notAttempted": ["OpenPose fitting", "SMPL-X fitting", "textured mesh reconstruction", "UV unwrap"], "reason": "This host is Windows/Python 3.13 with no verified kaolin/nvdiffrast/SMPL-X body model stack; the back-view sampler is independently testable."},
        "status": "STARTED",
        "samples": [],
    }
    try:
        import subprocess
        import numpy as np
        import torch
        from PIL import Image
        from torchvision.transforms import functional as TF
        from transformers import CLIPVisionModelWithProjection
        from diffusers import AutoencoderKL, ControlNetModel, DDPMScheduler, UNet2DConditionModel, UniPCMultistepScheduler
        from diffusion.lib.ccprojection import CCProjection
        from diffusion.lib.pipeline import BackHallucinationPipeline
        from torchvision import transforms

        try:
            result["repoHead"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=30).strip()
        except Exception:
            pass
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available in the sidecar runtime")
        device = torch.device("cuda")
        dtype = torch.float16
        result["runtime"] = {"python": os.sys.version, "torch": torch.__version__, "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0), "dtype": str(dtype)}

        load_started = time.perf_counter()
        noise_scheduler = DDPMScheduler.from_pretrained(str(model), subfolder="scheduler")
        vae = AutoencoderKL.from_pretrained(str(model), subfolder="vae", torch_dtype=dtype)
        clip_image_encoder = CLIPVisionModelWithProjection.from_pretrained(str(model), subfolder="image_encoder", torch_dtype=dtype)
        unet = UNet2DConditionModel.from_pretrained(str(model), subfolder="unet", torch_dtype=dtype)
        controlnet = ControlNetModel.from_pretrained(str(model), subfolder="controlnet", torch_dtype=dtype)
        refer_clip_proj = CCProjection.from_pretrained(str(model), subfolder="projection", clip_image_encoder=clip_image_encoder)
        refer_clip_proj.to(dtype=dtype)
        for module in (vae, clip_image_encoder, unet, controlnet, refer_clip_proj):
            module.requires_grad_(False)
        pipeline = BackHallucinationPipeline(
            vae=vae,
            clip_image_encoder=clip_image_encoder,
            unet=unet,
            controlnet=controlnet,
            scheduler=noise_scheduler,
            refer_clip_proj=refer_clip_proj,
            torch_dtype=dtype,
        )
        pipeline.scheduler = UniPCMultistepScheduler.from_config(pipeline.scheduler.config)
        pipeline.set_progress_bar_config(disable=True)
        offload = False
        try:
            # SiTH's pinned diffusers API exposes the inherited offload
            # helper without the newer `device=` keyword.
            pipeline.enable_model_cpu_offload()
            offload = True
        except Exception as exc:
            result["cpuOffloadError"] = repr(exc)
            pipeline = pipeline.to(device)
        result["loadSeconds"] = round(time.perf_counter() - load_started, 3)
        result["cpuOffload"] = offload

        image = Image.open(reference).convert("RGB").resize((args.resolution, args.resolution), Image.Resampling.LANCZOS)
        rgb_01 = TF.to_tensor(image)
        # SiTH's official dataset keeps the diffusion/VAE input at the
        # requested square resolution but sends a separate 224x224 CLIP
        # image normalized with CLIP's pretrained statistics.
        clip_rgb = TF.resize(rgb_01, [224, 224], interpolation=transforms.InterpolationMode.BILINEAR)
        clip_rgb = TF.normalize(
            clip_rgb,
            [0.48145466, 0.4578275, 0.40821073],
            [0.26862954, 0.26130258, 0.27577711],
        )
        rgb = rgb_01 * 2.0 - 1.0
        src_image = rgb.unsqueeze(0)
        src_ori_image = src_image.clone()
        src_clip_image = clip_rgb.unsqueeze(0)
        uv_y, uv_x = torch.meshgrid(
            torch.linspace(-1.0, 1.0, args.resolution),
            torch.linspace(-1.0, 1.0, args.resolution),
            indexing="ij",
        )
        tgt_uv = torch.stack([uv_x, uv_y, torch.zeros_like(uv_x)], dim=0).unsqueeze(0)
        tgt_mask = torch.ones((1, 1, args.resolution, args.resolution), dtype=torch.float32)
        view_cond = torch.tensor([0.0, 0.0, -1.0, 0.0], dtype=torch.float32).view(1, 4, 1, 1).repeat(1, 1, args.resolution, args.resolution)
        inputs = {"src_image": src_clip_image, "src_ori_image": src_ori_image, "tgt_uv": tgt_uv, "tgt_mask": tgt_mask, "view_cond": view_cond}

        for i in range(args.samples):
            seed = args.seed + i
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            sample = {"index": i, "seed": seed, "status": "STARTED"}
            try:
                generator = torch.Generator(device=device).manual_seed(seed)
                with torch.inference_mode(), torch.autocast("cuda", dtype=dtype):
                    images = pipeline.forward(
                        inputs,
                        generator=generator,
                        num_inference_steps=args.steps,
                        guidance_scale=3.5,
                        controlnet_conditioning_scale=1.0,
                        num_images_per_prompt=1,
                    )
                path = output / f"sith_back_{i:02d}_seed_{seed}.png"
                Image.fromarray((images[0] * 255).astype(np.uint8)).save(path)
                sample.update({"status": "GENERATED", "path": str(path), "elapsedSeconds": round(time.perf_counter() - started, 3), "peakAllocatedMiB": round(torch.cuda.max_memory_allocated() / 1024**2, 2), "peakReservedMiB": round(torch.cuda.max_memory_reserved() / 1024**2, 2)})
            except Exception as exc:
                sample.update({"status": "FAILED", "elapsedSeconds": round(time.perf_counter() - started, 3), "error": repr(exc), "traceback": traceback.format_exc()})
            result["samples"].append(sample)
        result["status"] = "GENERATED" if any(s["status"] == "GENERATED" for s in result["samples"]) else "FAILED"
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = repr(exc)
        result["traceback"] = traceback.format_exc()
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "result": str(result_path), "generated": sum(1 for s in result.get("samples", []) if s.get("status") == "GENERATED")}, ensure_ascii=False))
    return 0 if result["status"] == "GENERATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

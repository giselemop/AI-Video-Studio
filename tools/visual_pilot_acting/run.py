"""Offline queue-owned LivePortrait pilot. --preflight never loads a model."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time

DATA = Path(r"C:\install\AI\Data").resolve()
ROOT = Path(r"C:\install\AI\LivePortraitPilot").resolve()
SETUP = DATA / "VisualValidation20261024" / "acting-setup"
OFFICIAL = ROOT / "official"
COMMIT = "9b294b3d0536135442ea73cb01e6cb3ca7029dd3"
FFMPEG = Path(r"C:\install\FFmpeg\bin\ffmpeg.exe")
FFPROBE = Path(r"C:\install\FFmpeg\bin\ffprobe.exe")


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def governed(path: str, exists: bool = True) -> Path:
    p = Path(path).resolve()
    if not p.is_relative_to(DATA) or p == DATA:
        raise ValueError("All media and receipts must stay inside the governed Data directory")
    if exists and not p.is_file():
        raise FileNotFoundError(p)
    return p


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def probe(path: Path) -> dict:
    p = subprocess.run([str(FFPROBE), "-v", "error", "-count_frames", "-show_streams", "-show_format",
                        "-of", "json", str(path)], check=True, capture_output=True, text=True)
    return json.loads(p.stdout)


def verify_install() -> dict:
    if Path(sys.prefix).resolve() != ROOT / "venv":
        raise RuntimeError("The selected pilot must run in its isolated venv")
    dependency_lock = json.loads((SETUP / "dependency-lock.json").read_text(encoding="utf-8"))
    if dependency_lock["pythonVersion"] != platform.python_version():
        raise RuntimeError("Pinned pilot Python version changed")
    for package, version in dependency_lock["packages"].items():
        if importlib.metadata.version(package) != version:
            raise RuntimeError(f"Pinned pilot dependency changed: {package}")
    if not (OFFICIAL / "inference.py").is_file():
        raise RuntimeError("Pinned official source is missing")
    source_receipt = json.loads((SETUP / "download-source.json").read_text(encoding="utf-8"))
    if source_receipt["sourceCommit"] != COMMIT:
        raise RuntimeError("Official source revision mismatch")
    for item in source_receipt["files"]:
        p = Path(item["path"]).resolve()
        if not p.is_relative_to(OFFICIAL) or sha(p) != item["sha256"]:
            raise RuntimeError("Pinned official source content changed")
    model_receipt = json.loads((SETUP / "download-models.json").read_text(encoding="utf-8"))
    for item in model_receipt["files"]:
        p = Path(item["path"]).resolve()
        if not p.is_relative_to(OFFICIAL / "pretrained_weights") or sha(p) != item["sha256"]:
            raise RuntimeError("Pinned model content changed")
    # Imports only: no CUDA check, model deserialization, face detector, or inference.
    import torch
    import cv2
    import onnxruntime
    # Lock the detector/landmark backend before importing official classes that
    # subclass InferenceSession; no CUDA runtime is used by this ONNX package.
    if not getattr(onnxruntime, "_pilot_cpu_locked", False):
        original_session = onnxruntime.InferenceSession
        class CpuOnnxSession(original_session):
            def __init__(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs):
                super().__init__(path_or_bytes, sess_options=sess_options,
                                 providers=["CPUExecutionProvider"], **kwargs)
        onnxruntime.InferenceSession = CpuOnnxSession
        onnxruntime._pilot_cpu_locked = True
    from src.live_portrait_pipeline import LivePortraitPipeline
    return {"status": "Passed", "sourceCommit": COMMIT, "python": sys.version,
            "torch": torch.__version__, "onnxruntime": onnxruntime.__version__,
            "cv2": cv2.__version__, "modelFileCount": len(model_receipt["files"]),
            "dependencyLockSha256": sha(SETUP / "dependency-lock.json"),
            "onnxExecutionProvider": "CPUExecutionProvider (explicit pilot configuration)",
            "gpuInferenceStarted": False, "modelLoaded": False,
            "licenseStatus": "ExperimentalNonCommercialInsightFaceWeights",
            "contentReview": "NeedReview", "publicationStatus": "Blocked", "cloudCalls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    receipt_path = governed(args.receipt, exists=False)
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
    sys.path.insert(0, str(OFFICIAL))
    os.environ["PATH"] = str(FFMPEG.parent) + os.pathsep + os.environ.get("PATH", "")
    # Hard block URL-based downloads used by optional dependency fallbacks.
    import urllib.request
    def no_download(*unused_args, **unused_kwargs):
        raise RuntimeError("Network requests are disabled during local inference/preflight")
    urllib.request.urlopen = no_download
    urllib.request.urlretrieve = no_download
    import socket
    socket.create_connection = no_download
    socket.socket.connect = no_download
    socket.socket.connect_ex = no_download
    # requests/urllib3 ultimately reach these socket methods; do not permit an
    # optional missing checkpoint to trigger a hidden HTTP download.
    install = verify_install()
    if args.preflight:
        write_new(receipt_path, install)
        print(json.dumps(install), flush=True)
        return
    if not args.manifest:
        raise ValueError("--manifest is required for inference")
    request = json.loads(governed(args.manifest).read_text(encoding="utf-8-sig"))
    source = governed(request["sourcePath"])
    driving = governed(request["drivingPath"])
    output_dir = governed(request["outputDirectory"], exists=False)
    if output_dir.exists():
        raise FileExistsError("Output directory must be a new private task directory")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Pilot source must be an image, not a self-driving source video")
    if driving.suffix.lower() != ".mp4":
        raise ValueError("Only local MP4 driving media is accepted; pickle templates are rejected")
    source_hash, driving_hash = sha(source), sha(driving)
    if source_hash != request["sourceSha256"] or driving_hash != request["drivingSha256"]:
        raise ValueError("Source or driving media hash mismatch")
    duration = float(request.get("durationSeconds", 2.0))
    start = float(request.get("drivingStartSeconds", 0))
    region = request.get("animationRegion", "exp")
    multiplier = float(request.get("drivingMultiplier", 0.6))
    if not 2 <= duration <= 3 or not 0 <= start <= 60 or region not in {"exp", "all"} or not 0.1 <= multiplier <= 1:
        raise ValueError("Pilot is limited to 2–3 seconds, exp/all regions, and a 0.1–1 multiplier")
    if shutil.disk_usage(DATA).free < 20 * 1024 ** 3:
        raise RuntimeError("Inference refused: less than 20 GiB free disk")
    info = probe(driving)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    if start + duration > float(info["format"]["duration"]) + 0.02:
        raise ValueError("Driving video is shorter than the requested segment")
    output_dir.mkdir(parents=True, exist_ok=False)
    # Keep FFmpeg/output basenames short on Windows while retaining the frozen
    # original source path and digest in the receipt.
    local_source = output_dir / ("source-input" + source.suffix.lower())
    shutil.copyfile(source, local_source)
    if sha(local_source) != source_hash:
        raise RuntimeError("Private source copy differs from the frozen original")
    clip = output_dir / "driving-input.mp4"
    # Preserve driving cadence and duration. No external audio or padding is used.
    subprocess.run([str(FFMPEG), "-nostdin", "-v", "error", "-i", str(driving), "-ss", str(start),
                    "-t", str(duration), "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    str(clip)], check=True)
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(clip))
    previous, changes, count = None, [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)
        if previous is not None:
            changes.append(float(np.abs(gray - previous).mean()))
        previous = gray
        count += 1
    cap.release()
    if count < 40 or not changes or max(changes) < 0.05:
        raise ValueError("Driving input is empty or nearly static; no acting benefit can be claimed")
    from src.config.argument_config import ArgumentConfig
    from src.config.inference_config import InferenceConfig
    from src.config.crop_config import CropConfig
    from src.live_portrait_pipeline import LivePortraitPipeline
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("Selected pilot requires CUDA; CPU fallback is disabled")
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    if free_bytes < 1024 ** 3:
        raise RuntimeError("Insufficient free VRAM; queue must wait without falling back")
    torch.manual_seed(20261024)
    torch.cuda.reset_peak_memory_stats()
    config = ArgumentConfig(source=str(local_source), driving=str(clip), output_dir=str(output_dir / "official-output"),
                            animation_region=region, driving_multiplier=multiplier,
                            flag_crop_driving_video=True, flag_pasteback=True, flag_stitching=True,
                            flag_relative_motion=True, flag_eye_retargeting=False,
                            flag_lip_retargeting=False, flag_do_torch_compile=False)
    def select(cls):
        return cls(**{k: v for k, v in vars(config).items() if hasattr(cls, k)})
    started = time.perf_counter()
    pipeline = LivePortraitPipeline(inference_cfg=select(InferenceConfig), crop_cfg=select(CropConfig))
    output = pipeline.execute(config)
    torch.cuda.synchronize()
    candidates = sorted((output_dir / "official-output").glob("*.mp4"))
    primary = [p for p in candidates if not p.stem.endswith("_concat")]
    if len(primary) != 1:
        raise RuntimeError(f"Expected one primary animation output, found {len(primary)}")
    result = probe(primary[0])
    stream = next(s for s in result["streams"] if s["codec_type"] == "video")
    if int(stream["nb_read_frames"]) != count:
        raise RuntimeError("Output frame count differs from trimmed driving input")
    if source_hash != sha(source) or driving_hash != sha(driving):
        raise RuntimeError("An original input was modified")
    verify_install()  # Require official source and model hashes unchanged after inference.
    receipt = {**install, "gpuInferenceStarted": True, "modelLoaded": True,
               "provider": "OfficialLivePortraitLocalPilot", "durationSeconds": float(result["format"]["duration"]),
               "sourcePath": str(source), "sourceSha256": source_hash, "drivingPath": str(driving),
               "drivingSha256": driving_hash, "driverOrigin": request.get("driverOrigin", "existing-local-generated-video"),
               "driverIsNewHumanPerformance": False, "animationRegion": region, "drivingMultiplier": multiplier,
               "drivingFrames": count, "drivingMeanFrameDifference": float(np.mean(changes)),
               "outputPath": str(primary[0]), "outputSha256": sha(primary[0]),
               "width": stream["width"], "height": stream["height"], "fps": stream["avg_frame_rate"],
               "frames": int(stream["nb_read_frames"]), "totalSeconds": time.perf_counter() - started,
               "peakAllocatedMiB": torch.cuda.max_memory_allocated() / 1024 ** 2,
               "peakReservedMiB": torch.cuda.max_memory_reserved() / 1024 ** 2,
               "gpu": torch.cuda.get_device_name(), "initialFreeVramMiB": free_bytes / 1024 ** 2,
               "initialTotalVramMiB": total_bytes / 1024 ** 2,
               "audioDisposition": "picture-only; retain original audio separately without retiming",
               "qualityImprovement": "Unverified; requires A/B review of new-source reenactment"}
    receipt["sourceAndModelHashesPreserved"] = True
    write_new(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()

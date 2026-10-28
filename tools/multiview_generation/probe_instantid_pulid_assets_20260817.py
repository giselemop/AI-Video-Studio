"""Probe the deployed ComfyUI adapter loaders without fabricating a generation result."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


def file_record(path: Path, expected: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "expectedBytes": expected}
    if path.is_file():
        result["bytes"] = path.stat().st_size
        result["completeBySize"] = expected is None or path.stat().st_size == expected
        if path.stat().st_size <= 3 * 1024 * 1024 * 1024:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            result["sha256"] = digest.hexdigest()
    else:
        result.update({"bytes": 0, "completeBySize": False, "sha256": None})
    return result


def call_probe(name: str, func: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        value = func()
        return {"name": name, "status": "PASS", "durationMs": round((time.perf_counter() - started) * 1000, 1), "resultType": type(value).__name__, "error": None}
    except Exception as exc:  # keep exact blocker text in evidence, without credentials
        return {"name": name, "status": "BLOCKED_OR_FAILED", "durationMs": round((time.perf_counter() - started) * 1000, 1), "resultType": None, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--skip-eva", action="store_true", help="Do not trigger the native node's automatic 856MiB EVA CLIP download")
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    sys.path.insert(0, r"C:\install\AI\ComfyUI")
    sys.path.insert(0, r"C:\install\AI\ComfyUI\custom_nodes")
    sys.path.insert(0, r"C:\install\AI\IdentityWorker\vendor-src\insightface-0.7.3")
    import folder_paths
    folder_paths.models_dir = r"C:\install\AI\Models"
    results: list[dict[str, Any]] = []
    import ComfyUI_InstantID_20260817.InstantID as instantid
    import PuLID_ComfyUI_20260817.pulid as pulid

    results.append(call_probe("InstantIDModelLoader.ip-adapter.bin", lambda: instantid.InstantIDModelLoader().load_model("ip-adapter.bin")))
    results.append(call_probe("InstantIDFaceAnalysis.antelopev2.CPU", lambda: instantid.InstantIDFaceAnalysis().load_insight_face("CPU")))
    results.append(call_probe("PulidModelLoader.ip-adapter_pulid_sdxl_fp16.safetensors", lambda: pulid.PulidModelLoader().load_model("ip-adapter_pulid_sdxl_fp16.safetensors")))
    results.append(call_probe("PulidInsightFaceLoader.antelopev2.CPU", lambda: pulid.PulidInsightFaceLoader().load_insightface("CPU")))
    if args.skip_eva:
        results.append({"name": "PulidEvaClipLoader", "status": "BLOCKED_DEPENDENCY_NOT_DOWNLOADED", "durationMs": 0.0, "resultType": None, "error": "Skipped by controlled probe; native loader would auto-download EVA02_CLIP_L_336_psz14_s6B.pt (~856MiB)."})
    else:
        results.append(call_probe("PulidEvaClipLoader", lambda: pulid.PulidEvaClipLoader().load_eva_clip()))
    assets = {
        "instantIdAdapter": file_record(Path(r"C:\install\AI\Models\instantid\ip-adapter.bin"), 1691134141),
        "instantIdControlNet": file_record(Path(r"C:\install\AI\Models\controlnet\instantid\diffusion_pytorch_model.safetensors"), 2502139136),
        "pulidAdapter": file_record(Path(r"C:\install\AI\Models\pulid\ip-adapter_pulid_sdxl_fp16.safetensors"), 791372856),
        "sdxlBase": file_record(Path(r"C:\install\AI\Models\checkpoints\sdxl\sd_xl_base_1.0.safetensors"), 6938078334),
        "antelopeZip": file_record(Path(r"C:\install\AI\Models\InsightFace\downloads\antelopev2.zip"), 360662982),
        "antelopeFolder": {"path": r"C:\install\AI\Models\InsightFace\models\antelopev2", "files": sorted(p.name for p in Path(r"C:\install\AI\Models\InsightFace\models\antelopev2").glob("*.onnx"))},
    }
    evidence = {
        "schemaVersion": "2026-08-17.instantid-pulid-asset-probe.v1",
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runRoot": str(run_root),
        "python": sys.version,
        "assets": assets,
        "probes": results,
        "interpretation": "A loader PASS proves the installed node and adapter asset can initialize; it does not prove identity-view quality. A generation benchmark is recorded separately and only when an SDXL workflow completes with an output image.",
    }
    (run_root / "adapter-asset-probe.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

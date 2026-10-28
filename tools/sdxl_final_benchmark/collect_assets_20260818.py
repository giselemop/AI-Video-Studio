"""Collect the before/after asset manifest for the 2026-08-18 SDXL decision run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHUNK = 128 * 1024 * 1024
RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def range_state(path: Path, expected_size: int) -> dict[str, Any]:
    target_bytes = path.stat().st_size if path.is_file() else 0
    original: list[dict[str, Any]] = []
    for fragment in sorted(path.parent.glob(path.name + ".range[0-9][0-9][0-9]")):
        suffix = fragment.name.rsplit(".range", 1)[-1]
        index = int(suffix)
        start = target_bytes + index * CHUNK
        expected = max(0, min(CHUNK, expected_size - start))
        original.append({"index": index, "path": str(fragment), "bytes": fragment.stat().st_size, "expectedBytes": expected, "status": "VALID" if fragment.stat().st_size == expected else "PARTIAL_OR_INVALID"})
    recovered: list[dict[str, Any]] = []
    for fragment in sorted(path.parent.glob(path.name + ".range[0-9][0-9][0-9].recovered")):
        suffix = fragment.name.split(".range", 1)[-1].split(".", 1)[0]
        index = int(suffix)
        start = target_bytes + index * CHUNK
        expected = max(0, min(CHUNK, expected_size - start))
        recovered.append({"index": index, "path": str(fragment), "bytes": fragment.stat().st_size, "expectedBytes": expected, "status": "VALID" if fragment.stat().st_size == expected else "PARTIAL_OR_INVALID"})
    return {"prefixBytes": target_bytes, "chunkBytes": CHUNK, "originalFragments": original, "recoveredFragments": recovered}


def spec(name: str, path: str, expected_size: int, expected_sha: str, source: str, revision: str | None = None) -> dict[str, Any]:
    target = Path(path)
    exists = target.is_file()
    actual_size = target.stat().st_size if exists else 0
    actual_sha = digest(target) if exists and actual_size <= 8 * 1024 * 1024 * 1024 else None
    if exists and actual_size == expected_size and actual_sha and actual_sha.lower() == expected_sha.lower():
        status = "COMPLETE_VALIDATED"
    elif exists and actual_size > 0:
        status = "PARTIAL_RESUMABLE"
    elif exists:
        status = "UNKNOWN"
    else:
        status = "MISSING"
    record: dict[str, Any] = {
        "name": name,
        "path": str(target),
        "size": actual_size,
        "expectedSize": expected_size,
        "sha256": actual_sha,
        "expectedSha256": expected_sha,
        "status": status,
        "source": source,
        "skipDownload": status == "COMPLETE_VALIDATED",
    }
    if target.is_file() and actual_size < expected_size:
        record["resume"] = range_state(target, expected_size)
    if revision:
        record["revision"] = revision
    return record


def git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", "-C", r"C:\install\AI\VideoStudio", *args], text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(RUN_ROOT))
    parser.add_argument("--phase", choices=["before", "after"], default="before")
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    hf_revision = "11afd202f2ae80869d6cef18b1ec775e79bd8d12"
    assets = [
        spec("SDXL base", r"C:\install\AI\Models\checkpoints\sdxl\sd_xl_base_1.0.safetensors", 6938078334, "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b", "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"),
        spec("InstantID adapter", r"C:\install\AI\Models\instantid\ip-adapter.bin", 1691134141, "02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1", "https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin"),
        spec("InstantID ControlNet", r"C:\install\AI\Models\controlnet\instantid\diffusion_pytorch_model.safetensors", 2502139136, "c8127be9f174101ebdafee9964d856b49b634435cf6daa396d3f593cf0bbbb05", "https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors"),
        spec("PuLID adapter", r"C:\install\AI\Models\pulid\ip-adapter_pulid_sdxl_fp16.safetensors", 791372856, "b258a5cd2c0c7d35f4d3e59909d7648498686afae4d0c74917e9c47d7704fbf5", "https://huggingface.co/huchenlei/ipadapter_pulid/resolve/main/ip-adapter_pulid_sdxl_fp16.safetensors"),
        spec("antelopev2 archive", r"C:\install\AI\Models\InsightFace\downloads\antelopev2.zip", 360662982, "8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5", "https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip"),
        spec("PuLID EVA02 CLIP L 336", rf"C:\install\AI\Models\hf_cache\models--QuanSun--EVA-CLIP\snapshots\{hf_revision}\EVA02_CLIP_L_336_psz14_s6B.pt", 856461210, "84c3a17a228c567a155259b2245b0b59072bf7da510260a0a02ec54de6d50b05", "https://huggingface.co/QuanSun/EVA-CLIP/resolve/main/EVA02_CLIP_L_336_psz14_s6B.pt", hf_revision),
    ]
    existing = json.loads((run_root / "02-existing-assets.json").read_text(encoding="utf-8-sig")) if args.phase == "after" and (run_root / "02-existing-assets.json").exists() else None
    manifest = {
        "schemaVersion": "2026-08-18.sdxl-existing-assets.v1",
        "capturedAt": now(),
        "phase": args.phase,
        "runRoot": str(run_root),
        "git": {"branch": git(["branch", "--show-current"]), "head": git(["rev-parse", "HEAD"]), "dirtyCount": len([line for line in git(["status", "--porcelain=v1"]).splitlines() if line.strip()])},
        "assets": assets,
        "noDuplicateDownloadRule": "COMPLETE_VALIDATED assets are SKIP_DOWNLOAD and are never re-fetched.",
    }
    (run_root / "02-existing-assets.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    before_assets = existing.get("assets") if existing else assets
    resume = {
        "schemaVersion": "2026-08-18.sdxl-asset-resume.v1",
        "capturedAt": now(),
        "phase": args.phase,
        "runRoot": str(run_root),
        "before": before_assets,
        "current": assets,
        "actions": [{"name": item["name"], "action": "SKIP_DOWNLOAD" if item["status"] == "COMPLETE_VALIDATED" else ("RESUME_RANGE_WITH_RECOVERED_SIDECAR" if item["status"] == "PARTIAL_RESUMABLE" else "DOWNLOAD_OFFICIAL_HTTPS_ASSET"), "status": item["status"]} for item in assets],
        "preservation": "Original partial and valid range files are preserved; incomplete ranges are resumed into .recovered sidecars; final target replacement only follows size+SHA validation.",
    }
    (run_root / "03-asset-resume-and-validation.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

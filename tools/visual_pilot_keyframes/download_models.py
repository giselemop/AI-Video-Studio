"""Download only the three approved FLUX.2 Klein 4B artifacts; never run inference."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.request
import urllib.error


MODEL_ROOT = Path(r"C:\install\AI\Models\Flux2Klein4B")
EVIDENCE_ROOT = Path(r"C:\install\AI\Data\VisualValidation20261024\keyframes-setup")
ARTIFACTS = [
    {
        "role": "diffusion_models",
        "repo": "black-forest-labs/FLUX.2-klein-4b-fp8",
        "remote": "flux-2-klein-4b-fp8.safetensors",
        "name": "flux-2-klein-4b-fp8.safetensors",
        "size": 4070624520,
        "sha256": "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6",
    },
    {
        "role": "text_encoders",
        "repo": "Comfy-Org/flux2-klein-4B",
        "remote": "split_files/text_encoders/qwen_3_4b.safetensors",
        "name": "qwen_3_4b.safetensors",
        "size": 8044982048,
        "sha256": "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a",
    },
    {
        "role": "vae",
        "repo": "Comfy-Org/flux2-klein-4B",
        "remote": "split_files/vae/flux2-vae.safetensors",
        "name": "flux2-vae.safetensors",
        "size": 336211292,
        "sha256": "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3",
    },
]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def write_new(path, value):
    if not path.exists():
        path.write_bytes(value)


def download_ranges(url, target, expected_size, workers):
    prefix = target.with_suffix(target.suffix + ".partial")
    prefix_size = prefix.stat().st_size if prefix.exists() else 0
    if prefix_size > expected_size:
        raise RuntimeError("Partial artifact exceeds expected size: " + str(prefix))
    parts = target.with_suffix(target.suffix + ".parts")
    parts.mkdir(exist_ok=True)
    chunk_size = 64 * 1024 * 1024
    ranges = [(start, min(start + chunk_size, expected_size) - 1) for start in range(prefix_size, expected_size, chunk_size)]
    progress = parts / "ranges.json"
    layout = {"prefix_bytes": prefix_size, "expected_bytes": expected_size, "ranges": ranges}
    if progress.exists() and json.loads(progress.read_text(encoding="utf-8")) != json.loads(json.dumps(layout)):
        raise RuntimeError("Saved range layout differs; refusing unsafe resume")
    progress.write_text(json.dumps(layout), encoding="utf-8")

    def download_one(bounds):
        start, end = bounds
        part = parts / f"{start:012d}-{end:012d}.part"
        expected = end - start + 1
        for attempt in range(4):
            present = part.stat().st_size if part.exists() else 0
            if present > expected:
                raise RuntimeError("Range file exceeds expected size")
            if present == expected:
                return part
            request = urllib.request.Request(url, headers={"Range": f"bytes={start + present}-{end}"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start + present}-{end}/"):
                        raise RuntimeError("Server did not honor the exact requested byte range")
                    with part.open("ab" if part.exists() else "xb") as output:
                        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                            output.write(block)
                if part.stat().st_size == expected:
                    return part
            except (OSError, urllib.error.URLError):
                if attempt == 3:
                    raise
            time.sleep(2 * (attempt + 1))
        raise RuntimeError("Range download remained incomplete")

    completed = prefix_size
    last_report = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_one, bounds): bounds for bounds in ranges}
        for future in as_completed(futures):
            future.result()
            start, end = futures[future]
            completed += end - start + 1
            if time.monotonic() - last_report > 15:
                print(json.dumps({"name": target.name, "bytes": completed, "expected": expected_size, "range_workers": workers}), flush=True)
                last_report = time.monotonic()
    if shutil.disk_usage(target.parent).free - expected_size < 30 * 1024**3:
        raise RuntimeError("Assembly refused: must retain 30 GiB free; downloaded ranges retained")
    combined = target.with_suffix(target.suffix + ".assembled")
    with combined.open("wb") as output:
        if prefix_size:
            with prefix.open("rb") as source:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
        for start, end in ranges:
            with (parts / f"{start:012d}-{end:012d}.part").open("rb") as source:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
    return combined, prefix, parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly download the approved artifacts")
    parser.add_argument("--source", choices=["huggingface", "modelscope"], default="huggingface")
    parser.add_argument("--artifact", choices=["all", "diffusion_models", "text_encoders", "vae"], default="all")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--proxy", choices=["http://127.0.0.1:7897"])
    args = parser.parse_args()
    if args.proxy:
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy})))
    selected = [a for a in ARTIFACTS if args.artifact == "all" or a["role"] == args.artifact]
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    required = sum(a["size"] for a in selected)
    report = {"artifacts": selected, "required_bytes": required, "free_bytes": shutil.disk_usage(MODEL_ROOT.parent).free, "source": args.source, "process_proxy": args.proxy}
    print(json.dumps(report, ensure_ascii=True), flush=True)
    if not args.download:
        return

    revisions = {}
    for repo in sorted({a["repo"] for a in ARTIFACTS}):
        info = json.loads(fetch("https://huggingface.co/api/models/" + repo))
        revisions[repo] = info["sha"]
        prefix = repo.replace("/", "__")
        write_new(EVIDENCE_ROOT / (prefix + "__model_info.json"), json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"))
        write_new(EVIDENCE_ROOT / (prefix + "__README.md"), fetch(f"https://huggingface.co/{repo}/raw/{info['sha']}/README.md"))
    write_new(EVIDENCE_ROOT / "FLUX2-Klein-LICENSE.md", fetch(f"https://huggingface.co/{ARTIFACTS[0]['repo']}/raw/{revisions[ARTIFACTS[0]['repo']]}/LICENSE.md"))
    write_new(EVIDENCE_ROOT / "Qwen3-4B-LICENSE", fetch("https://huggingface.co/Qwen/Qwen3-4B/raw/main/LICENSE"))
    write_new(EVIDENCE_ROOT / "official_image_edit_distilled.json", fetch("https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/image_flux2_klein_image_edit_4b_distilled.json"))
    write_new(EVIDENCE_ROOT / "official_klein_guide.mdx", fetch("https://raw.githubusercontent.com/Comfy-Org/docs/main/tutorials/flux/flux-2-klein.mdx"))

    remaining = sum(a["size"] for a in selected if not (MODEL_ROOT / a["role"] / a["name"]).exists())
    free = shutil.disk_usage(MODEL_ROOT.parent).free
    if free - remaining < 30 * 1024**3:
        raise RuntimeError("Download refused: must retain 30 GiB free for the existing video pipeline")
    manifest = {"status": "Downloading", "model_root": str(MODEL_ROOT), "revisions": revisions, "source": args.source, "process_proxy": args.proxy, "artifacts": []}
    manifest_path = EVIDENCE_ROOT / ("download_manifest.json" if args.artifact == "all" else "download_manifest_" + args.artifact + ".json")
    for artifact in selected:
        target = MODEL_ROOT / artifact["role"] / artifact["name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        prior_parts = target.with_suffix(target.suffix + ".parts")
        prior_prefix = target.with_suffix(target.suffix + ".partial")
        resumed_bytes = (prior_prefix.stat().st_size if prior_prefix.exists() else 0) + sum(p.stat().st_size for p in prior_parts.glob("*.part"))
        if args.source == "modelscope":
            url = f"https://modelscope.cn/models/{artifact['repo']}/resolve/master/{artifact['remote']}"
        else:
            url = f"https://huggingface.co/{artifact['repo']}/resolve/{revisions[artifact['repo']]}/{artifact['remote']}"
        if target.exists():
            if target.stat().st_size != artifact["size"] or file_hash(target) != artifact["sha256"]:
                raise RuntimeError("Existing artifact differs; refusing overwrite: " + str(target))
        else:
            combined, prefix, parts = download_ranges(url, target, artifact["size"], args.workers)
            if combined.stat().st_size != artifact["size"] or file_hash(combined) != artifact["sha256"]:
                raise RuntimeError("Artifact hash/size failed; downloaded files retained: " + str(combined))
            os.rename(combined, target)
            if prefix.exists():
                prefix.unlink()
            for part in parts.glob("*.part"):
                part.unlink()
            (parts / "ranges.json").unlink()
            parts.rmdir()
        row = {**artifact, "path": str(target), "revision": revisions[artifact["repo"]], "url": url, "resumed_bytes_before": resumed_bytes, "verified": True}
        manifest["artifacts"].append(row)
        print(json.dumps({"verified": artifact["name"], "bytes": artifact["size"]}), flush=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["status"] = "Passed"
    manifest["free_bytes_after"] = shutil.disk_usage(MODEL_ROOT).free
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("KLEIN_MODEL_DOWNLOAD_VERIFIED", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

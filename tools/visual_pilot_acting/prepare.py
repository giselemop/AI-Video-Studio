"""Prepare an isolated official LivePortrait pilot. Never starts inference."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\install\AI\LivePortraitPilot")
EVIDENCE = Path(r"C:\install\AI\Data\VisualValidation20261024\acting-setup")
COMMIT = "9b294b3d0536135442ea73cb01e6cb3ca7029dd3"
BUNDLED_PYTHON = Path(os.environ.get("AI_VIDEO_STUDIO_BOOTSTRAP_PYTHON", sys.executable))
class LoggedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlparse(newurl).hostname
        print(f"download redirect host: {host}", flush=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LoggedRedirect())


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        temp = path.with_suffix(path.suffix + ".partial")
        with opener.open(url, timeout=120) as response, temp.open("wb") as dst:
            shutil.copyfileobj(response, dst, 1024 * 1024)
        temp.replace(path)
    return {"url": url, "path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def download_ranges(url: str, path: Path, size: int, expected_sha256: str) -> dict:
    """Bounded public Range transfer; validate the final pinned SHA separately."""
    if path.is_file():
        existing_hash = digest(path)
        if existing_hash == expected_sha256:
            return {"url": url, "path": str(path), "bytes": path.stat().st_size, "sha256": existing_hash,
                    "cacheHit": True, "cacheOrigin": "previously downloaded canonical-hash-identical pilot cache"}
        path.replace(path.with_suffix(path.suffix + f".failed-hash-{int(time.time())}"))
    if size > 512 * 1024 ** 2:
        raise RuntimeError("Unexpected human model file size exceeds 512 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".chunked.partial")
    old_partial = path.with_suffix(path.suffix + ".partial")
    prefix_size = old_partial.stat().st_size if old_partial.is_file() else 0
    if prefix_size > size:
        raise RuntimeError("Unexpected legacy partial length")
    if not temporary.is_file():
        with temporary.open("wb") as f:
            if prefix_size:
                with old_partial.open("rb") as prior:
                    shutil.copyfileobj(prior, f, 1024 * 1024)
            f.truncate(size)
    chunk_size = 8 * 1024 * 1024
    state_path = path.with_suffix(path.suffix + ".range-state.json")
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    state_lock = threading.Lock()
    def fetch_chunk(start):
        end = min(size - 1, start + chunk_size - 1)
        saved = state.get(str(start))
        if saved and saved.get("end") == end:
            with temporary.open("rb") as prior:
                prior.seek(start)
                if hashlib.sha256(prior.read(end - start + 1)).hexdigest() == saved["sha256"]:
                    return
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with opener.open(req, timeout=120) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise RuntimeError("Unexpected mirror Range response")
                    body = response.read()
                if len(body) != end - start + 1:
                    raise RuntimeError("Incomplete mirror Range response")
                with temporary.open("r+b") as f:
                    f.seek(start)
                    f.write(body)
                with state_lock:
                    state[str(start)] = {"end": end, "sha256": hashlib.sha256(body).hexdigest()}
                    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
                return
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(attempt + 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(fetch_chunk, range(prefix_size, size, chunk_size)))
    if digest(temporary) != expected_sha256:
        raise RuntimeError("Completed ranged model failed its frozen official SHA256")
    temporary.replace(path)
    return {"url": url, "path": str(path), "bytes": size, "sha256": digest(path), "transfer": "verified-206-range"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["source", "models"], required=True)
    parser.add_argument("--transport", choices=["official", "official-verified-proxy", "modelscope-verified-mirror"], default="official")
    parser.add_argument("--proxy", help="Explicit preparation-only HTTP proxy; never written to system settings")
    args = parser.parse_args()
    if args.proxy:
        global opener
        if args.proxy not in {"http://127.0.0.1:7897", "http://[::1]:7897"}:
            raise ValueError("Only the locally verified preparation proxy is accepted")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy}), LoggedRedirect())
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(ROOT).free < 20 * 1024 ** 3:
        raise RuntimeError("Preparation refused: less than 20 GiB free")
    receipt = {"stage": args.stage, "utc": datetime.now(timezone.utc).isoformat(),
               "sourceCommit": COMMIT, "gpuInferenceStarted": False, "files": []}
    if args.stage == "source":
        prior_manifest = EVIDENCE / "download-source.json"
        if prior_manifest.is_file():
            prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
            if prior.get("sourceCommit") == COMMIT and len(prior.get("files", [])) >= 59:
                if all(digest(Path(f["path"])) == f["sha256"] for f in prior["files"]):
                    print(json.dumps({"status": "Passed", "stage": "source", "cached": True,
                                      "files": len(prior["files"]), "gpuInferenceStarted": False}))
                    return
        with opener.open(f"https://api.github.com/repos/KlingAIResearch/LivePortrait/git/trees/{COMMIT}?recursive=1", timeout=30) as response:
            tree = json.load(response)
        checkout = ROOT / "official"
        roots = {"inference.py", "requirements.txt", "requirements_base.txt", "LICENSE", "readme.md"}
        unused = {"readme.md", "src/gradio_pipeline.py", "src/live_portrait_pipeline_animal.py",
                  "src/utils/animal_landmark_runner.py", "src/utils/check_windows_port.py",
                  "src/utils/viz.py", "src/utils/dependencies/insightface/data/rec_builder.py"}
        selected = [e for e in tree["tree"] if e["type"] == "blob" and
                    (e["path"] in roots or (e["path"].startswith("src/") and "/XPose/" not in e["path"]))
                    and e["path"] not in unused and "/data/images/" not in e["path"]
                    and "/data/objects/" not in e["path"] and "/clip_embedding" not in e["path"]]
        print(f"Downloading {len(selected)} required human-inference files through the official GitHub API", flush=True)
        def fetch_source(entry):
            name = entry["path"]
            target = checkout / name
            if target.is_file() and hashlib.sha1(b"blob " + str(target.stat().st_size).encode() + b"\0" + target.read_bytes()).hexdigest() == entry["sha"]:
                body = target.read_bytes()
            elif entry["size"] == 0:
                body = b""
            else:
                with opener.open(entry["url"], timeout=30) as response:
                    body = base64.b64decode(json.load(response)["content"])
            if hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest() != entry["sha"]:
                raise RuntimeError(f"Official Git blob digest mismatch: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            return {"url": entry["url"], "path": str(target), "bytes": len(body), "sha256": digest(target),
                    "gitBlobSha": entry["sha"]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipt["files"] = list(pool.map(fetch_source, selected))
        if not (ROOT / "venv" / "Scripts" / "python.exe").is_file():
            subprocess.run([str(BUNDLED_PYTHON), "-m", "venv", str(ROOT / "venv")], check=True)
        receipt["runtimeType"] = "isolated-venv-from-configured-bootstrap-python"
        receipt["baseInterpreter"] = str(BUNDLED_PYTHON)
    else:
        if args.transport in {"modelscope-verified-mirror", "official-verified-proxy"}:
            revision = "f49a6df47080f1a36ce46812ec771c72b75dfbc5"
            hf_revision = "82a4fa6735ca58432b6ce39301b4b9ee066dea47"
            # Cross-checked against official Hugging Face file SHA256 pages.
            expected = {
                "liveportrait/base_models/appearance_feature_extractor.pth": "5279bb8654293dbdf327030b397f107237dd9212fb11dd75b83dfb635211ceb5",
                "liveportrait/base_models/motion_extractor.pth": "251e6a94ad667a1d0c69526d292677165110ef7f0cf0f6d199f0e414e8aa0ca5",
                "liveportrait/base_models/spade_generator.pth": "4780afc7909a9f84e24c01d73b31a555ef651521a1fe3b2429bd04534d992aee",
                "liveportrait/base_models/warping_module.pth": "2f61a6f265fe344f14132364859a78bdbbc2068577170693da57fb96d636e282",
                "liveportrait/landmark.onnx": "31d22a5041326c31f19b78886939a634a5aedcaa5ab8b9b951a1167595d147db",
                "liveportrait/retargeting_models/stitching_retargeting_module.pth": "3652d5a3f95099141a56986aaddec92fadf0a73c87a20fac9a2c07c32b28b611",
                "insightface/models/buffalo_l/2d106det.onnx": "f001b856447c413801ef5c42091ed0cd516fcd21f2d6b79635b1e733a7109dbf",
                "insightface/models/buffalo_l/det_10g.onnx": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
            }
            sizes = {"appearance_feature_extractor.pth": 3387959, "motion_extractor.pth": 112545506,
                     "spade_generator.pth": 221813590, "warping_module.pth": 182180086,
                     "landmark.onnx": 114666491, "stitching_retargeting_module.pth": 2393098,
                     "2d106det.onnx": 5030888, "det_10g.onnx": 16923827}
            def fetch_weight(item):
                name, expected_hash = item
                target = ROOT / "official" / "pretrained_weights" / name
                if name.startswith("insightface/"):
                    local = Path(r"C:\install\AI\Models\InsightFace") / Path(name).relative_to("insightface")
                    if local.is_file() and digest(local) == expected_hash:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if not target.is_file():
                            shutil.copyfile(local, target)
                        return {"url": "local-existing-byte-identical-insightface", "originalPath": str(local),
                                "path": str(target), "bytes": target.stat().st_size, "sha256": digest(target)}
                url = (f"https://huggingface.co/KlingTeam/LivePortrait/resolve/{hf_revision}/{name}"
                       if args.transport == "official-verified-proxy" else
                       f"https://modelscope.cn/api/v1/models/AI-ModelScope/LivePortrait/repo?Revision={revision}&FilePath={name}")
                result = download_ranges(url, target, sizes[Path(name).name], expected_hash)
                if result["sha256"] != expected_hash:
                    raise RuntimeError(f"Official SHA256 mismatch for mirrored weight {name}")
                print(f"verified {name}", flush=True)
                result["officialFilePage"] = f"https://huggingface.co/KlingTeam/LivePortrait/blob/main/{name}"
                return result
            with ThreadPoolExecutor(max_workers=1) as pool:
                receipt["files"] = list(pool.map(fetch_weight, expected.items()))
            receipt["modelRepository"] = "KlingTeam/LivePortrait"
            receipt["modelRevision"] = "official-file-SHA256-manifest"
            receipt["transport"] = "AI-ModelScope/LivePortrait verified mirror; existing detector files reused by exact hash"
            receipt["transportRevision"] = revision
            if args.transport == "official-verified-proxy":
                receipt["modelRevision"] = hf_revision
                receipt["transport"] = "official Hugging Face via explicitly verified local proxy; canonical-hash-identical cache reused"
                receipt["transportRevision"] = hf_revision
            receipt["freeDiskBytesAfter"] = shutil.disk_usage(ROOT).free
            (EVIDENCE / "download-models.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            print(json.dumps({"status": "Passed", "stage": "models", "files": len(receipt["files"]),
                              "receiptPath": str(EVIDENCE / "download-models.json")}))
            return
        with opener.open("https://huggingface.co/api/models/KlingTeam/LivePortrait", timeout=120) as response:
            info = json.load(response)
        revision = info["sha"]
        receipt["modelRepository"] = "KlingTeam/LivePortrait"
        receipt["modelRevision"] = revision
        allowed = ("liveportrait/", "insightface/")
        for entry in info["siblings"]:
            name = entry["rfilename"]
            if not name.startswith(allowed) or not name.endswith((".pth", ".onnx")):
                continue
            receipt["files"].append(download(
                f"https://huggingface.co/KlingTeam/LivePortrait/resolve/{revision}/{name}",
                ROOT / "official" / "pretrained_weights" / name))
            print(f"downloaded {name}", flush=True)
        if not receipt["files"]:
            raise RuntimeError("No official human model files discovered")
    receipt["freeDiskBytesAfter"] = shutil.disk_usage(ROOT).free
    (EVIDENCE / f"download-{args.stage}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"status": "Passed", "stage": args.stage, "files": len(receipt["files"]),
                      "downloadBytes": sum(f["bytes"] for f in receipt["files"]),
                      "receiptPath": str(EVIDENCE / f"download-{args.stage}.json")}))


if __name__ == "__main__":
    main()

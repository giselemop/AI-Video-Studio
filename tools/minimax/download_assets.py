"""Download the pinned public H3 assets without replacing existing model files.

Uses bounded range requests, durable chunk checkpoints and full SHA-256 checks.
No API key is used. Interrupted downloads can be resumed with the same command.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from urllib.parse import quote

import requests


def atomic_replace(source: Path, target: Path) -> None:
    """Brief Windows read handles must not abort an otherwise durable download."""
    for attempt in range(12):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(.05 * (attempt + 1))


@contextmanager
def download_lock(root: Path, filename: str = ".minimax-download.lock", conflict: str = "Another model download is already running"):
    """OS-owned lock is released even if a download process is terminated."""
    path = root / filename
    with path.open("a+b") as stream:
        stream.seek(0)
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError(conflict) from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError(conflict) from None
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def target_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Asset target must stay inside the models directory")
    if path.suffix not in {".gguf", ".safetensors"}:
        raise ValueError("Only model data files can be downloaded")
    return path


def download(asset: dict, root: Path, workers: int, chunk_size: int) -> None:
    target = target_path(root, asset["target"])
    size = int(asset["size"])
    expected = asset["sha256"]
    if target.exists():
        if target.stat().st_size != size or digest(target) != expected:
            raise ValueError("Existing model differs from the pinned asset; preserved")
        print(f"verified {target.name}", flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    checkpoint = target.with_name(target.name + ".download.json")
    identity = {"size": size, "sha256": expected, "chunk_size": chunk_size}
    completed: set[int] = set()
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("Download checkpoint belongs to another asset; preserved")
        if not partial.exists() or partial.stat().st_size != size:
            raise ValueError("Checkpoint data is missing or truncated; preserved")
        completed = set(saved.get("completed", []))
    elif partial.exists():
        raise ValueError("Unrecognized partial model exists; preserved")
    else:
        with partial.open("xb") as stream:
            stream.truncate(size)
    ranges = [(index, start, min(start + chunk_size, size) - 1)
              for index, start in enumerate(range(0, size, chunk_size))]
    lock = threading.Lock()

    def save_checkpoint() -> None:
        temporary = checkpoint.with_name(checkpoint.name + ".tmp")
        temporary.write_text(json.dumps({**identity, "completed": sorted(completed)}), encoding="utf-8")
        atomic_replace(temporary, checkpoint)

    save_checkpoint()
    base = f"https://huggingface.co/{asset['repository']}/resolve/{asset['revision']}/{quote(asset['file'], safe='/')}"

    def fetch(item: tuple[int, int, int]) -> None:
        index, start, end = item
        for attempt in range(3):
            try:
                # A unique public URL avoids a cache serving another range's signed redirect.
                url = f"{base}?download=true&range_start={start}"
                with requests.get(url, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=(25, 90)) as response:
                    if response.status_code in {401, 403, 404}:
                        raise PermissionError(f"Public model unavailable: HTTP {response.status_code}")
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Server did not honor the requested byte range")
                    written = 0
                    with partial.open("r+b") as stream:
                        stream.seek(start)
                        for data in response.iter_content(1024 * 1024):
                            if written + len(data) > end - start + 1:
                                raise ValueError("Range response exceeded its declared length")
                            stream.write(data)
                            written += len(data)
                        if written != end - start + 1:
                            raise ValueError("Range response was truncated")
                        stream.flush()
                        os.fsync(stream.fileno())
                with lock:
                    completed.add(index)
                    save_checkpoint()
                    if len(completed) % 8 == 0 or len(completed) == len(ranges):
                        print(f"{target.name}: {len(completed)}/{len(ranges)} chunks", flush=True)
                return
            except (PermissionError, ValueError):
                raise
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError("Public model download failed after 3 attempts") from None
                time.sleep(2 ** attempt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch, (item for item in ranges if item[0] not in completed)))
    if digest(partial) != expected:
        raise ValueError("SHA-256 verification failed; partial file preserved")
    # No other caller should be publishing this same target while the script runs.
    if target.exists():
        raise FileExistsError("Model appeared during download; preserved")
    partial.rename(target)
    checkpoint.unlink()
    print(f"verified {target.name} bytes={size} sha256={expected}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[2] / "config/minimax-local-assets.json")
    parser.add_argument("--models", type=Path, default=Path(r"C:\install\AI\Models"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-mib", type=int, default=64)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.models.resolve()
    assets = json.loads(args.manifest.read_text(encoding="utf-8"))["assets"]
    if not 1 <= args.workers <= 16 or not 1 <= args.chunk_mib <= 128:
        raise ValueError("workers must be 1..16; chunk size must be 1..128 MiB")
    root.mkdir(parents=True, exist_ok=True)
    remaining = sum(int(asset["size"]) for asset in assets
                    if not target_path(root, asset["target"]).exists()
                    and not target_path(root, asset["target"]).with_name(Path(asset["target"]).name + ".part").exists())
    if not args.verify_only and shutil.disk_usage(root).free < remaining + 10 * 1024 ** 3:
        raise RuntimeError("Insufficient disk space including the 10 GiB reserve")
    failures = []
    with download_lock(root):
        for asset in assets:
            try:
                if args.verify_only:
                    path = target_path(root, asset["target"])
                    if not path.exists() or path.stat().st_size != asset["size"] or digest(path) != asset["sha256"]:
                        raise ValueError("Pinned model is missing or not verified")
                    print(f"verified {path.name}", flush=True)
                else:
                    download(asset, root, args.workers, args.chunk_mib * 1024 * 1024)
            except Exception as error:
                failures.append(asset["role"])
                print(f"BLOCKED {asset['role']}: {type(error).__name__}: {error}", flush=True)
    if failures:
        raise SystemExit("Incomplete assets: " + ", ".join(failures))


if __name__ == "__main__":
    main()

"""Resume one public HTTP asset with range requests, then verify its SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def download_range(url: str, path: Path, start: int, end: int, index: int) -> tuple[int, int]:
    headers = {"Range": f"bytes={start}-{end}"}
    temp = path.with_name(path.name + f".range{index:03d}")
    with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError(f"range {index} returned HTTP {response.status_code}, refusing a non-range response")
        content_range = response.headers.get("Content-Range", "")
        if not content_range.startswith(f"bytes {start}-{end}/"):
            raise RuntimeError(f"range {index} returned unexpected Content-Range: {content_range}")
        with temp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    size = temp.stat().st_size
    expected = end - start + 1
    if size != expected:
        raise RuntimeError(f"range {index} wrote {size} bytes, expected {expected}")
    return index, size


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-mib", type=int, default=128)
    args = parser.parse_args()
    target = Path(args.target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = target.stat().st_size if target.exists() else 0
    if prefix > args.size:
        raise RuntimeError(f"existing prefix {prefix} exceeds expected size {args.size}")
    chunk_size = args.chunk_mib * 1024 * 1024
    ranges: list[tuple[int, int, int]] = []
    index = 0
    for start in range(prefix, args.size, chunk_size):
        end = min(args.size - 1, start + chunk_size - 1)
        ranges.append((start, end, index))
        index += 1
    print(f"prefix={prefix} remaining={args.size-prefix} ranges={len(ranges)} workers={args.workers}", flush=True)
    if ranges:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(download_range, args.url, target, start, end, idx) for start, end, idx in ranges]
            completed = 0
            for future in as_completed(futures):
                idx, size = future.result()
                completed += 1
                print(f"range={idx} bytes={size} completed={completed}/{len(ranges)}", flush=True)
    assembled = target.with_name(target.name + ".assembled")
    with assembled.open("wb") as output:
        if prefix:
            with target.open("rb") as existing:
                remaining = prefix
                while remaining:
                    chunk = existing.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("existing prefix ended before its recorded size")
                    output.write(chunk)
                    remaining -= len(chunk)
        for _, _, idx in ranges:
            part = target.with_name(target.name + f".range{idx:03d}")
            with part.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
    if assembled.stat().st_size != args.size:
        raise RuntimeError(f"assembled size {assembled.stat().st_size} does not equal expected {args.size}")
    actual = sha256(assembled)
    print(f"sha256={actual}", flush=True)
    if actual.lower() != args.sha256.lower():
        raise RuntimeError(f"SHA-256 mismatch: expected {args.sha256}, got {actual}")
    os.replace(assembled, target)
    print(f"complete={target} bytes={target.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()

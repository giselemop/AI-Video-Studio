from __future__ import annotations

import argparse
import concurrent.futures
import os
import shutil
import time
from pathlib import Path

import requests


def copy_range(source: Path, destination: Path, start: int, end: int) -> int:
    remaining = end - start + 1
    copied = 0
    with source.open("rb") as src, destination.open("wb") as dst:
        src.seek(start)
        while remaining:
            block = src.read(min(1024 * 1024, remaining))
            if not block:
                break
            dst.write(block)
            copied += len(block)
            remaining -= len(block)
    return copied


def fetch_range(url: str, destination: Path, start: int, end: int, retries: int = 4) -> int:
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    expected = end - start + 1
    for attempt in range(retries):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 120), allow_redirects=True) as response:
                if response.status_code != 206:
                    raise RuntimeError(f"HTTP Range unsupported or rejected: status={response.status_code} content-range={response.headers.get('Content-Range')}")
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {start}-{end}/"):
                    raise RuntimeError(f"Unexpected Content-Range: {content_range}")
                with destination.open("wb") as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            output.write(block)
            if destination.stat().st_size != expected:
                raise RuntimeError(f"Range size mismatch: got={destination.stat().st_size} expected={expected}")
            return expected
        except Exception:
            if destination.exists():
                destination.unlink()
            if attempt + 1 == retries:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one large public file with resumable HTTP ranges.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--chunks", type=int, default=8)
    args = parser.parse_args()

    output = Path(args.output).resolve()
    parts_dir = output.parent / (output.name + ".parallel-parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    existing_length = output.stat().st_size if output.exists() else 0
    if existing_length > args.size:
        raise RuntimeError(f"Existing file is larger than expected: {existing_length} > {args.size}")
    ranges = []
    for index in range(args.chunks):
        start = args.size * index // args.chunks
        end = args.size * (index + 1) // args.chunks - 1 if index + 1 < args.chunks else args.size - 1
        ranges.append((index, start, end))

    def prepare(item: tuple[int, int, int]) -> tuple[int, int]:
        index, start, end = item
        part = parts_dir / f"part-{index:03d}"
        expected = end - start + 1
        if part.exists() and part.stat().st_size == expected:
            return index, expected
        if part.exists():
            part.unlink()
        covered_end = min(existing_length, end + 1)
        copied = 0
        if covered_end > start:
            copied = copy_range(output, part, start, covered_end - 1)
        if covered_end <= end:
            fetched = fetch_range(args.url, part.with_suffix(part.suffix + ".fetch"), max(start, covered_end), end)
            with part.open("ab") as target, (part.with_suffix(part.suffix + ".fetch")).open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            (part.with_suffix(part.suffix + ".fetch")).unlink()
            copied += fetched
        if part.stat().st_size != expected:
            raise RuntimeError(f"Part {index} size mismatch: {part.stat().st_size} != {expected}")
        return index, copied

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.chunks) as executor:
        futures = [executor.submit(prepare, item) for item in ranges]
        for future in concurrent.futures.as_completed(futures):
            index, count = future.result()
            print(f"part={index} bytes={count}", flush=True)

    temporary = output.with_suffix(output.suffix + ".parallel-complete")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("wb") as target:
        for index, _, _ in ranges:
            part = parts_dir / f"part-{index:03d}"
            with part.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    if temporary.stat().st_size != args.size:
        raise RuntimeError(f"Assembled size mismatch: {temporary.stat().st_size} != {args.size}")
    if output.exists():
        backup = output.with_suffix(output.suffix + ".partial-before-parallel")
        if backup.exists():
            backup.unlink()
        os.replace(output, backup)
    os.replace(temporary, output)
    print(f"completed={output} bytes={output.stat().st_size}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

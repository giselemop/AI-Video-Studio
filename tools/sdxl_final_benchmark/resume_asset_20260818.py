"""Resume an asset without overwriting existing partial range fragments.

Existing valid fragments are reused. Existing incomplete fragments are copied to
`.recovered` sidecars and resumed there; the original fragment is preserved.
The target file is replaced only after the assembled file passes size and SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_length(start: int, end: int) -> int:
    return end - start + 1


def range_path(target: Path, index: int) -> Path:
    return target.with_name(target.name + f".range{index:03d}")


def recovered_path(target: Path, index: int) -> Path:
    return target.with_name(target.name + f".range{index:03d}.recovered")


def candidate_for(target: Path, index: int, start: int, end: int) -> tuple[Path | None, dict[str, object]]:
    expected = expected_length(start, end)
    original = range_path(target, index)
    recovered = recovered_path(target, index)
    evidence: dict[str, object] = {
        "index": index,
        "start": start,
        "end": end,
        "expectedBytes": expected,
        "originalPath": str(original),
        "recoveredPath": str(recovered),
        "originalBytes": original.stat().st_size if original.exists() else 0,
        "recoveredBytes": recovered.stat().st_size if recovered.exists() else 0,
    }

    if recovered.exists():
        size = recovered.stat().st_size
        if size == expected:
            evidence["status"] = "RECOVERED_VALID"
            return recovered, evidence
        if size > expected:
            raise RuntimeError(f"recovered fragment exceeds expected size: {recovered} {size}>{expected}")
        evidence["status"] = "RECOVERED_PARTIAL"
        return recovered, evidence

    if original.exists():
        size = original.stat().st_size
        if size == expected:
            evidence["status"] = "ORIGINAL_VALID"
            return original, evidence
        if size > expected:
            raise RuntimeError(f"original fragment exceeds expected size: {original} {size}>{expected}")
        if size > 0:
            recovered.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, recovered)
            evidence["status"] = "ORIGINAL_PARTIAL_COPIED_TO_RECOVERED"
            evidence["recoveredBytes"] = recovered.stat().st_size
            return recovered, evidence
        evidence["status"] = "ORIGINAL_EMPTY_PLACEHOLDER"
        return recovered, evidence

    evidence["status"] = "MISSING"
    return recovered, evidence


def download_remaining(url: str, path: Path, start: int, end: int, index: int) -> dict[str, object]:
    expected = expected_length(start, end)
    current = path.stat().st_size if path.exists() else 0
    if current > expected:
        raise RuntimeError(f"sidecar exceeds expected size: {path} {current}>{expected}")
    if current == expected:
        return {"index": index, "status": "ALREADY_COMPLETE", "bytes": current, "expectedBytes": expected}

    request_start = start + current
    headers = {"Range": f"bytes={request_start}-{end}"}
    with requests.get(url, headers=headers, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError(f"range {index} returned HTTP {response.status_code}; refusing non-range response")
        content_range = response.headers.get("Content-Range", "")
        if not content_range.startswith(f"bytes {request_start}-{end}/"):
            raise RuntimeError(f"range {index} returned unexpected Content-Range: {content_range}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    final_size = path.stat().st_size
    if final_size != expected:
        raise RuntimeError(f"range {index} wrote {final_size} bytes, expected {expected}")
    return {"index": index, "status": "DOWNLOADED_OR_RESUMED", "bytes": final_size, "expectedBytes": expected}


def assemble(target: Path, prefix: int, candidates: list[Path], expected_size: int, expected_sha256: str, suffix: str) -> dict[str, object]:
    assembled = target.with_name(target.name + f".assembled_{suffix}")
    if assembled.exists():
        raise RuntimeError(f"refusing to overwrite existing assembled file: {assembled}")
    with assembled.open("wb") as output:
        with target.open("rb") as source:
            remaining = prefix
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise RuntimeError("target prefix ended before recorded prefix size")
                output.write(chunk)
                remaining -= len(chunk)
        for candidate in candidates:
            with candidate.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    actual_size = assembled.stat().st_size
    if actual_size != expected_size:
        return {"status": "ASSEMBLY_SIZE_MISMATCH", "assembled": str(assembled), "actualBytes": actual_size, "expectedBytes": expected_size}
    actual_sha = sha256(assembled)
    if actual_sha.lower() != expected_sha256.lower():
        return {"status": "INVALID_HASH", "assembled": str(assembled), "actualSha256": actual_sha, "expectedSha256": expected_sha256}
    os.replace(assembled, target)
    return {"status": "COMPLETE_VALIDATED", "target": str(target), "bytes": target.stat().st_size, "sha256": actual_sha}


def update_hf_ref(target: Path, revision: str | None) -> None:
    if not revision:
        return
    # target = .../models--org--repo/snapshots/<revision>/<filename>
    repo_cache = target.parent.parent.parent
    ref = repo_cache / "refs" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    if ref.exists() and ref.read_text(encoding="utf-8").strip() != revision:
        raise RuntimeError(f"ref already points to another revision: {ref}")
    if not ref.exists():
        ref.write_text(revision + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-mib", type=int, default=128)
    parser.add_argument("--run-suffix", default="20260818_run01")
    parser.add_argument("--hf-revision", default=None)
    args = parser.parse_args()

    target = Path(args.target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == args.size:
        actual = sha256(target)
        status = "SKIP_DOWNLOAD_COMPLETE" if actual.lower() == args.sha256.lower() else "INVALID_HASH_EXISTING_COMPLETE_SIZE"
        if status == "SKIP_DOWNLOAD_COMPLETE":
            update_hf_ref(target, args.hf_revision)
        print(json.dumps({"status": status, "target": str(target), "bytes": target.stat().st_size, "sha256": actual}, ensure_ascii=False, indent=2), flush=True)
        if status != "SKIP_DOWNLOAD_COMPLETE":
            raise SystemExit(2)
        return
    if not target.exists():
        target.touch()
    prefix = target.stat().st_size
    if prefix > args.size:
        raise RuntimeError(f"target prefix exceeds expected size: {prefix}>{args.size}")

    chunk_size = args.chunk_mib * 1024 * 1024
    range_count = (args.size - prefix + chunk_size - 1) // chunk_size
    jobs: list[tuple[int, int, int, Path]] = []
    candidates: list[Path] = []
    fragment_evidence: list[dict[str, object]] = []
    for index in range(range_count):
        start = prefix + index * chunk_size
        end = min(args.size - 1, start + chunk_size - 1)
        candidate, evidence = candidate_for(target, index, start, end)
        assert candidate is not None
        fragment_evidence.append(evidence)
        candidates.append(candidate)
        candidate_size = candidate.stat().st_size if candidate.exists() else 0
        if candidate_size != expected_length(start, end):
            jobs.append((index, start, end, candidate))

    print(json.dumps({"status": "RESUME_PLAN", "target": str(target), "prefixBytes": prefix, "rangeCount": range_count, "jobs": len(jobs), "fragments": fragment_evidence}, ensure_ascii=False, indent=2), flush=True)
    completed: list[dict[str, object]] = []
    if jobs:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {executor.submit(download_remaining, args.url, path, start, end, index): (index, path) for index, start, end, path in jobs}
            for future in as_completed(future_map):
                result = future.result()
                completed.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)

    for candidate in candidates:
        if not candidate.exists():
            raise RuntimeError(f"missing candidate after download: {candidate}")
    result = assemble(target, prefix, candidates, args.size, args.sha256, args.run_suffix)
    if result.get("status") == "COMPLETE_VALIDATED":
        update_hf_ref(target, args.hf_revision)
    result["completedJobs"] = completed
    result["fragmentCount"] = len(candidates)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if result.get("status") != "COMPLETE_VALIDATED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()

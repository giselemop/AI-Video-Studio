"""Run the small, reproducible regression set for the final benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")
PROJECT_ROOT = Path(r"C:\install\AI\VideoStudio")
PYTHON = Path(r"C:\install\AI\IdentityWorker\venv\Scripts\python.exe")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def run_check(run_root: Path, name: str, command: list[str], cwd: Path, timeout: int = 900) -> dict[str, object]:
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        status = "PASS" if result.returncode == 0 else "FAIL"
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        timed_out = False
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        status = "FAIL_TIMEOUT"
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        timed_out = True
        exit_code = None
    duration = round((time.perf_counter() - started) * 1000, 1)
    log_path = run_root / "logs" / f"regression-{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8", errors="replace")
    return {
        "name": name,
        "status": status,
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": duration,
        "command": command,
        "cwd": str(cwd),
        "log": str(log_path),
        "outputTail": output[-4000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    args = parser.parse_args()
    root = Path(args.run_root).resolve()
    tools = sorted((PROJECT_ROOT / "tools" / "sdxl_final_benchmark").glob("*.py"))
    checks: list[dict[str, object]] = []
    checks.append(run_check(root, "python-compile", [str(PYTHON), "-m", "py_compile", *[str(path) for path in tools]], PROJECT_ROOT))
    checks.append(run_check(root, "asset-validation", [str(PYTHON), "-c", "import json, pathlib; p=pathlib.Path(r'C:\\install\\AI\\Data\\QA\\sdxl_identity_final_benchmark_20260818\\run_01\\02-existing-assets.json'); a=json.loads(p.read_text(encoding='utf-8')); assert all(x['status']=='COMPLETE_VALIDATED' and x['size']==x['expectedSize'] and x['sha256'].lower()==x['expectedSha256'].lower() for x in a['assets']); print('AssetValidation: Passed')"], PROJECT_ROOT))
    checks.append(run_check(root, "resume-manifest", [str(PYTHON), "-c", "import json, pathlib; p=pathlib.Path(r'C:\\install\\AI\\Data\\QA\\sdxl_identity_final_benchmark_20260818\\run_01\\03-asset-resume-and-validation.json'); j=json.loads(p.read_text(encoding='utf-8')); assert j['current'] and all(x['status']=='COMPLETE_VALIDATED' for x in j['current']); assert j['preservation']; print('ResumeManifest: Passed')"], PROJECT_ROOT))
    checks.append(run_check(root, "vram-probe-parsing", [str(PYTHON), "-c", "import json, pathlib; r=pathlib.Path(r'C:\\install\\AI\\Data\\QA\\sdxl_identity_final_benchmark_20260818\\run_01'); rows=[]; [rows.extend(json.loads((r/f).read_text(encoding='utf-8'))['rows']) for f in ['04-instantid-vram-probe.json','05-pulid-vram-probe.json']]; assert all(x['gpu']['peakVramMiB'] and x['gpu']['lowestFreeMiB'] for x in rows); print('VRAMProbeParsing: Passed')"], PROJECT_ROOT))
    checks.append(run_check(root, "server-build", ["dotnet", "build", "server\\VideoStudio.Server.csproj", "--nologo"], PROJECT_ROOT, timeout=1200))
    checks.append(run_check(root, "quality-harness-build", ["dotnet", "build", "tests\\VideoStudio.QualityHarness\\VideoStudio.QualityHarness.csproj", "--nologo"], PROJECT_ROOT, timeout=1200))
    checks.append(run_check(root, "quality-harness-self-test", ["dotnet", "run", "--project", "tests\\VideoStudio.QualityHarness\\VideoStudio.QualityHarness.csproj", "--no-build", "--", "--self-test"], PROJECT_ROOT, timeout=600))
    checks.append(run_check(root, "git-diff-check", ["git", "diff", "--check"], PROJECT_ROOT))
    payload = {
        "schemaVersion": "2026-08-18.sdxl-build-regression.v1",
        "capturedAt": now(),
        "runRoot": str(root),
        "scope": "Final benchmark tools, asset/manifest arithmetic, VRAM parsing, project build, quality harness self-test, and git diff check.",
        "checks": checks,
        "allPassed": all(check["status"] == "PASS" for check in checks),
    }
    (root / "12-build-regression.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

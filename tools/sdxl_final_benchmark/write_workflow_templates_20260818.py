"""Create versioned, non-overwriting final benchmark workflow templates."""

from __future__ import annotations

import json
from pathlib import Path

from run_comfy_stage_20260818 import workflow_for


def main() -> None:
    specs = [
        ("InstantID", Path(r"C:\install\AI\Workflows\23_sdxl_instantid_final_benchmark_v1_api.json")),
        ("PuLID", Path(r"C:\install\AI\Workflows\24_sdxl_pulid_final_benchmark_v1_api.json")),
    ]
    results = []
    for method, path in specs:
        if path.exists():
            results.append({"method": method, "path": str(path), "status": "EXISTING_NOT_OVERWRITTEN"})
            continue
        workflow = workflow_for(method, "A", "front", 410001, f"sdxl_final_benchmark_20260818/{method.lower()}_template")
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append({"method": method, "path": str(path), "status": "CREATED"})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

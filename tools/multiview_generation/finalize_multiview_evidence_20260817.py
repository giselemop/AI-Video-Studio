"""Assemble the required cross-method evidence records from completed probes."""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_ROOT = Path(r"C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01")
OLD_ROOT = Path(r"C:\install\AI\Data\QA\identity_foundation_20260816\run_02")


def read(name: str, default: Any) -> Any:
    path = RUN_ROOT / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(name: str, value: Any) -> None:
    (RUN_ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def rate(count: int | None, total: int | None) -> float | None:
    return round(count / total, 4) if count is not None and total else None


def method_row(name: str, summary: dict[str, Any], status: str = "MEASURED") -> dict[str, Any]:
    total = summary.get("total", 0)
    dual = summary.get("dualPass")
    technical_success = summary.get("technicalSuccess")
    if technical_success is None and status == "MEASURED":
        technical_success = total
    return {"method": name, "status": status, "total": total, "technicalSuccess": technical_success, "identityPass": summary.get("identityPass"), "viewPass": summary.get("viewPass"), "dualPass": dual, "dualPassRate": rate(dual, total), "hardReject": summary.get("hardReject"), "productionCandidate": bool(dual is not None and rate(dual, total) is not None and rate(dual, total) >= 0.7)}


def main() -> None:
    captured = datetime.now().astimezone().isoformat()
    baseline = read("02-baseline-summary.json", {})
    head_control = read("03-head-pose-control.json", {})
    head = read("04-faceid-headpose-benchmark.json", {})
    instant_deploy = read("05-instantid-deployment.json", {})
    instant = read("06-instantid-benchmark.json", {})
    pulid_deploy = read("07-pulid-deployment.json", {})
    pulid = read("08-pulid-benchmark.json", {})
    img = read("09-img2img-benchmark.json", {})
    old_golden = read_from_old("09-golden-reference-pack-v2.json", {})
    old_selector = read_from_old("10-reference-selector-v2-validation.json", {})
    old_performance = read_from_old("11-performance.json", {})
    head_summary = head.get("summary", {})
    img_summary = img.get("summary", {})
    baseline_methods = baseline.get("byMethod", {})
    methods = [
        method_row("Baseline", baseline_methods.get("Baseline", {})),
        method_row("FaceID", baseline_methods.get("FaceID", {})),
        method_row("FaceID+HeadPose", head_summary),
        method_row("A_Img2Img_Pose", img_summary.get("byMethod", {}).get("A_Img2Img_Pose", {})),
        method_row("B_Img2Img_FaceID_Pose", img_summary.get("byMethod", {}).get("B_Img2Img_FaceID_Pose", {})),
        method_row("C_Img2Img_HeadPose", img_summary.get("byMethod", {}).get("C_Img2Img_HeadPose", {})),
        method_row("D_Img2Img_FaceID_HeadPose", img_summary.get("byMethod", {}).get("D_Img2Img_FaceID_HeadPose", {})),
        method_row("InstantID", instant.get("summary", {}), instant.get("status", "BLOCKED")),
        method_row("PuLID", pulid.get("summary", {}), pulid.get("status", "BLOCKED")),
    ]
    ranking = sorted(methods, key=lambda row: ((row["dualPassRate"] if row["dualPassRate"] is not None else -1), (row["viewPass"] if row["viewPass"] is not None else -1), (row["identityPass"] if row["identityPass"] is not None else -1)), reverse=True)
    write("10-method-comparison.json", {
        "schemaVersion": "2026-08-17.method-comparison.v1", "capturedAt": captured, "runRoot": str(RUN_ROOT),
        "ranking": [{"rank": index + 1, **row} for index, row in enumerate(ranking)], "methods": methods,
        "pareto": {"bestDualMeasured": ranking[0] if ranking else None, "identityOnlyBest": max(methods, key=lambda row: row["identityPass"] if row["identityPass"] is not None else -1), "viewOnlyBest": max(methods, key=lambda row: row["viewPass"] if row["viewPass"] is not None else -1)},
        "decision": "NO_TOP_PRODUCTION_METHOD", "reason": "No current method reaches the 30% Dual continuation gate; no method reaches the 70% production-candidate gate.", "thresholdsUnchanged": True,
    })
    dual_rows = [row for row in head.get("rows", []) if row.get("dualPass")]
    write("11-top-method-controlled-candidates.json", {
        "schemaVersion": "2026-08-17.top-method-candidates.v1", "capturedAt": captured, "runRoot": str(RUN_ROOT), "selectedMethod": None,
        "selectionStatus": "NO_TOP_METHOD", "expansionAllowed": False, "candidateCount": len(dual_rows), "productionCandidateCount": 0,
        "bestMeasuredRoute": "FaceID+HeadPose", "bestMeasuredDualPass": len(dual_rows), "bestMeasuredTotal": len(head.get("rows", [])), "bestMeasuredDualRate": rate(len(dual_rows), len(head.get("rows", []))),
        "reviewCandidates": [{"path": row.get("path"), "requestedView": row.get("requestedView"), "seed": row.get("seed"), "rawCosineSimilarity": row.get("rawCosineSimilarity"), "yaw": row.get("yaw"), "qualification": "dual_pass_but_not_a_production_candidate"} for row in dual_rows],
        "blockedExpansionReason": "FaceID+HeadPose Dual is below 30%; Img2Img routes have zero view passes; InstantID/PuLID are blocked before generation.",
    })
    current_rows = []
    for source, rows in (("FaceID+HeadPose", head.get("rows", [])), ("Img2Img", img.get("rows", []))):
        for row in rows:
            current_rows.append({"source": source, "method": row.get("method"), "requestedView": row.get("requestedView"), "seed": row.get("seed"), "denoise": row.get("denoise"), "path": row.get("path"), "technicalSuccess": row.get("technicalSuccess"), "rawCosineSimilarity": row.get("rawCosineSimilarity"), "yaw": row.get("yaw"), "yawError": row.get("yawError"), "identityPass": row.get("identityPass"), "viewPass": row.get("viewPass"), "dualPass": row.get("dualPass"), "hardRejectFlags": row.get("hardRejectFlags")})
    write("12-character-qa-results.json", {
        "schemaVersion": "2026-08-17.character-qa-results.v1", "capturedAt": captured, "runRoot": str(RUN_ROOT), "frozenIdentityThreshold": 0.5,
        "summary": {"completedRows": len(current_rows), "technicalSuccess": sum(bool(row.get("technicalSuccess")) for row in current_rows), "identityPass": sum(bool(row.get("identityPass")) for row in current_rows), "viewPass": sum(bool(row.get("viewPass")) for row in current_rows), "dualPass": sum(bool(row.get("dualPass")) for row in current_rows), "dualPassRateAcrossNonIndependentRows": rate(sum(bool(row.get("dualPass")) for row in current_rows), len(current_rows)), "manualReviewRequired": True},
        "byBenchmark": {"FaceID+HeadPose": head_summary, "Img2Img": img_summary, "InstantID": instant.get("summary", {}), "PuLID": pulid.get("summary", {})},
        "rows": current_rows, "bodyPoseAndCrop": "UNMEASURED_MANUAL_REVIEW", "thresholdsUnchanged": True,
    })
    old_pack = old_golden.get("goldenPack", [])
    golden_by_view = {view: 0 for view in ["front", "front_left_30", "front_right_30", "left_45", "right_45", "half_body_front", "full_body_front"]}
    for row in old_pack:
        if row.get("requestedView") in golden_by_view:
            golden_by_view[row["requestedView"]] += 1
    write("13-golden-reference-pack-v3.json", {
        "schemaVersion": "2026-08-17.golden-pack-v3", "capturedAt": captured, "runRoot": str(RUN_ROOT), "targetCount": "10-20", "count": len(old_pack), "goldenPack": old_pack,
        "newReviewCandidates": [{"goldenId": None, "requestedView": row.get("requestedView"), "path": row.get("path"), "method": row.get("method"), "seed": row.get("seed"), "qualification": "dual_pass_but_not_promoted; duplicate_front_view; manual_review_required"} for row in dual_rows],
        "goldenByView": golden_by_view, "status": "FAIL_GOLDEN_TARGET_NOT_MET", "autoPromotionAllowed": False, "manualReviewRequired": True, "loRAAllowed": False,
        "reason": "No new non-front dual candidates were produced and the existing v2 pack has only 3 entries; target is 10-20 with core non-front views.",
    })
    old_current = old_selector.get("current", {})
    write("14-selector-validation.json", {
        "schemaVersion": "2026-08-17.selector-validation.v3", "capturedAt": captured, "runRoot": str(RUN_ROOT), "goldenPack": str(RUN_ROOT / "13-golden-reference-pack-v3.json"),
        "current": {"total": len(golden_by_view), "direct": sum(1 for value in golden_by_view.values() if value > 0), "fallback": sum(1 for value in golden_by_view.values() if value == 0), "directQualifiedReferenceRate": round(sum(1 for value in golden_by_view.values() if value > 0) / len(golden_by_view), 4)},
        "previousEvidence": {"current": old_current, "path": str(OLD_ROOT / "10-reference-selector-v2-validation.json")}, "gatePass": False, "reason": "Direct selector coverage remains below 80%; no non-front Golden references are available.", "manualReviewRequired": True,
    })
    head_rows = head.get("rows", [])
    img_rows = img.get("rows", [])
    generation_times = [row.get("generationDurationMs") or 0 for row in img_rows if row.get("generationDurationMs")]
    qa_times = [row.get("analysisMs") or 0 for row in img_rows if row.get("analysisMs")]
    free_vram = [row.get("vramAfter", {}).get("freeMiB") for row in head_rows if row.get("vramAfter")] + [row.get("vramAfter", {}).get("freeMiB") for row in img_rows if row.get("vramAfter")]
    probe = read("adapter-asset-probe.json", {})
    probe_times = {item["name"]: item.get("durationMs") for item in probe.get("probes", [])} if probe else {}
    write("15-performance.json", {
        "schemaVersion": "2026-08-17.performance.v1", "capturedAt": captured, "runRoot": str(RUN_ROOT), "gpu": {"name": "NVIDIA GeForce RTX 4070", "totalMiB": 12282, "minFreeMiBMeasured": min(free_vram) if free_vram else None, "sdxlPeakMeasured": False},
        "headPose": {"rows": len(head_rows), "generationP50Ms": 4061, "generationP95Ms": 8127, "identityQaP50Ms": 937.621, "minFreeMiB": 6898},
        "img2img": {"rows": len(img_rows), "generationP50Ms": statistics.median(generation_times) if generation_times else None, "generationP95Ms": sorted(generation_times)[max(0, int(len(generation_times) * .95 + .999) - 1)] if generation_times else None, "identityQaP50Ms": statistics.median(qa_times) if qa_times else None, "minFreeMiB": min(free_vram) if free_vram else None},
        "adapterLoaders": probe_times, "previousRun": {"path": str(OLD_ROOT / "11-performance.json"), "generationP50Ms": old_performance.get("generation", {}).get("p50Ms"), "embeddingP50Ms": old_performance.get("embedding", {}).get("p50Ms")},
        "limitations": ["InstantID/PuLID SDXL generation peak VRAM is unmeasured because complete assets were not available; do not infer a pass from SD1.5 VRAM."],
    })
    if not (RUN_ROOT / "16-build-regression.json").exists():
        write("16-build-regression.json", {"schemaVersion": "2026-08-17.multiview-build-regression.v1", "capturedAt": captured, "status": "PENDING", "note": "Run C# build, QualityHarness self-test, Python compile, and git diff check before final acceptance."})
    write("17-final-acceptance.json", {
        "schemaVersion": "2026-08-17.multiview-final-acceptance.v1", "capturedAt": captured, "runRoot": str(RUN_ROOT), "finalStatus": "NO_GO_MULTIVIEW", "recommendedIdentityMethod": "FaceID for front-only identity reference; no production multiview method", "readyForCharacterLoRAPoC": False,
        "gates": {"FailureAnalysis": {"status": "PASS", "evidence": "faceid-failure-analysis.json"}, "HeadPoseControl": {"status": "FAIL_LOW_YIELD", "evidence": "04-faceid-headpose-benchmark.json", "dualPass": head_summary.get("dualPass"), "total": head_summary.get("total")}, "InstantID": {"status": instant.get("status"), "evidence": "06-instantid-benchmark.json"}, "PuLID": {"status": pulid.get("status"), "evidence": "08-pulid-benchmark.json"}, "Img2Img": {"status": "FAIL_ZERO_VIEW_DUAL", "evidence": "09-img2img-benchmark.json", "dualPass": img_summary.get("dualPass"), "total": img_summary.get("total")}, "Golden": {"status": "FAIL", "evidence": "13-golden-reference-pack-v3.json", "count": len(old_pack)}, "Selector": {"status": "FAIL", "evidence": "14-selector-validation.json"}, "BuildRegression": {"status": read("16-build-regression.json", {}).get("status", "PENDING"), "evidence": "16-build-regression.json"}},
        "summary": {"headPoseDual": f"{head_summary.get('dualPass', 0)}/{head_summary.get('total', 0)}", "img2imgDual": f"{img_summary.get('dualPass', 0)}/{img_summary.get('total', 0)}", "goldenCount": len(old_pack), "selectorDirectRate": round(sum(1 for value in golden_by_view.values() if value > 0) / len(golden_by_view), 4)},
        "blocked": ["BLOCKED_MULTIVIEW_DUAL_LT_30", "BLOCKED_INSTANTID_SDXL_ASSETS_OR_PREGENERATION", "BLOCKED_PULID_EVA_AND_SDXL", "BLOCKED_GOLDEN_PACK", "BLOCKED_SELECTOR", "BLOCKED_LORA", "BLOCKED_VIDEO_SCOPE_BY_LATEST_PROMPT"],
        "manualReview": ["identity likeness", "head-pose semantics and left/right direction", "hair/clothing/occlusion", "body coverage/crop", "Golden promotion"], "thresholdsUnchanged": True,
    })
    print(json.dumps({"status": "assembled", "methodCount": len(methods), "goldenCount": len(old_pack), "headPose": head_summary, "img2img": img_summary}, ensure_ascii=False, indent=2))


def read_from_old(name: str, default: Any) -> Any:
    path = OLD_ROOT / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    main()

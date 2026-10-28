"""Build human-review HTML for executed benchmark stages."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


DEFAULT_RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")
STYLE = """
body{font-family:Segoe UI,Microsoft YaHei,sans-serif;background:#f4f6f8;color:#17202a;margin:24px}
h1{margin:0 0 8px}h2{margin-top:28px}.summary{display:flex;gap:12px;flex-wrap:wrap}.card{background:white;border-radius:10px;padding:12px 16px;box-shadow:0 1px 4px #0002}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.sample{background:#fff;border-radius:10px;padding:10px;box-shadow:0 1px 4px #0002}.sample img{width:100%;aspect-ratio:2/3;object-fit:contain;background:#e9edf0;border-radius:6px}.sample h3{margin:8px 0 4px;font-size:15px}.metric{font-size:12px;line-height:1.55}.pass{color:#087f5b;font-weight:600}.fail{color:#c92a2a;font-weight:600}.muted{color:#667085}.table{width:100%;border-collapse:collapse;background:#fff}.table th,.table td{border:1px solid #dfe3e8;padding:7px;text-align:left;vertical-align:top;font-size:12px}.table th{background:#eef2f6}.view-block{margin-top:18px}.banner{padding:12px 16px;background:#fff3cd;border-left:4px solid #e0a800;border-radius:6px}.path{word-break:break-all}
"""


def load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def esc(value: Any) -> str:
    return html.escape("NOT_RUN" if value is None else str(value))


def percent(value: Any) -> str:
    return "NOT_RUN" if value is None else f"{float(value) * 100:.2f}%"


def image_src(path: str | None) -> str:
    return Path(path).resolve().as_uri() if path else ""


def page(title: str, subtitle: str, body: str) -> str:
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{esc(title)}</title><style>{STYLE}</style></head><body><h1>{esc(title)}</h1><div class='muted'>{esc(subtitle)}</div>{body}</body></html>"


def card(row: dict[str, Any]) -> str:
    path = row.get("workerOutputPath") or row.get("outputPath") or row.get("path")
    dual = bool(row.get("dualPass"))
    image = f"<img src='{html.escape(image_src(path), quote=True)}' alt='{esc(row.get('requestedView'))} seed {esc(row.get('seed'))}'>" if path else "<div class='banner'>没有输出图</div>"
    rejects = ", ".join(row.get("hardRejects") or row.get("hardRejectFlags") or []) or "none"
    return f"<div class='sample'>{image}<h3>{esc(row.get('requestedView'))} × seed {esc(row.get('seed'))}</h3><div class='metric'>Cosine: {esc(row.get('identityRawCosine', row.get('rawCosineSimilarity')))}<br>Yaw: {esc(row.get('yaw'))}° / target {esc(row.get('targetYaw'))}°<br>YawError: {esc(row.get('yawError'))}°<br>Face: {esc(row.get('faceCount'))}; Identity: {esc(row.get('identityPass'))}; View: {esc(row.get('viewPass'))}<br><span class='{('pass' if dual else 'fail')}'>Dual: {esc(dual)}</span>; HardReject: {esc(rejects)}<br>Generation: {esc(row.get('generationTimeMs'))} ms; Technical: {esc(row.get('technicalSuccess'))}<br><span class='path'>{esc(path)}</span></div></div>"


def stage_page(root: Path, method: str, filename: str, title: str) -> str:
    payload = load(root, filename)
    summary = payload.get("summary", {})
    rows = payload.get("rows", [])
    status = summary.get("status", payload.get("status", "NOT_RUN"))
    summary_html = f"<div class='summary'><div class='card'>Status: <b>{esc(status)}</b></div><div class='card'>Requested: {esc(summary.get('requestedCount'))}</div><div class='card'>Technical: {esc(summary.get('technicalSuccessCount'))}</div><div class='card'>Identity: {esc(summary.get('identityPassCount'))}</div><div class='card'>View: {esc(summary.get('viewPassCount'))}</div><div class='card'>Dual: {esc(summary.get('dualPassCount'))} / {percent(summary.get('endToEndYield'))}</div><div class='card'>Median cosine: {esc(summary.get('medianCosine'))}</div><div class='card'>Median yaw error: {esc(summary.get('medianYawError'))}°</div></div>"
    if not rows:
        body = summary_html + "<div class='banner' style='margin-top:18px'>该阶段没有实际执行样本；没有生成图片，也没有把 NOT_RUN 写成 0% 质量。</div>"
    else:
        blocks = []
        for view in sorted({row.get("requestedView") for row in rows}):
            blocks.append(f"<h2>{esc(view)}</h2><div class='grid'>{''.join(card(row) for row in rows if row.get('requestedView') == view)}</div>")
        body = summary_html + "".join(blocks)
    return page(title, f"{method}；来源 {filename}；只展示实际生成的样本", body)


def comparison_page(root: Path) -> str:
    payloads = [("InstantID", load(root, "06-instantid-stage-b.json")), ("PuLID", load(root, "07-pulid-stage-b.json"))]
    blocks = []
    for view in ["front", "left30", "left45"]:
        rows_html = []
        for label, payload in payloads:
            for row in [item for item in payload.get("rows", []) if item.get("requestedView") == view]:
                path = row.get("workerOutputPath") or row.get("outputPath")
                image = f"<img src='{html.escape(image_src(path), quote=True)}' style='width:150px;max-height:220px;object-fit:contain;background:#eee' alt='{esc(label)} {esc(view)} {esc(row.get('seed'))}'>" if path else "NOT_RUN"
                rejects = ", ".join(row.get("hardRejects") or []) or "none"
                metrics = f"Cosine={esc(row.get('identityRawCosine'))}; Yaw={esc(row.get('yaw'))}°; Error={esc(row.get('yawError'))}°; Dual={esc(row.get('dualPass'))}; Time={esc(row.get('generationTimeMs'))} ms; Reject={esc(rejects)}"
                rows_html.append(f"<tr><td>{esc(label)}</td><td>{esc(row.get('seed'))}</td><td>{image}<br>{metrics}</td></tr>")
        blocks.append(f"<div class='view-block'><h2>{view}</h2><table class='table'><thead><tr><th>Method</th><th>Seed</th><th>Image / metrics</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>")
    return page("InstantID vs PuLID — SDXL Stage B", "统一 master、prompt、seed、分辨率与 QA 阈值；左右并排只展示实际生成样本", "".join(blocks))


def golden_page(root: Path) -> str:
    acceptance = load(root, "13-final-acceptance.json")
    body = f"<div class='banner'>Status: <b>NOT_RUN</b><br>Reason: 两种方法均未通过 Stage B >=30% Dual gate，Stage C 未执行，因此没有 Golden Candidates。</div><div class='card' style='margin-top:18px'>Final decision: <b>{esc(acceptance.get('decision'))}</b><br>Ready for Character LoRA POC: {esc(acceptance.get('readyForCharacterLoraPoc'))}</div>"
    return page("Final Golden Candidates", "本页只记录 Golden Candidate 是否被允许执行，不伪造未生成图片", body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    args = parser.parse_args()
    root = Path(args.run_root).resolve()
    output = root / "html"
    output.mkdir(parents=True, exist_ok=True)
    (output / "01-instantid-stage-b.html").write_text(stage_page(root, "InstantID", "06-instantid-stage-b.json", "InstantID — SDXL Stage B"), encoding="utf-8")
    (output / "02-pulid-stage-b.html").write_text(stage_page(root, "PuLID", "07-pulid-stage-b.json", "PuLID — SDXL Stage B"), encoding="utf-8")
    instant_c = load(root, "08-instantid-stage-c.json")
    pulid_c = load(root, "09-pulid-stage-c.json")
    if instant_c.get("status") == "EVALUATED" and instant_c.get("rows"):
        (output / "03-instantid-stage-c.html").write_text(stage_page(root, "InstantID", "08-instantid-stage-c.json", "InstantID — SDXL Stage C"), encoding="utf-8")
    if pulid_c.get("status") == "EVALUATED" and pulid_c.get("rows"):
        (output / "04-pulid-stage-c.html").write_text(stage_page(root, "PuLID", "09-pulid-stage-c.json", "PuLID — SDXL Stage C"), encoding="utf-8")
    (output / "05-instantid-vs-pulid.html").write_text(comparison_page(root), encoding="utf-8")
    (output / "06-final-golden-candidates.html").write_text(golden_page(root), encoding="utf-8")
    print(json.dumps({"htmlDirectory": str(output), "files": sorted(path.name for path in output.glob("*.html")), "stageCHtmlGenerated": bool((instant_c.get('status') == 'EVALUATED' and instant_c.get('rows')) or (pulid_c.get('status') == 'EVALUATED' and pulid_c.get('rows')))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

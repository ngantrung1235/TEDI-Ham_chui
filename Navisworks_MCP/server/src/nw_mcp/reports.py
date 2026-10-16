"""Xuat bao cao clash (CSV / HTML) tu ket qua nw_clash_results - chay phia Python, ghi len may chay MCP."""

from __future__ import annotations

import csv
import html
import io
from pathlib import Path
from typing import Any

COLUMNS = [
    ("stt", "STT"),
    ("name", "Tên va chạm"),
    ("status", "Trạng thái"),
    ("distance_m", "Khoảng cách (m)"),
    ("x", "X (m)"),
    ("y", "Y (m)"),
    ("z", "Z (m)"),
    ("item1_name", "Cấu kiện 1"),
    ("item1_path", "Đường dẫn 1"),
    ("item2_name", "Cấu kiện 2"),
    ("item2_path", "Đường dẫn 2"),
]


def flatten(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for i, r in enumerate(results, start=1):
        pt = r.get("point_m") or [None, None, None]
        i1, i2 = r.get("item1") or {}, r.get("item2") or {}
        rows.append({
            "stt": i, "name": r.get("name"), "status": r.get("status"), "distance_m": r.get("distance_m"),
            "x": pt[0], "y": pt[1], "z": pt[2],
            "item1_name": i1.get("name"), "item1_path": i1.get("path"),
            "item2_name": i2.get("name"), "item2_path": i2.get("path"),
        })
    return rows


def to_csv(test: str, results: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([label for _, label in COLUMNS])
    for row in flatten(results):
        w.writerow(["" if row[k] is None else row[k] for k, _ in COLUMNS])
    return buf.getvalue()


def to_html(test: str, results: list[dict[str, Any]], summary: dict[str, int]) -> str:
    esc = html.escape
    head = "".join(f"<th>{esc(label)}</th>" for _, label in COLUMNS)
    body = []
    for row in flatten(results):
        cells = "".join(f"<td>{esc('' if row[k] is None else str(row[k]))}</td>" for k, _ in COLUMNS)
        body.append(f"<tr class=\"st-{esc(str(row['status'] or '').lower())}\">{cells}</tr>")
    chips = "".join(f"<span class=\"chip\">{esc(k)}: <b>{v}</b></span>" for k, v in summary.items())
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>Báo cáo va chạm - {esc(test)}</title>
<style>
body{{font:14px/1.45 system-ui,Segoe UI,sans-serif;margin:24px;color:#1b1f23}}
h1{{font-size:20px;margin:0 0 8px}} .chip{{display:inline-block;padding:2px 10px;margin:0 6px 12px 0;border-radius:12px;background:#eef1f5}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #d5dbe3;padding:4px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f5f8;position:sticky;top:0}} tr.st-new td:nth-child(3){{color:#b42318;font-weight:600}}
tr.st-resolved td:nth-child(3),tr.st-approved td:nth-child(3){{color:#067647}}
</style></head><body>
<h1>Báo cáo va chạm: {esc(test)}</h1>
<div>{chips}</div>
<table><thead><tr>{head}</tr></thead><tbody>
{''.join(body)}
</tbody></table></body></html>"""


def write_report(path: str, fmt: str, test: str, results: list[dict[str, Any]]) -> str:
    fmt = fmt.lower()
    if fmt not in ("csv", "html"):
        raise ValueError("format chi nhan 'csv' hoac 'html'.")
    summary: dict[str, int] = {"Tổng": len(results)}
    for r in results:
        st = str(r.get("status") or "?")
        summary[st] = summary.get(st, 0) + 1
    text = to_csv(test, results) if fmt == "csv" else to_html(test, results, summary)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig de Excel mo CSV tieng Viet khong loi font
    target.write_text(text, encoding="utf-8-sig" if fmt == "csv" else "utf-8", newline="")
    return str(target)

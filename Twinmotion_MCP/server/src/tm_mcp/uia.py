"""Doc/kich hoat phan tu giao dien qua Microsoft UI Automation (tuy chon, can `pip install pywinauto`).

LUU Y: giao dien Twinmotion dua tren Unreal Slate - UI Automation thuong chi lo cap cua so, it hoac khong co nut
ben trong (tuy phien ban/cau hinh accessibility). Do do day la lop BO SUNG; duong chinh la chup man hinh + chuot/phim.
CHUA kiem chung voi Twinmotion 2026.1.
"""

from __future__ import annotations

from typing import Any

from .controller import ControlError


def _root(hwnd: int):
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise ControlError("Can cai pywinauto de dung UI Automation:  pip install pywinauto  (extra 'uia').") from exc
    return Desktop(backend="uia").window(handle=hwnd).element_info


def _describe(info: Any, depth: int) -> dict:
    r = info.rectangle
    return {
        "depth": depth, "name": info.name or "", "control_type": str(info.control_type or ""),
        "automation_id": info.automation_id or "", "class_name": info.class_name or "",
        "rect": [r.left, r.top, r.right, r.bottom],
    }


def tree(hwnd: int, max_depth: int = 4, name_filter: str | None = None, limit: int = 300) -> dict:
    out: list[dict] = []
    truncated = False
    needle = (name_filter or "").lower()

    def walk(info: Any, depth: int) -> None:
        nonlocal truncated
        if truncated:
            return
        row = _describe(info, depth)
        if not needle or needle in row["name"].lower() or needle in row["automation_id"].lower():
            if len(out) >= limit:
                truncated = True
                return
            out.append(row)
        if depth < max_depth:
            try:
                children = info.children()
            except Exception:
                children = []
            for child in children:
                walk(child, depth + 1)

    walk(_root(hwnd), 0)
    return {"elements": out, "truncated": truncated,
            "note": "Danh sach ngan/chi co cap cua so nghia la ung dung (Slate) khong lo UI Automation: dung chup man hinh + tm_click."}


def invoke(hwnd: int, name: str | None = None, automation_id: str | None = None, control_type: str | None = None,
           index: int = 0, double: bool = False) -> dict:
    if not (name or automation_id):
        raise ControlError("Can name hoac automation_id.")
    try:
        from pywinauto.controls.uiawrapper import UIAWrapper
    except ImportError as exc:
        raise ControlError("Can cai pywinauto de dung UI Automation:  pip install pywinauto  (extra 'uia').") from exc

    matches: list[Any] = []

    def walk(info: Any, depth: int) -> None:
        if depth > 12:
            return
        if ((name and (info.name or "").lower() == name.lower()) or (automation_id and info.automation_id == automation_id)) \
                and (not control_type or str(info.control_type).lower() == control_type.lower()):
            matches.append(info)
        try:
            for child in info.children():
                walk(child, depth + 1)
        except Exception:
            pass

    walk(_root(hwnd), 0)
    if not matches:
        raise ControlError("Khong tim thay phan tu (UI Automation co the khong lo phan tu nay; dung chup man hinh + tm_click).")
    if index >= len(matches):
        raise ControlError(f"index {index} vuot qua so phan tu khop ({len(matches)}).")
    ctrl = UIAWrapper(matches[index])
    try:
        ctrl.invoke()
        used = "invoke"
    except Exception:
        (ctrl.double_click_input if double else ctrl.click_input)()
        used = "click_input"
    return {"matched": len(matches), "used": used, "element": _describe(matches[index], 0)}

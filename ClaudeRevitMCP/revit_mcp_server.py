"""MCP server noi Claude (Desktop / Code) voi Revit dang mo tren cung may.

Luong du lieu:
    Claude  --stdio (MCP)-->  file nay  --TCP 127.0.0.1-->  add-in TEDI_ClaudeBridge
    (nut "Ket noi Claude" tren tab "TEDI Claude" cua Revit 2024/2027,
    xem TEDI_Ham_chui_model/TEDI_ClaudeBridge/BridgeServer.cs)

Add-in ghi port + token vao %APPDATA%\\TEDI-Ham_chui\\claude_bridge.json moi lan bat
cau noi; server nay doc lai file do o MOI lan goi lenh nen khong can cau hinh tay,
ke ca khi khoi dong lai Revit.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError


def _connection_file() -> Path:
    override = os.environ.get("TEDI_REVIT_BRIDGE_FILE")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "TEDI-Ham_chui" / "claude_bridge.json"


class RevitBridgeError(ToolError):
    """Loi tra ve cho Claude nguyen van (ToolError khong bi SDK an thong bao)."""


def call_revit(method: str, params: dict[str, Any] | None = None, timeout: float = 90.0) -> Any:
    """Gui 1 lenh sang add-in Revit, tra ve 'result' hoac raise RevitBridgeError."""
    path = _connection_file()
    if not path.exists():
        raise RevitBridgeError(
            f"Khong thay {path}. Hay mo Revit va bam nut 'Ket noi Claude' "
            "tren tab 'TEDI Claude' truoc."
        )
    info = json.loads(path.read_text(encoding="utf-8"))
    request = {"id": 1, "token": info["token"], "method": method, "params": params or {}}

    try:
        with socket.create_connection((info.get("host", "127.0.0.1"), int(info["port"])), timeout=timeout) as sock:
            sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
    except OSError as exc:
        raise RevitBridgeError(
            f"Khong ket noi duoc Revit tai {info.get('host')}:{info.get('port')} ({exc}). "
            "Revit da dong hoac cau noi da tat - bam lai nut 'Ket noi Claude'."
        ) from exc

    if not buffer:
        raise RevitBridgeError("Revit dong ket noi ma khong tra loi.")
    response = json.loads(buffer.decode("utf-8"))
    if not response.get("ok"):
        raise RevitBridgeError(response.get("error", "Loi khong ro tu Revit."))
    return response.get("result")


mcp = MCPServer(
    "revit",
    instructions=(
        "Cong cu doc/chinh model Revit dang mo (du an ham chui TEDI). Toa do va chieu dai "
        "hinh hoc tra ve theo mm; gia tri parameter 'value' theo don vi hien thi cua du an, "
        "'raw' theo don vi noi bo Revit (feet). Truoc khi sua (revit_set_parameters) hay doc "
        "phan tu bang revit_get_element va xac nhan voi nguoi dung."
    ),
)


@mcp.tool()
def revit_ping() -> Any:
    """Kiem tra ket noi toi Revit: phien ban Revit va ten model dang mo."""
    return call_revit("ping")


@mcp.tool()
def revit_get_document_info() -> Any:
    """Thong tin model dang mo: ten, duong dan, don vi chieu dai, view hien hanh, danh sach Level, so phan tu."""
    return call_revit("get_document_info")


@mcp.tool()
def revit_list_categories() -> Any:
    """Liet ke cac category co phan tu trong model (ten hien thi, ten BuiltInCategory, so luong)."""
    return call_revit("list_categories")


@mcp.tool()
def revit_get_selection() -> Any:
    """Cac phan tu nguoi dung dang chon trong Revit (id, ten, category, type, level)."""
    return call_revit("get_selection")


@mcp.tool()
def revit_list_elements(
    category: str | None = None,
    name_contains: str | None = None,
    active_view_only: bool = False,
    limit: int = 200,
) -> Any:
    """Liet ke phan tu (khong gom element type).

    Args:
        category: Ten BuiltInCategory (vd. "OST_Rebar", "OST_StructuralFraming",
            "OST_GenericModel") hoac ten hien thi category. Bo trong = moi category.
        name_contains: Loc theo chuoi con trong ten phan tu hoac ten type.
        active_view_only: Chi lay phan tu hien trong view dang mo.
        limit: So phan tu toi da tra ve (1-5000); 'total' van cho biet tong so.
    """
    return call_revit(
        "list_elements",
        {"category": category, "name_contains": name_contains, "active_view_only": active_view_only, "limit": limit},
    )


@mcp.tool()
def revit_get_element(element_id: int, include_type_parameters: bool = False) -> Any:
    """Chi tiet 1 phan tu: toan bo parameter, vi tri (mm), bounding box (mm).

    Args:
        element_id: ElementId cua phan tu.
        include_type_parameters: Lay them parameter cua type (family type).
    """
    return call_revit("get_element", {"id": element_id, "include_type_parameters": include_type_parameters})


@mcp.tool()
def revit_get_rebar_summary(host_id: int | None = None, selection_only: bool = False) -> Any:
    """Thong ke cot thep theo loai thanh: so thanh, tong chieu dai (m), khoi luong danh nghia (kg).

    Args:
        host_id: Chi tinh thep thuoc 1 cau kien host (ElementId).
        selection_only: Chi tinh thep dang chon, hoac thep co host dang chon.
    """
    params: dict[str, Any] = {"selection_only": selection_only}
    if host_id is not None:
        params["host_id"] = host_id
    return call_revit("get_rebar_summary", params)


@mcp.tool()
def revit_select_elements(element_ids: list[int], zoom: bool = True) -> Any:
    """Chon (highlight) cac phan tu trong Revit de nguoi dung xem; zoom=True thi phong to toi chung."""
    return call_revit("select_elements", {"ids": element_ids, "zoom": zoom})


@mcp.tool()
def revit_set_parameters(element_id: int, values: dict[str, Any]) -> Any:
    """SUA MODEL: gan gia tri parameter cho 1 phan tu trong 1 Transaction (loi 1 cai la huy ca lo, Ctrl+Z de hoan tac).

    Args:
        element_id: ElementId cua phan tu.
        values: {ten_parameter: gia_tri}. So duoc hieu theo don vi hien thi cua du an
            (vd. mm); chuoi cho tham so so se duoc Revit phan tich (vd. "2500 mm");
            bool cho tham so Yes/No.
    """
    return call_revit("set_parameters", {"id": element_id, "values": values})


@mcp.tool()
def revit_get_draw_all_rebar_settings() -> Any:
    """Thong so mac dinh (mm) cua lenh "Ve tat ca thep" ham chui + model da co RebarShape Rebar_21 chua.

    Goi truoc revit_draw_all_rebar de trinh bay bang thong so cho nguoi dung xac nhan.
    """
    return call_revit("get_draw_all_rebar_settings")


@mcp.tool()
def revit_draw_all_rebar(settings: dict[str, float] | None = None, host_ids: list[int] | None = None) -> Any:
    """SUA MODEL: ve toan bo cot thep than ham (nut "Ve tat ca thep") cho cac cau kien dang chon.

    Quy trinh: (1) goi revit_get_draw_all_rebar_settings, trinh bay thong so va XAC NHAN voi
    nguoi dung; (2) dan nguoi dung: sau khi goi lenh, trong Revit phai pick lan luot 3 mat cho
    TUNG cau kien - MAT BANG (day/nap), MAT DUNG (tuong trai/phai), MAT CANH (dau dot); Esc de huy.
    Lenh cho toi 30 phut trong luc nguoi dung pick. Moi nhom thep commit Transaction rieng.

    Args:
        settings: Ghi de thong so (mm), vd. {"CoverMm": 50, "DiamS1Mm": 25, "SpaceS1Mm": 125}.
            Ten hop le lay tu revit_get_draw_all_rebar_settings; bo trong = mac dinh theo ban ve.
        host_ids: ElementId cac dot ham can ve; bo trong = dung selection hien tai trong Revit.
    """
    params: dict[str, Any] = {}
    if settings:
        params["settings"] = settings
    if host_ids:
        params["host_ids"] = host_ids
    return call_revit("draw_all_rebar", params, timeout=31 * 60)


if __name__ == "__main__":
    mcp.run()

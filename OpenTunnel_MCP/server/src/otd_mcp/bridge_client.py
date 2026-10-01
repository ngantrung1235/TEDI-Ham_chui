"""Client HTTP toi add-in OTDMcpBridge chay ben trong OpenTunnel Designer.

Bridge ghi file discovery (mac dinh %LOCALAPPDATA%\\OTDMcp\\bridge.json) chua port + token
moi lan khoi dong; client doc lai file nay o moi lan goi nen OTD khoi dong lai van ket noi
duoc ma khong can restart MCP server.

Bien moi truong ghi de:
  OTD_MCP_URL + OTD_MCP_TOKEN  dung truc tiep, bo qua file discovery
  OTD_MCP_DISCOVERY            duong dan file discovery khac
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

try:  # mcp >= 2.0
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]


class BridgeError(ToolError, RuntimeError):
    """Bridge tra ve loi (method loi, sai tham so, exception trong OTD...).

    Ke thua ToolError de MCP chuyen nguyen van thong bao cho LLM tu sua tham so,
    thay vi an thanh "Error executing tool".
    """


class BridgeUnavailable(BridgeError):
    """Khong ket noi duoc bridge (OTD chua mo / add-in chua nap)."""


HOW_TO_START = (
    "Hay mo OpenTunnel Designer 2026, mo 1 file DGN, roi go key-in 'mdl load OTDMcpBridge' "
    "(hoac 'OTDMCP START' neu add-in da nap). Kiem tra bang key-in 'OTDMCP STATUS'."
)


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str
    source: str


def discovery_path() -> Path:
    override = os.environ.get("OTD_MCP_DISCOVERY")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "OTDMcp" / "bridge.json"


def discover() -> Endpoint:
    url, token = os.environ.get("OTD_MCP_URL"), os.environ.get("OTD_MCP_TOKEN")
    if url and token:
        return Endpoint(url.rstrip("/"), token, "env")

    path = discovery_path()
    try:
        info = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise BridgeUnavailable(f"Khong thay file discovery {path}. {HOW_TO_START}") from None
    except (OSError, ValueError) as exc:
        raise BridgeUnavailable(f"Khong doc duoc {path}: {exc}") from exc

    port, tok = info.get("port"), info.get("token")
    if not port or not tok:
        raise BridgeUnavailable(f"File discovery {path} thieu port/token.")
    return Endpoint(info.get("url") or f"http://127.0.0.1:{port}", tok, str(path))


class BridgeClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, timeout: float) -> httpx.Client:
        # trust_env=False: khong cho request loopback di qua HTTP(S)_PROXY cua may cong ty.
        return httpx.Client(timeout=timeout, transport=self._transport, trust_env=False)

    def health(self) -> dict[str, Any]:
        ep = discover()
        try:
            with self._client(5) as c:
                r = c.get(f"{ep.url}/health")
        except httpx.TransportError as exc:
            raise BridgeUnavailable(f"Bridge khong phan hoi tai {ep.url} ({exc}). {HOW_TO_START}") from exc
        r.raise_for_status()
        return r.json()

    def call(self, method: str, params: dict[str, Any] | None = None, timeout_s: float = 120) -> Any:
        payload = {"method": method, "params": {**(params or {}), "_timeout_s": timeout_s}}
        for attempt in range(2):
            ep = discover()
            try:
                with self._client(timeout_s + 15) as c:
                    r = c.post(f"{ep.url}/rpc", json=payload, headers={"X-OTD-Token": ep.token})
            except httpx.TransportError as exc:
                raise BridgeUnavailable(f"Khong ket noi duoc bridge tai {ep.url} ({exc}). {HOW_TO_START}") from exc

            # 401: OTD vua khoi dong lai -> token moi; doc lai discovery 1 lan.
            if r.status_code == 401 and attempt == 0 and ep.source != "env":
                continue
            break

        try:
            body = r.json()
        except ValueError:
            raise BridgeError(f"Bridge tra ve HTTP {r.status_code} khong phai JSON: {r.text[:300]}") from None

        if not body.get("ok"):
            err = body.get("error") or {}
            msg = f"[{method}] {err.get('type', 'Error')}: {err.get('message', 'loi khong ro')}"
            detail = err.get("detail")
            if detail:
                msg += f"\n--- chi tiet ---\n{detail[:1500]}"
            raise BridgeError(msg)
        return body.get("result")

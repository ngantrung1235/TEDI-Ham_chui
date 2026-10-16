"""Chay snippet C# trong Navisworks qua bridge (script.csharp) va chuan hoa ket qua / loi."""

from __future__ import annotations

from typing import Any, Sequence

from mcp_bridge_common import BridgeClient
from mcp_bridge_common.compat import ToolError


def run_snippet(bridge: BridgeClient, body: str, args: dict[str, Any] | None = None, *,
                headers: Sequence[str] = ("",), timeout_s: float = 120, what: str = "snippet") -> Any:
    """Bien dich + chay `body`. Thu lan luot cac `headers` (dong using) toi khi bien dich duoc.

    Tra ve return_value (JSON). Loi bien dich -> ToolError liet ke diagnostic cua TAT CA bien the de LLM
    doi chieu bang explore_api va sua bang run_csharp. Loi luc chay (exception trong Navisworks) do
    BridgeClient nem BridgeError.
    """
    failures: list[list[str]] = []
    for header in headers:
        result = bridge.call(
            "script.csharp",
            {"code": header + body, "args": args or {}, "timeout_s": timeout_s},
            timeout_s=timeout_s + 30,
        )
        if result.get("compiled"):
            return result.get("return_value")
        failures.append(result.get("errors") or ["(khong co diagnostic)"])

    lines = [f"Khong bien dich duoc {what} trong Navisworks - ten lop/ham API co the khac ban dang chay."]
    for i, errs in enumerate(failures, start=1):
        label = f" (bien the using #{i})" if len(failures) > 1 else ""
        lines.append(f"Loi{label}:")
        lines.extend(f"  {e}" for e in errs[:8])
    lines.append("Cach xu ly: dung nw_explore_api(assembly_filter=..., type_filter=..., include_members=True) de tim "
                 "dung ten, sau do chay ban sua bang nw_run_csharp.")
    raise ToolError("\n".join(lines))

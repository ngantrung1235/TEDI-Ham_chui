"""Connection state for the PLAXIS 3D Input and Output remote scripting servers."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.environ.get("PLAXIS_HOST", "localhost"))
    input_port: int = field(default_factory=lambda: _env_int("PLAXIS_INPUT_PORT", 10000))
    output_port: int = field(default_factory=lambda: _env_int("PLAXIS_OUTPUT_PORT", 10001))
    password: str = field(default_factory=lambda: os.environ.get("PLAXIS_PASSWORD", ""))
    # seconds; None lets long calculations run without an HTTP timeout
    request_timeout: float | None = None
    allow_python: bool = field(
        default_factory=lambda: os.environ.get("PLAXIS_MCP_ALLOW_PYTHON", "0") in {"1", "true", "yes"}
    )


def _default_factory(host: str, port: int, password: str, request_timeout: float | None):
    from plxscripting.easy import new_server  # imported lazily: optional at test time

    return new_server(host, port, password=password, request_timeout=request_timeout)


class PlaxisSession:
    """Holds (s_i, g_i) for Input and (s_o, g_o) for Output.

    plxscripting is synchronous and not thread-safe, so every call goes
    through ``lock``; the MCP layer runs the calls in a worker thread.
    """

    def __init__(self, settings: Settings | None = None, server_factory: Callable | None = None):
        self.settings = settings or Settings()
        self._factory = server_factory or _default_factory
        self.lock = threading.RLock()
        self.s_i: Any = None
        self.g_i: Any = None
        self.s_o: Any = None
        self.g_o: Any = None

    # -- Input ---------------------------------------------------------------
    def connect_input(self, host: str | None = None, port: int | None = None, password: str | None = None) -> dict:
        st = self.settings
        st.host = host or st.host
        st.input_port = port or st.input_port
        if password is not None:
            st.password = password
        try:
            self.s_i, self.g_i = self._factory(st.host, st.input_port, st.password, st.request_timeout)
        except Exception as exc:
            self.s_i = self.g_i = None
            raise RuntimeError(
                f"Cannot reach PLAXIS 3D Input at {st.host}:{st.input_port}. Open PLAXIS 3D Input, enable "
                "Expert > Configure remote scripting server with the same port and password "
                f"(env PLAXIS_PASSWORD). Detail: {exc}"
            ) from exc
        self.s_o = self.g_o = None
        return self.describe()

    def input(self) -> tuple[Any, Any]:
        if self.g_i is None:
            self.connect_input()
        return self.s_i, self.g_i

    # -- Output --------------------------------------------------------------
    def connect_output(self, port: int | None = None, phase_name: str | None = None) -> dict:
        """Connect to Output. Without a port, ask Input to open Output via ``view``."""
        st = self.settings
        if port is None:
            _, g_i = self.input()
            phase = getattr(g_i, phase_name) if phase_name else list(g_i.Phases)[-1]
            port = int(g_i.view(phase))
        st.output_port = port
        self.s_o, self.g_o = self._factory(st.host, port, st.password, st.request_timeout)
        return self.describe()

    def output(self) -> tuple[Any, Any]:
        if self.g_o is None:
            self.connect_output()
        return self.s_o, self.g_o

    def describe(self) -> dict:
        info: dict[str, Any] = {
            "host": self.settings.host,
            "input_connected": self.g_i is not None,
            "output_connected": self.g_o is not None,
            "input_port": self.settings.input_port,
            "output_port": self.settings.output_port if self.g_o is not None else None,
        }
        s = self.s_i
        if s is not None:
            for attr in ("name", "major_version", "minor_version", "is_3d"):
                try:
                    info[attr] = getattr(s, attr)
                except Exception:
                    pass
            if info.get("is_3d") is False:
                info["warning"] = "Connected server is PLAXIS 2D; this MCP server targets PLAXIS 3D."
        return info

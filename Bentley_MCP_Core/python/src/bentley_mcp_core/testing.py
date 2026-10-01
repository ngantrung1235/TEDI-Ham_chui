"""Bridge gia lap (thay cho add-in trong san pham Bentley) de test MCP server khi khong co san pham."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# PNG 1x1 hop le
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class FakeBridge:
    def __init__(self, token: str = "tok-123") -> None:
        self.token = token
        self.calls: list[tuple[str, dict]] = []
        self.next_id = 4241
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # im lang
                pass

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.startswith("/health"):
                    self._send(200, {"ok": True, "name": "FakeMcpBridge", "version": "fake"})
                else:
                    self._send(404, {"ok": False})

            def do_POST(self):
                if self.headers.get("X-MCP-Token") != bridge.token:
                    self._send(401, {"ok": False, "error": {"type": "Unauthorized", "message": "bad token"}})
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                method, params = body["method"], body.get("params", {})
                bridge.calls.append((method, params))
                self._send(200, bridge.respond(method, params))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def respond(self, method: str, params: dict) -> dict:
        if method == "session.info":
            return {"ok": True, "result": {"active_file": "C:/du_an/model.dgn", "units": {"uor_per_meter": 10000.0}}}
        if method == "geometry.extrusion":
            self.next_id += 1
            holes = sum(1 for loop in params["loops"] if loop["role"] == "hole")
            return {"ok": True, "result": {"id": self.next_id, "holes": holes}}
        if method == "view.capture":
            return {"ok": True, "result": {"mime_type": "image/png", "data_base64": base64.b64encode(PNG_1PX).decode()}}
        if method == "keyin.send":
            return {"ok": True, "result": {"queued": params["keyins"]}}
        if method == "elements.get" and params.get("id") == 999:
            return {"ok": False, "error": {"type": "ArgumentException", "message": "Khong tim thay element id=999"}}
        return {"ok": True, "result": {"echo": method}}

    def write_discovery(self, path: Path) -> None:
        path.write_text(json.dumps({"port": self.port, "token": self.token, "pid": 1}), encoding="utf-8")

    def __enter__(self) -> "FakeBridge":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

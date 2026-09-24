"""Single-threaded apartment (STA) worker for AutoCAD COM calls.

COM objects obtained in one thread must be used from that thread, and AutoCAD
rejects calls while it is busy (RPC_E_CALL_REJECTED / RPC_E_SERVERCALL_RETRYLATER),
e.g. during a regen or when a dialog is open. All COM work is therefore queued
to one dedicated thread that called CoInitialize, and busy errors are retried
with back-off.
"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

BUSY_HRESULTS = {
    -2147418111,  # RPC_E_CALL_REJECTED
    -2147417846,  # RPC_E_SERVERCALL_RETRYLATER
    -2147417848,  # RPC_E_DISCONNECTED (reported while AutoCAD restarts a command)
}


def hresult(exc: BaseException) -> int | None:
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):
        return args[0]
    return getattr(exc, "hresult", None)


def with_retry(fn: Callable[[], Any], attempts: int = 20, delay: float = 0.15) -> Any:
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if hresult(exc) not in BUSY_HRESULTS or i == attempts - 1:
                raise
            time.sleep(min(delay * (1.5**i), 2.0))
    raise RuntimeError("unreachable")


class ComWorker:
    """Runs callables on one COM-initialised thread."""

    def __init__(self, init_com: bool = True):
        self._q: "queue.Queue[tuple[Callable[[], Any], Future]]" = queue.Queue()
        self._init_com = init_com
        self._thread = threading.Thread(target=self._run, name="acad-com", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self._init_com:
            try:
                import pythoncom

                pythoncom.CoInitialize()
            except ImportError:
                pass  # non-Windows: only the DXF backend / fakes run here
        while True:
            fn, fut = self._q.get()
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(with_retry(fn))
            except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
                fut.set_exception(exc)

    def submit(self, fn: Callable[[], Any]) -> Future:
        fut: Future = Future()
        self._q.put((fn, fut))
        return fut

    def call(self, fn: Callable[[], Any], timeout: float | None = None) -> Any:
        return self.submit(fn).result(timeout)
